"""アプリケーション設定を .env から読み込むモジュール。

呼び出し側(main.py, tts_server.py 等)は load_settings() を呼ぶだけで
Settings インスタンスを取得できる。必須項目が不足・不正な場合は、
起動時にどの環境変数が問題かが分かるメッセージ付きで RuntimeError を送出する。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# .env に必ず存在し、かつ空文字であってはならない環境変数名の一覧
_REQUIRED_ENV_NAMES = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_ADMIN_USER_ID",
    "TWITCH_CLIENT_ID",
    "TWITCH_OAUTH_TOKEN",
    "TWITCH_BOT_NICK",
    "TWITCH_CHANNEL",
    "IRODORI_TTS_DIR",
    "IRODORI_TTS_VENV_PYTHON",
    "IRODORI_TTS_REF_WAV",
)


@dataclass(frozen=True)
class Settings:
    # Discord
    discord_bot_token: str
    discord_admin_user_id: int
    discord_guild_id: int | None
    admin_check_interval_seconds: float
    playback_timeout_seconds: float

    # Twitch
    twitch_client_id: str
    twitch_oauth_token: str
    twitch_bot_nick: str
    twitch_channel: str

    # Irodori-TTS連携
    irodori_tts_dir: str
    irodori_tts_venv_python: str
    irodori_tts_hf_checkpoint: str | None
    irodori_tts_checkpoint: str | None
    irodori_tts_ref_wav: str
    irodori_tts_model_precision: str
    irodori_tts_codec_device: str
    irodori_tts_compile_model: bool
    irodori_tts_compile_dynamic: bool

    # TTSサイドカーサーバー
    tts_server_host: str
    tts_server_port: int
    tts_debug_logging: bool
    tts_startup_timeout_seconds: float

    # 任意
    ffmpeg_path: str | None


def _raw(name: str) -> str:
    """環境変数を文字列として取得する(前後の空白は除去)。未設定なら空文字。"""
    return os.environ.get(name, "").strip()


def _get_required(name: str) -> str:
    """必須環境変数を取得する。未設定または空文字ならエラー。"""
    value = _raw(name)
    if not value:
        raise RuntimeError(
            f"環境変数 '{name}' が未設定です。.env ファイルに値を設定してください。"
        )
    return value


def _get_optional(name: str) -> str | None:
    """任意環境変数を取得する。未設定または空文字なら None。"""
    value = _raw(name)
    return value if value else None


def _parse_int(name: str, value: str) -> int:
    """文字列を int に変換する。失敗時はどの変数が原因かが分かるエラーを送出。"""
    try:
        return int(value)
    except ValueError as e:
        raise RuntimeError(
            f"環境変数 '{name}' の値 '{value}' を整数に変換できません。"
        ) from e


def _get_optional_int(name: str) -> int | None:
    value = _get_optional(name)
    if value is None:
        return None
    return _parse_int(name, value)


def _get_float(name: str, default: float) -> float:
    value = _raw(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as e:
        raise RuntimeError(
            f"環境変数 '{name}' の値 '{value}' を数値(float)に変換できません。"
        ) from e


def _get_bool(name: str, default: bool) -> bool:
    """環境変数を真偽値として取得する。未設定(空文字)なら default を返す。"""
    value = _raw(name).lower()
    if not value:
        return default
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise RuntimeError(
        f"環境変数 '{name}' の値 '{value}' を真偽値に変換できません"
        "('true'/'false' 等を指定してください)。"
    )


def load_settings() -> Settings:
    """.env を読み込み、Settings インスタンスを構築する。

    必須項目の不足・型変換の失敗があれば RuntimeError を送出する。
    """
    load_dotenv()

    # 必須項目の不足はまとめて検出し、一目で分かるように報告する
    missing = [name for name in _REQUIRED_ENV_NAMES if not _raw(name)]
    if missing:
        raise RuntimeError(
            "以下の必須環境変数が .env に設定されていません: " + ", ".join(missing)
        )

    hf_checkpoint = _get_optional("IRODORI_TTS_HF_CHECKPOINT")
    local_checkpoint = _get_optional("IRODORI_TTS_CHECKPOINT")
    if hf_checkpoint is None and local_checkpoint is None:
        raise RuntimeError(
            "IRODORI_TTS_HF_CHECKPOINT か IRODORI_TTS_CHECKPOINT のいずれか一方を"
            " .env に設定してください(両方とも未設定です)。"
        )

    return Settings(
        discord_bot_token=_get_required("DISCORD_BOT_TOKEN"),
        discord_admin_user_id=_parse_int(
            "DISCORD_ADMIN_USER_ID", _get_required("DISCORD_ADMIN_USER_ID")
        ),
        discord_guild_id=_get_optional_int("DISCORD_GUILD_ID"),
        admin_check_interval_seconds=_get_float("ADMIN_CHECK_INTERVAL_SECONDS", 5.0),
        playback_timeout_seconds=_get_float("PLAYBACK_TIMEOUT_SECONDS", 30.0),
        twitch_client_id=_get_required("TWITCH_CLIENT_ID"),
        twitch_oauth_token=_get_required("TWITCH_OAUTH_TOKEN"),
        twitch_bot_nick=_get_required("TWITCH_BOT_NICK"),
        twitch_channel=_get_required("TWITCH_CHANNEL"),
        irodori_tts_dir=_get_required("IRODORI_TTS_DIR"),
        irodori_tts_venv_python=_get_required("IRODORI_TTS_VENV_PYTHON"),
        irodori_tts_hf_checkpoint=hf_checkpoint,
        irodori_tts_checkpoint=local_checkpoint,
        irodori_tts_ref_wav=_get_required("IRODORI_TTS_REF_WAV"),
        irodori_tts_model_precision=_raw("IRODORI_TTS_MODEL_PRECISION") or "auto",
        irodori_tts_codec_device=_raw("IRODORI_TTS_CODEC_DEVICE") or "auto",
        irodori_tts_compile_model=_get_bool("IRODORI_TTS_COMPILE_MODEL", True),
        irodori_tts_compile_dynamic=_get_bool("IRODORI_TTS_COMPILE_DYNAMIC", True),
        tts_server_host=_raw("TTS_SERVER_HOST") or "127.0.0.1",
        tts_server_port=_parse_int(
            "TTS_SERVER_PORT", _raw("TTS_SERVER_PORT") or "8765"
        ),
        tts_debug_logging=_get_bool("TTS_DEBUG_LOGGING", False),
        tts_startup_timeout_seconds=_get_float("TTS_STARTUP_TIMEOUT_SECONDS", 600.0),
        ffmpeg_path=_get_optional("FFMPEG_PATH"),
    )
