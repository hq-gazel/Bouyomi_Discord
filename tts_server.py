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
    IRODORI_TTS_MODEL_PRECISION (任意、デフォルト "auto")
    IRODORI_TTS_CODEC_DEVICE (任意、デフォルト "auto")
    IRODORI_TTS_COMPILE_MODEL (任意、デフォルト "true")
    IRODORI_TTS_COMPILE_DYNAMIC (任意、デフォルト "true")
    TTS_DEBUG_LOGGING (任意、デフォルト "false")

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

# lib.env_utilsはstdlibのみに依存するため、Irodori-TTS用の重い依存関係を
# 持つこの別venvからでも import 可能(本ファイルはプロジェクトルート直下に
# あるため、スクリプトのあるディレクトリがsys.path[0]となりlibを解決できる)。
from lib.env_utils import get_bool as _env_bool
from lib.env_utils import get_optional as _get_optional
from lib.env_utils import get_raw as _env_raw
from lib.env_utils import parse_int as _parse_int

# irodori_tts パッケージがIrodori-TTSの.venvにインストール済みであれば
# 本来sys.path操作は不要だが、念のためIRODORI_TTS_DIRをsys.pathに追加しておく。
_IRODORI_TTS_DIR = os.environ.get("IRODORI_TTS_DIR", "").strip()
if _IRODORI_TTS_DIR and _IRODORI_TTS_DIR not in sys.path:
    sys.path.insert(0, _IRODORI_TTS_DIR)

