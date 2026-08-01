"""Bouyomi_Discord エントリポイント。

Twitchコメントを取得し、Irodori-TTSサイドカーサーバーで音声合成した上で、
Discord BOTがボイスチャンネルで読み上げる常駐アプリケーションの起動処理。

起動時にIrodori-TTSサイドカーサーバー(tts_server.py)をsubprocessとして
別インタプリタ(settings.irodori_tts_venv_python)で立ち上げ、healthyになる
のを待ってから、Discord BOTとTwitch BOTを並行実行する。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from lib.bridge import CommentQueueBridge
from lib.config import Settings, load_settings
from lib.discord_bot import DiscordVoiceBot
from lib.ng_word_filter import NgWordMasker, load_ng_words
from lib.tts_client import TtsClient
from lib.twitch_bot import TwitchChatBot
from lib.user_aliases import load_user_aliases

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent
_TTS_SERVER_PATH = _PROJECT_ROOT / "tts_server.py"
_USER_ALIASES_PATH = _PROJECT_ROOT / "cfg" / "user_aliases.json"
_NG_WORDS_PATH = _PROJECT_ROOT / "cfg" / "ng_words.txt"


def _configure_logging(*, debug: bool) -> None:
    """ルートロガーを初期化する。DEBUG_LOGGING有効時はDEBUGレベルにする。"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="[%(levelname)s] [%(name)s] %(message)s")


def _start_tts_server_process(settings: Settings) -> subprocess.Popen[bytes]:
    """Irodori-TTSサイドカーサーバーをsubprocessとして起動する。

    tts_server.py は lib.config をimportできない設計のため、必要な設定は
    環境変数経由で渡す。
    """
    env = os.environ.copy()
    env["IRODORI_TTS_DIR"] = settings.irodori_tts_dir
    if settings.irodori_tts_hf_checkpoint:
        env["IRODORI_TTS_HF_CHECKPOINT"] = settings.irodori_tts_hf_checkpoint
    if settings.irodori_tts_checkpoint:
        env["IRODORI_TTS_CHECKPOINT"] = settings.irodori_tts_checkpoint
    env["IRODORI_TTS_REF_WAV"] = settings.irodori_tts_ref_wav
    env["TTS_SERVER_HOST"] = settings.tts_server_host
    env["TTS_SERVER_PORT"] = str(settings.tts_server_port)
    env["IRODORI_TTS_MODEL_PRECISION"] = settings.irodori_tts_model_precision
    env["IRODORI_TTS_CODEC_DEVICE"] = settings.irodori_tts_codec_device
    env["IRODORI_TTS_COMPILE_MODEL"] = str(settings.irodori_tts_compile_model).lower()
    env["IRODORI_TTS_COMPILE_DYNAMIC"] = str(settings.irodori_tts_compile_dynamic).lower()
    env["TTS_DEBUG_LOGGING"] = str(settings.tts_debug_logging).lower()

    return subprocess.Popen(
        [settings.irodori_tts_venv_python, str(_TTS_SERVER_PATH)],
        cwd=str(_PROJECT_ROOT),
        env=env,
    )


async def _stop_tts_server_process(
    proc: subprocess.Popen[bytes],
    tts_client: TtsClient,
    shutdown_timeout_seconds: float,
) -> None:
    """TTSサイドカーサブプロセスを終了する(terminate優先、タイムアウト時はkill)。

    Windowsではterminate()/kill()が猶予なく即死させ、TTSサーバー側のlifespan
    シャットダウンフックが実行されないため、強制終了前に/shutdown経由で
    明示的にクリーンアップを完了させる。
    """
    if proc.poll() is not None:
        return

    await tts_client.shutdown()
    proc.terminate()
    try:
        proc.wait(timeout=shutdown_timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


async def main() -> None:
    # 設定読み込み前はDEBUG_LOGGINGの値が分からないため、まずINFOで初期化し、
    # 読み込み成功後にsettings.debug_loggingに応じてレベルを調整する。
    _configure_logging(debug=False)
    try:
        settings = load_settings()
        user_aliases = load_user_aliases(_USER_ALIASES_PATH)
        ng_word_masker = NgWordMasker(load_ng_words(_NG_WORDS_PATH))
    except RuntimeError as e:
        logger.error(f"設定エラー: {e}")
        sys.exit(1)

    if settings.debug_logging:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Irodori-TTSサイドカーサーバーを起動しています...")
    tts_process = _start_tts_server_process(settings)

    tts_client = TtsClient(
        host=settings.tts_server_host,
        port=settings.tts_server_port,
        synthesize_timeout_seconds=settings.tts_synthesize_timeout_seconds,
        health_check_timeout_seconds=settings.tts_health_check_timeout_seconds,
    )

    try:
        await tts_client.wait_until_healthy(timeout=settings.tts_startup_timeout_seconds)
    except TimeoutError as e:
        logger.error(f"TTSサーバー起動エラー: {e}")
        await _stop_tts_server_process(
            tts_process, tts_client, settings.tts_shutdown_timeout_seconds
        )
        sys.exit(1)

    logger.info("Irodori-TTSサイドカーサーバーの起動を確認しました。")

    bridge = CommentQueueBridge()
    discord_bot = DiscordVoiceBot(settings, bridge, tts_client)
    twitch_bot = TwitchChatBot(settings, bridge, user_aliases, ng_word_masker)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(discord_bot.run())
            tg.create_task(twitch_bot.run())
    finally:
        logger.info("シャットダウン処理を開始します...")
        await discord_bot.shutdown()
        await twitch_bot.shutdown()
        await _stop_tts_server_process(
            tts_process, tts_client, settings.tts_shutdown_timeout_seconds
        )
        logger.info("シャットダウン完了。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
