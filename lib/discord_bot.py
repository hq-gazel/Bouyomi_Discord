"""Discord BOT本体。

Twitchコメント(TTS合成済み音声)を、管理者が入室しているVCまで追いかけて
再生するボイスBOTを提供する。

前提:
- Discord Developer Portal で "SERVER MEMBERS INTENT" を有効化しておくこと
  (intents.members = True を使うために必須)。
- 音声再生には discord.py の FFmpegPCMAudio を使うため、システムに ffmpeg の
  実行可能ファイルが必要(PATH上にあるか、settings.ffmpeg_path で絶対パス指定)。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import discord
from discord.ext import tasks

from lib.bridge import LatestOnlyBridge
from lib.config import Settings
from lib.tts_client import TtsClient


class DiscordVoiceBot:
    """管理者のVC入退室を追跡し、TwitchコメントのTTS音声を再生するBOT。"""

    def __init__(
        self, settings: Settings, bridge: LatestOnlyBridge, tts_client: TtsClient
    ) -> None:
        self._settings = settings
        self._bridge = bridge
        self._tts_client = tts_client

        # 管理者を追いかけて接続している VoiceClient(未接続なら None)。
        # 複数ギルド同時対応は不要なので、単一の VoiceClient のみ保持する。
        self._voice_client: discord.VoiceClient | None = None

        intents = discord.Intents.default()
        # 管理者のボイス状態変化・メンバー情報を取得するために必須。
        # Discord Developer Portal で "Server Members Intent" を有効化しておくこと。
        intents.members = True
        intents.voice_states = True
        intents.guilds = True

        self._client = discord.Client(intents=intents)

        # イベントハンドラ・タスクを紐付け
        self._client.event(self.on_ready)
        self._client.event(self.on_voice_state_update)

        self._reconcile_loop = tasks.loop(
            seconds=settings.admin_check_interval_seconds
        )(self._reconcile_loop_body)
        self._reconcile_loop.before_loop(self._before_reconcile_loop)

        self._consume_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        """discord.pyクライアントを起動し、切断されるまでブロックする。"""
        # WindowsではdiscordがlibopusをOSに自動ロードしないため、明示的にロードする。
        # 未ロードのままFFmpegPCMAudio(PCM音源)を再生するとOpusNotLoadedで
        # 音声再生タスクが即死し、無音のまま気付けない不具合になる。
        if not discord.opus.is_loaded():
            discord.opus._load_default()
            if discord.opus.is_loaded():
                print("[discord_bot] libopusをロードしました。")
            else:
                print(
                    "[discord_bot] libopusのロードに失敗しました。音声再生ができません。"
                )

        await self._client.start(self._settings.discord_bot_token)

    async def shutdown(self) -> None:
        """discord.pyクライアントを安全にクローズする(VC切断含む)。"""
        if self._reconcile_loop.is_running():
            self._reconcile_loop.cancel()
        if self._consume_task is not None:
            self._consume_task.cancel()

        if self._voice_client is not None and self._voice_client.is_connected():
            await self._voice_client.disconnect()
            self._voice_client = None

        await self._client.close()

    async def on_ready(self) -> None:
        """接続完了時、管理者の現在のVC状態を能動的に同期し、定期タスクを開始する。"""
        print(f"[discord_bot] ログイン完了: {self._client.user}")

        await self._reconcile_admin_voice_state()

        # 二重起動を避けるため、既に走っていなければ開始する。
        if not self._reconcile_loop.is_running():
            self._reconcile_loop.start()
        if self._consume_task is None:
            self._consume_task = asyncio.create_task(self._consume_loop())

    async def on_voice_state_update(
        self,
        member: discord.Member,
        _before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """管理者のボイス状態変化に応じて、BOTのVC接続を追従させる。"""
        if member.id != self._settings.discord_admin_user_id:
            return

        if after.channel is not None:
            # 管理者が(別の)VCに入室/移動した
            if (
                self._voice_client is not None
                and self._voice_client.is_connected()
            ):
                if self._voice_client.channel.id != after.channel.id:
                    await self._voice_client.move_to(after.channel)
            else:
                self._voice_client = await after.channel.connect()
        else:
            # 管理者が全VCから退出した
            if self._voice_client is not None and self._voice_client.is_connected():
                await self._voice_client.disconnect()
            self._voice_client = None

    async def _reconcile_admin_voice_state(self) -> None:
        """管理者の現在のVC在室状況を能動的にチェックし、BOTの接続状態を同期する。

        on_ready 時の初期同期と、定期ポーリングによる自己修復の両方から
        呼び出される共通ロジック(イベント取りこぼし対策)。
        """
        admin_id = self._settings.discord_admin_user_id

        member: discord.Member | None = None
        if self._settings.discord_guild_id is not None:
            guild = self._client.get_guild(self._settings.discord_guild_id)
            if guild is not None:
                member = guild.get_member(admin_id)
        else:
            for guild in self._client.guilds:
                found = guild.get_member(admin_id)
                if found is not None:
                    member = found
                    break

        if member is not None and member.voice is not None and member.voice.channel is not None:
            target_channel = member.voice.channel
            if self._voice_client is not None and self._voice_client.is_connected():
                if self._voice_client.channel.id != target_channel.id:
                    await self._voice_client.move_to(target_channel)
            else:
                self._voice_client = await target_channel.connect()
        else:
            # 管理者がどのVCにもいない場合、接続中なら切断しておく。
            if self._voice_client is not None and self._voice_client.is_connected():
                await self._voice_client.disconnect()
            self._voice_client = None

    async def _before_reconcile_loop(self) -> None:
        await self._client.wait_until_ready()

    async def _reconcile_loop_body(self) -> None:
        await self._reconcile_admin_voice_state()

    async def _consume_loop(self) -> None:
        """Twitchコメント(のTTS音声)を取り出し、順次VCで再生し続けるループ。"""
        while True:
            text = await self._bridge.wait_and_take()
            print(f"[discord_bot] TTS合成を開始します: {text!r}")
            try:
                wav_bytes = await self._tts_client.synthesize(text)
            except (RuntimeError, TimeoutError) as e:
                print(f"[discord_bot] TTS合成に失敗しました: {e}")
                continue
            print(f"[discord_bot] TTS合成完了({len(wav_bytes)} bytes)。再生します。")
            try:
                await self._play(wav_bytes)
            except discord.DiscordException as e:
                print(f"[discord_bot] 音声再生に失敗しました: {e}")
                continue
            print("[discord_bot] 再生完了。")

    async def _play(self, wav_bytes: bytes) -> None:
        """WAV音声データを、現在接続中のVCで再生する(再生完了まで待機する)。"""
        if self._voice_client is None or not self._voice_client.is_connected():
            print("[discord_bot] VC未接続のため再生をスキップします。")
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_file.write(wav_bytes)
            tmp_path = Path(tmp_file.name)

        try:
            if self._voice_client.is_playing():
                self._voice_client.stop()

            loop = asyncio.get_running_loop()
            finished_event = asyncio.Event()

            def _after_playback(error: Exception | None) -> None:
                if error is not None:
                    print(f"[discord_bot] 再生中にエラーが発生しました: {error}")
                loop.call_soon_threadsafe(finished_event.set)

            source = discord.FFmpegPCMAudio(
                str(tmp_path), executable=self._settings.ffmpeg_path or "ffmpeg"
            )
            self._voice_client.play(source, after=_after_playback)
            await finished_event.wait()
        finally:
            tmp_path.unlink(missing_ok=True)