import torch
import torchaudio
from huggingface_hub import hf_hub_download
from irodori_tts.inference_runtime import (
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
    model_precision: str
    codec_device: str
    compile_model: bool
    compile_dynamic: bool
    debug_logging: bool


def _load_config() -> _ServerConfig:
    """環境変数からサーバー設定を読み込む。不足・矛盾があればRuntimeErrorを送出。"""
    irodori_tts_dir = _env_raw("IRODORI_TTS_DIR")
    if not irodori_tts_dir:
        raise RuntimeError("環境変数 'IRODORI_TTS_DIR' が未設定です。")

    hf_checkpoint = _get_optional("IRODORI_TTS_HF_CHECKPOINT")
    local_checkpoint = _get_optional("IRODORI_TTS_CHECKPOINT")
    if hf_checkpoint is None and local_checkpoint is None:
        raise RuntimeError(
            "'IRODORI_TTS_HF_CHECKPOINT' か 'IRODORI_TTS_CHECKPOINT' のいずれか"
            "一方を環境変数に設定してください(両方とも未設定です)。"
        )

    ref_wav = _env_raw("IRODORI_TTS_REF_WAV")
    if not ref_wav:
        raise RuntimeError("環境変数 'IRODORI_TTS_REF_WAV' が未設定です。")

    host = _env_raw("TTS_SERVER_HOST") or "127.0.0.1"
    port_raw = _env_raw("TTS_SERVER_PORT") or "8765"
    port = _parse_int("TTS_SERVER_PORT", port_raw)

    model_precision = _env_raw("IRODORI_TTS_MODEL_PRECISION") or "auto"
    codec_device = _env_raw("IRODORI_TTS_CODEC_DEVICE") or "auto"
    compile_model = _env_bool("IRODORI_TTS_COMPILE_MODEL", True)
    compile_dynamic = _env_bool("IRODORI_TTS_COMPILE_DYNAMIC", True)
    debug_logging = _env_bool("TTS_DEBUG_LOGGING", False)

    return _ServerConfig(
        irodori_tts_dir=irodori_tts_dir,
        hf_checkpoint=hf_checkpoint,
        local_checkpoint=local_checkpoint,
        ref_wav=ref_wav,
        host=host,
        port=port,
        model_precision=model_precision,
        codec_device=codec_device,
        compile_model=compile_model,
        compile_dynamic=compile_dynamic,
        debug_logging=debug_logging,
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


def _resolve_model_precision(raw: str, model_device: str) -> str:
    """'auto' なら CUDA検出時 'bf16'、それ以外(CPU等)は 'fp32' に解決する。"""
    if raw.strip().lower() != "auto":
        return raw
    return "bf16" if model_device == "cuda" else "fp32"


def _resolve_codec_device(raw: str) -> str:
    """'auto' なら CUDA使用可否で 'cuda' / 'cpu' に解決する。"""
    if raw.strip().lower() != "auto":
        return raw
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_reference_wav(path: str) -> tuple[torch.Tensor, int]:
    """torchaudio.load()で読み込み、失敗時はsoundfileへフォールバックする。
    Irodori-TTS本体のinference_runtime._load_audio(非公開シンボル)への依存を
    避けるため、同等の最小実装をここに複製している。
    """
    try:
        return torchaudio.load(str(path))
    except RuntimeError:
        import soundfile as sf

        data, sr = sf.read(str(path), dtype="float32")
        wav = torch.from_numpy(data)
        return (wav.unsqueeze(0) if wav.ndim == 1 else wav.T), sr


class _RuntimeState:
    """アプリ全体で共有する推論ランタイムの保持状態。"""

    def __init__(self) -> None:
        self.runtime: InferenceRuntime | None = None
        self.ref_latent_path: str | None = None
        # TTS_DEBUG_LOGGING設定値。/synthesizeでlog_fnを渡すかどうかに使う。
        self.debug_logging: bool = False

    @property
    def ready(self) -> bool:
        return self.runtime is not None and self.ref_latent_path is not None


_state = _RuntimeState()

# torch.compileウォームアップ時に使うダミーテキスト。
_WARMUP_TEXT = "こんにちは、これはウォームアップ用のテストメッセージです。"


def _load_runtime_blocking(config: _ServerConfig) -> InferenceRuntime:
    """モデルロード(ブロッキング処理)。startup時に1回だけ呼ばれる想定。"""
    checkpoint_path = _resolve_checkpoint_path(config)
    model_device = _detect_model_device()
    model_precision = _resolve_model_precision(config.model_precision, model_device)
    codec_device = _resolve_codec_device(config.codec_device)
    print(
        f"[tts_server] loading checkpoint={checkpoint_path} model_device={model_device} "
        f"model_precision={model_precision} codec_device={codec_device} "
        f"compile_model={config.compile_model} compile_dynamic={config.compile_dynamic}"
    )
    runtime = InferenceRuntime.from_key(
        RuntimeKey(
            checkpoint=checkpoint_path,
            model_device=model_device,
            model_precision=model_precision,
            codec_device=codec_device,
            compile_model=config.compile_model,
            compile_dynamic=config.compile_dynamic,
        )
    )
    print("[tts_server] model load complete")
    return runtime


def _warmup_runtime(runtime: InferenceRuntime, ref_latent_path: str, *, debug_logging: bool) -> None:
    """torch.compileの初回コンパイルコストを起動時に前倒しするためのウォームアップ。

    /health が200を返す(_state.readyになる)前に実行することで、実際の初回
    コメント読み上げ時にコンパイル待ちが発生しないようにする。
    失敗時は例外をそのまま伝播させ、起動を失敗させる(設定不備は起動時に
    落とす既存方針を踏襲。不安定な場合はIRODORI_TTS_COMPILE_MODEL=falseで
    ウォームアップ自体を無効化できる)。
    """
    print("[tts_server] compileウォームアップを開始します(初回のみ時間がかかります)...")
    log_fn = print if debug_logging else None
    runtime.synthesize(
        SamplingRequest(text=_WARMUP_TEXT, ref_latent=ref_latent_path), log_fn=log_fn
    )
    print("[tts_server] compileウォームアップが完了しました。")


def _precompute_ref_latent(runtime: InferenceRuntime, ref_wav: str) -> str:
    """参照音声wavを起動時に1回だけエンコードし、結果のlatentを一時ファイルへ
    保存してそのパスを返す。毎synthesize呼び出しで重複していたcodecエンコード
    (CPU上のニューラルネット順伝播)を排除するためのキャッシュ。
    """
    defaults = SamplingRequest(text="")
    wav, sr = _load_reference_wav(ref_wav)
    if defaults.max_ref_seconds is not None and defaults.max_ref_seconds > 0:
        max_ref_samples = max(1, int(float(defaults.max_ref_seconds) * float(sr)))
        if wav.shape[1] > max_ref_samples:
            wav = wav[:, :max_ref_samples]

    ref_latent = runtime.codec.encode_waveform(
        wav.unsqueeze(0),
        sample_rate=int(sr),
        normalize_db=defaults.ref_normalize_db,
        ensure_max=bool(defaults.ref_ensure_max),
    ).cpu()

    fd, tmp_path = tempfile.mkstemp(suffix=".pt", prefix="tts_ref_latent_")
    os.close(fd)
    torch.save(ref_latent, tmp_path)
    print(f"[tts_server] cached reference latent -> {tmp_path}")
    return tmp_path


def _cleanup_state() -> None:
    """ランタイム破棄と参照latent一時ファイルの削除を行う(冪等)。

    Windowsではsubprocess.terminate()/kill()が同一実装(TerminateProcess)で
    猶予なく即死させるため、lifespanのシャットダウンフックが実行される機会が
    ない。そのためmain.py側が強制終了前に /shutdown 経由で明示的に呼び出す。
    """
    _state.runtime = None
    if _state.ref_latent_path is not None:
        Path(_state.ref_latent_path).unlink(missing_ok=True)
        _state.ref_latent_path = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    config = _load_config()
    _state.debug_logging = config.debug_logging
    _state.runtime = _load_runtime_blocking(config)
    _state.ref_latent_path = _precompute_ref_latent(_state.runtime, config.ref_wav)
    if config.compile_model:
        # ウォームアップは_state.ready(=/healthが200を返す)になる前、
        # つまりここで完了させる。失敗時は例外がそのまま伝播し起動が失敗する。
        _warmup_runtime(
            _state.runtime, _state.ref_latent_path, debug_logging=config.debug_logging
        )
    yield
    _cleanup_state()


app = FastAPI(lifespan=_lifespan)


class SynthesizeRequestBody(BaseModel):
    text: str


@app.get("/health")
def health() -> dict[str, str]:
    if not _state.ready:
        raise HTTPException(status_code=503, detail="model is still loading")
    return {"status": "ok"}


@app.post("/shutdown")
def shutdown() -> dict[str, str]:
    """強制終了(terminate/kill)前にクリーンアップを完了させるためのエンドポイント。"""
    _cleanup_state()
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
    ref_latent_path = _state.ref_latent_path
    assert ref_latent_path is not None

    def _synthesize_blocking() -> bytes:
        log_fn = print if _state.debug_logging else None
        result = runtime.synthesize(
            SamplingRequest(text=text, ref_latent=ref_latent_path), log_fn=log_fn
        )
        # torchaudio(torchcodecバックエンド)がBytesIOへの直接保存に対応していない
        # ため、一時ファイル経由でWAVを書き出してからバイト列として読み込む。
        # save_wav()はtorchaudio失敗時にsoundfileへフォールバックする実装。
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "synthesized.wav"
            save_wav(tmp_path, result.audio, result.sample_rate)
            return tmp_path.read_bytes()

    loop = asyncio.get_running_loop()
    try:
        wav_bytes = await loop.run_in_executor(None, _synthesize_blocking)
    except Exception as e:
        print(f"[tts_server] synthesize failed: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "synthesis_failed", "message": str(e)},
        ) from e
    return Response(content=wav_bytes, media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    _config = _load_config()
    uvicorn.run(app, host=_config.host, port=_config.port)
