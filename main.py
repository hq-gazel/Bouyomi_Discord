"""Bouyomi_Discord エントリポイント。

Twitchコメントを取得し、Irodori-TTSサイドカーサーバーで音声合成した上で、
Discord BOTがボイスチャンネルで読み上げる常駐アプリケーションの起動処理。

起動時にIrodori-TTSサイドカーサーバー(tts_server.py)をsubprocessとして
別インタプリタ(settings.irodori_tts_venv_python)で立ち上げ、healthyになる
のを待ってから、Discord BOTとTwitch BOTを並行実行する。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from lib.bridge import CommentQueueBridge
from lib.config import Settings, load_settings
from lib.discord_bot import DiscordVoiceBot
from lib.tts_client import TtsClient
from lib.twitch_bot import TwitchChatBot

_PROJECT_ROOT = Path(__file__).parent
_TTS_SERVER_PATH = _PROJECT_ROOT / "tts_server.py"
_TTS_SHUTDOWN_TIMEOUT_SECONDS = 10.0


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
    proc: subprocess.Popen[bytes], tts_client: TtsClient
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
        proc.wait(timeout=_TTS_SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


async def main() -> None:
    try:
        settings = load_settings()
    except RuntimeError as e:
        print(f"設定エラー: {e}", file=sys.stderr)
        sys.exit(1)

    print("[main] Irodori-TTSサイドカーサーバーを起動しています...")
    tts_process = _start_tts_server_process(settings)

    tts_client = TtsClient(host=settings.tts_server_host, port=settings.tts_server_port)

    try:
        await tts_client.wait_until_healthy(timeout=settings.tts_startup_timeout_seconds)
    except TimeoutError as e:
        print(f"TTSサーバー起動エラー: {e}", file=sys.stderr)
        await _stop_tts_server_process(tts_process, tts_client)
        sys.exit(1)

    print("[main] Irodori-TTSサイドカーサーバーの起動を確認しました。")

    bridge = CommentQueueBridge()
    discord_bot = DiscordVoiceBot(settings, bridge, tts_client)
    twitch_bot = TwitchChatBot(settings, bridge)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(discord_bot.run())
            tg.create_task(twitch_bot.run())
    finally:
        print("[main] シャットダウン処理を開始します...")
        await discord_bot.shutdown()
        await twitch_bot.shutdown()
        await _stop_tts_server_process(tts_process, tts_client)
        print("[main] シャットダウン完了。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
