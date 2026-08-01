"""アプリケーション設定を .env から読み込むモジュール。

呼び出し側(main.py, tts_server.py 等)は load_settings() を呼ぶだけで
Settings インスタンスを取得できる。必須項目が不足・不正な場合は、
起動時にどの環境変数が問題かが分かるメッセージ付きで RuntimeError を送出する。
"""

from __future__ import annotations

import string
from dataclasses import dataclass

from dotenv import load_dotenv

from lib.env_utils import (
    get_bool as _get_bool,
)
from lib.env_utils import (
    get_float as _get_float,
)
from lib.env_utils import (
    get_int as _get_int,
)
from lib.env_utils import (
    get_optional as _get_optional,
)
from lib.env_utils import (
    get_optional_int as _get_optional_int,
)
from lib.env_utils import (
    get_raw as _raw,
)
from lib.env_utils import (
    get_required as _get_required,
)
from lib.env_utils import (
    parse_int as _parse_int,
)

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

# Twitchコメント読み上げ時のテンプレート文字列のデフォルト値・許可プレースホルダー
_DEFAULT_TWITCH_COMMENT_TEMPLATE = "{username}さん、{comment}"
_TEMPLATE_ALLOWED_PLACEHOLDERS = frozenset({"username", "comment"})


@dataclass(frozen=True)
class Settings:
    # Discord
    discord_bot_token: str
    discord_admin_user_id: int
    discord_guild_id: int | None
    admin_check_interval_seconds: float
    playback_timeout_seconds: float
    retry_backoff_initial_seconds: float
    retry_backoff_max_seconds: float
    retry_circuit_open_threshold: int
    retry_circuit_open_interval_seconds: float

    # Twitch
    twitch_client_id: str
    twitch_oauth_token: str
    twitch_bot_nick: str
    twitch_channel: str
    twitch_comment_template: str

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


def _validate_template_placeholders(
    env_name: str, template: str, allowed: frozenset[str]
) -> None:
    """テンプレート文字列内のプレースホルダーが許可リスト内のみであることを検証する。

    `string.Formatter().parse()` でフィールド名を抽出する。属性/添字アクセス
    (`{username.foo}` 等)や空フィールド名(`{}`)は `field_name` にそのまま
    現れるため、許可リストとの完全一致のみを許可することでまとめて弾く。
    """
    for _, field_name, _, _ in string.Formatter().parse(template):
        if field_name is None:
            continue
        if field_name not in allowed:
            raise RuntimeError(
                f"環境変数 '{env_name}' のテンプレート '{template}' に"
                f" 許可されていないプレースホルダー '{{{field_name}}}' が含まれています。"
                f" 使用可能なプレースホルダー: {', '.join(sorted(allowed))}"
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

    twitch_comment_template = (
        _raw("TWITCH_COMMENT_TEMPLATE") or _DEFAULT_TWITCH_COMMENT_TEMPLATE
    )
    _validate_template_placeholders(
        "TWITCH_COMMENT_TEMPLATE", twitch_comment_template, _TEMPLATE_ALLOWED_PLACEHOLDERS
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
        retry_backoff_initial_seconds=_get_float("RETRY_BACKOFF_INITIAL_SECONDS", 1.0),
        retry_backoff_max_seconds=_get_float("RETRY_BACKOFF_MAX_SECONDS", 30.0),
        retry_circuit_open_threshold=_get_int("RETRY_CIRCUIT_OPEN_THRESHOLD", 5),
        retry_circuit_open_interval_seconds=_get_float(
            "RETRY_CIRCUIT_OPEN_INTERVAL_SECONDS", 60.0
        ),
        twitch_client_id=_get_required("TWITCH_CLIENT_ID"),
        twitch_oauth_token=_get_required("TWITCH_OAUTH_TOKEN"),
        twitch_bot_nick=_get_required("TWITCH_BOT_NICK"),
        twitch_channel=_get_required("TWITCH_CHANNEL"),
        twitch_comment_template=twitch_comment_template,
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
