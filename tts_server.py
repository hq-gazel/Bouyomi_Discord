"""Irodori-TTSサイドカーサーバー。

Bouyomi_Discord本体(discord.py/TwitchIO等の軽量venv)とは別に、
Irodori-TTS用の重い依存関係(torch/CUDA)を持つ`.venv`のpython.exeで
起動されるFastAPIサーバー。Bouyomi_Discord側からはHTTP経由でのみ
呼び出す(`lib/tts_client.py`参照)。

このファイルは `lib.config`(Bouyomi_Discordのvenv専用パッケージ)を
importできない前提のため、設定はすべて環境変数から直接読み込む。
main.py側がsubprocess起動時に以下の環境変数をセットして渡す想定:
    IRODORI_TTS_DIR
    IRODORI_TTS_HF_CHECKPOINT (任意)
    IRODORI_TTS_CHECKPOINT (任意、どちらか一方は設定される)
    IRODORI_TTS_REF_WAV
    TTS_SERVER_HOST (デフォルト "127.0.0.1")
    TTS_SERVER_PORT (デフォルト "8765")

起動: `<Irodori-TTSのvenv>\\Scripts\\python.exe tts_server.py`
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

# irodori_tts パッケージがIrodori-TTSの.venvにインストール済みであれば
# 本来sys.path操作は不要だが、念のためIRODORI_TTS_DIRをsys.pathに追加しておく。
_IRODORI_TTS_DIR = os.environ.get("IRODORI_TTS_DIR", "").strip()
if _IRODORI_TTS_DIR and _IRODORI_TTS_DIR not in sys.path:
    sys.path.insert(0, _IRODORI_TTS_DIR)

import torch  # noqa: E402
from huggingface_hub import hf_hub_download  # noqa: E402

from irodori_tts.inference_runtime import (  # noqa: E402
    InferenceRuntime,
    RuntimeKey,
    SamplingRequest,
    save_wav,
)


@dataclass(frozen=True)
class _ServerConfig:
    """環境変数から読み込んだサーバー設定。"""

    irodori_tts_dir: str
    hf_checkpoint: str | None
    local_checkpoint: str | None
    ref_wav: str
    host: str
    port: int


def _load_config() -> _ServerConfig:
    """環境変数からサーバー設定を読み込む。不足・矛盾があればRuntimeErrorを送出。"""
    irodori_tts_dir = os.environ.get("IRODORI_TTS_DIR", "").strip()
    if not irodori_tts_dir:
        raise RuntimeError("環境変数 'IRODORI_TTS_DIR' が未設定です。")

    hf_checkpoint = os.environ.get("IRODORI_TTS_HF_CHECKPOINT", "").strip() or None
    local_checkpoint = os.environ.get("IRODORI_TTS_CHECKPOINT", "").strip() or None
    if hf_checkpoint is None and local_checkpoint is None:
        raise RuntimeError(
            "'IRODORI_TTS_HF_CHECKPOINT' か 'IRODORI_TTS_CHECKPOINT' のいずれか"
            "一方を環境変数に設定してください(両方とも未設定です)。"
        )

    ref_wav = os.environ.get("IRODORI_TTS_REF_WAV", "").strip()
    if not ref_wav:
        raise RuntimeError("環境変数 'IRODORI_TTS_REF_WAV' が未設定です。")

    host = os.environ.get("TTS_SERVER_HOST", "").strip() or "127.0.0.1"
    port_raw = os.environ.get("TTS_SERVER_PORT", "").strip() or "8765"
    try:
        port = int(port_raw)
    except ValueError as e:
        raise RuntimeError(
            f"環境変数 'TTS_SERVER_PORT' の値 '{port_raw}' を整数に変換できません。"
        ) from e

    return _ServerConfig(
        irodori_tts_dir=irodori_tts_dir,
        hf_checkpoint=hf_checkpoint,
        local_checkpoint=local_checkpoint,
        ref_wav=ref_wav,
        host=host,
        port=port,
    )


def _resolve_checkpoint_path(config: _ServerConfig) -> str:
    """ローカルチェックポイント or HuggingFace Hubからダウンロードしたパスを返す。

    Irodori-TTSのCLI(infer.py)と同様、HF指定時は`model.safetensors`を
    hf_hub_downloadでダウンロードして得たローカルキャッシュパスを使う。
    """
    if config.local_checkpoint is not None:
        return config.local_checkpoint

    assert config.hf_checkpoint is not None
    return hf_hub_download(
        repo_id=config.hf_checkpoint,
        filename="model.safetensors",
    )


def _detect_model_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


class _RuntimeState:
    """アプリ全体で共有する推論ランタイムの保持状態。"""

    def __init__(self) -> None:
        self.runtime: InferenceRuntime | None = None
        self.ref_wav: str | None = None

    @property
    def ready(self) -> bool:
        return self.runtime is not None


_state = _RuntimeState()


def _load_runtime_blocking(config: _ServerConfig) -> InferenceRuntime:
    """モデルロード(ブロッキング処理)。startup時に1回だけ呼ばれる想定。"""
    checkpoint_path = _resolve_checkpoint_path(config)
    model_device = _detect_model_device()
    print(f"[tts_server] loading checkpoint={checkpoint_path} model_device={model_device}")
    runtime = InferenceRuntime.from_key(
        RuntimeKey(checkpoint=checkpoint_path, model_device=model_device)
    )
    print("[tts_server] model load complete")
    return runtime


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    config = _load_config()
    _state.ref_wav = config.ref_wav
    _state.runtime = _load_runtime_blocking(config)
    yield
    _state.runtime = None


app = FastAPI(lifespan=_lifespan)


class SynthesizeRequestBody(BaseModel):
    text: str


@app.get("/health")
def health() -> dict[str, str]:
    if not _state.ready:
        raise HTTPException(status_code=503, detail="model is still loading")
    return {"status": "ok"}


@app.post("/synthesize")
async def synthesize(body: SynthesizeRequestBody) -> Response:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty")
    if not _state.ready:
        raise HTTPException(status_code=503, detail="model is still loading")

    runtime = _state.runtime
    assert runtime is not None
    ref_wav = _state.ref_wav
    assert ref_wav is not None

    def _synthesize_blocking() -> bytes:
        result = runtime.synthesize(SamplingRequest(text=text, ref_wav=ref_wav), log_fn=None)
        # torchaudio(torchcodecバックエンド)がBytesIOへの直接保存に対応していない
        # ため、一時ファイル経由でWAVを書き出してからバイト列として読み込む。
        # save_wav()はtorchaudio失敗時にsoundfileへフォールバックする実装。
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "synthesized.wav"
            save_wav(tmp_path, result.audio, result.sample_rate)
            return tmp_path.read_bytes()

    loop = asyncio.get_running_loop()
    wav_bytes = await loop.run_in_executor(None, _synthesize_blocking)
    return Response(content=wav_bytes, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    _config = _load_config()
    uvicorn.run(app, host=_config.host, port=_config.port)
