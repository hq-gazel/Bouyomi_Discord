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
import io

import discord
from discord.ext import tasks

from lib.bridge import CommentQueueBridge
from lib.config import Settings
from lib.tts_client import TtsClient


class DiscordVoiceBot:
    """管理者のVC入退室を追跡し、TwitchコメントのTTS音声を再生するBOT。"""

    def __init__(
        self, settings: Settings, bridge: CommentQueueBridge, tts_client: TtsClient
    ) -> None:
        self._settings = settings
        self._bridge = bridge
        self._tts_client = tts_client
        # 合成済み音声データを合成ループから再生ループへ渡すキュー。
        # maxsize=1により、現在再生中の1件が消費されるまで次の合成結果の
        # putをブロックする(=先読みは常に1件分までに意図的に制限)。
        # 破棄は行わない(フルならブロックするだけ)。
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)

        # 管理者を追いかけて接続している VoiceClient(未接続なら None)。
        # 複数ギルド同時対応は不要なので、単一の VoiceClient のみ保持する。
        self._voice_client: discord.VoiceClient | None = None
        # イベント駆動のon_voice_state_updateと定期ポーリングの
        # _reconcile_loop_bodyがself._voice_clientを同時にチェック→await→代入
        # する競合(TOCTOU、二重connect)を防ぐための排他ロック。
        self._voice_lock = asyncio.Lock()

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

        self._synthesize_task: asyncio.Task[None] | None = None
        self._playback_task: asyncio.Task[None] | None = None

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
        if self._synthesize_task is not None:
            self._synthesize_task.cancel()
        if self._playback_task is not None:
            self._playback_task.cancel()

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
        if self._synthesize_task is None:
            self._synthesize_task = asyncio.create_task(self._synthesize_loop())
        if self._playback_task is None:
            self._playback_task = asyncio.create_task(self._playback_loop())

    async def on_voice_state_update(
        self,
        member: discord.Member,
        _before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """管理者のボイス状態変化に応じて、BOTのVC接続を追従させる。"""
        if member.id != self._settings.discord_admin_user_id:
            return

        async with self._voice_lock:
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

        async with self._voice_lock:
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
        # tasks.Loopは未捕捉例外が飛ぶとループ自体が永久停止するため、
        # ここで握って自己修復ポーリングが止まらないようにする。
        try:
            await self._reconcile_admin_voice_state()
        except Exception as e:
            print(f"[discord_bot] 定期同期処理でエラーが発生しました: {e}")

    async def _synthesize_loop(self) -> None:
        """Twitchコメントを取り出してTTS合成し、結果を再生キューへ渡し続けるループ。

        再生ループとは別タスクとして動くため、現在再生中の音声がある間にも
        次のコメントの合成をバックグラウンドで進められる(パイプライン化)。
        """
        while True:
            text = await self._bridge.wait_and_take()
            print(f"[discord_bot] TTS合成を開始します: {text!r}")
            try:
                wav_bytes = await self._tts_client.synthesize(text)
            except Exception as e:
                print(f"[discord_bot] TTS合成に失敗しました: {e}")
                continue
            print(f"[discord_bot] TTS合成完了({len(wav_bytes)} bytes)。再生キューへ渡します。")
            await self._audio_queue.put(wav_bytes)

    async def _playback_loop(self) -> None:
        """合成済み音声データを再生キューから取り出し、順次VCで再生し続けるループ。"""
        while True:
            wav_bytes = await self._audio_queue.get()
            print("[discord_bot] 再生します。")
            try:
                await self._play(wav_bytes)
            except Exception as e:
                print(f"[discord_bot] 音声再生に失敗しました: {e}")
                continue
            print("[discord_bot] 再生完了。")

    async def _play(self, wav_bytes: bytes) -> None:
        """WAV音声データを、現在接続中のVCで再生する(再生完了まで待機する)。

        ffmpegの偶発的なハング等で再生が詰まった場合に備え、
        settings.playback_timeout_seconds を超えても再生完了が通知されなければ
        強制的に復旧を試みて例外を送出する(呼び出し元の_playback_loopが
        次のキュー項目に進めるようにするため)。
        """
        async with self._voice_lock:
            voice_client = self._voice_client

        if voice_client is None or not voice_client.is_connected():
            print("[discord_bot] VC未接続のため再生をスキップします。")
            return

        if voice_client.is_playing():
            voice_client.stop()

        loop = asyncio.get_running_loop()
        finished_event = asyncio.Event()

        def _after_playback(error: Exception | None) -> None:
            if error is not None:
                print(f"[discord_bot] 再生中にエラーが発生しました: {error}")
            loop.call_soon_threadsafe(finished_event.set)

        # 一時ファイル経由をやめ、メモリ上のWAVバイト列を直接ffmpegへパイプする。
        source = discord.FFmpegPCMAudio(
            io.BytesIO(wav_bytes),
            pipe=True,
            executable=self._settings.ffmpeg_path or "ffmpeg",
        )
        voice_client.play(source, after=_after_playback)
        timeout = self._settings.playback_timeout_seconds
        print(f"[discord_bot] 再生を開始しました(タイムアウト{timeout}秒)。")
        try:
            await asyncio.wait_for(finished_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print(
                f"[discord_bot] {timeout}秒応答なしのためタイムアウトしました。"
                "復旧を試みます。"
            )
            try:
                source.cleanup()
            except Exception as e:
                print(f"[discord_bot] 再生ソースのクリーンアップに失敗しました: {e}")
            try:
                voice_client.stop()
            except Exception as e:
                print(f"[discord_bot] 再生停止に失敗しました: {e}")
            raise
