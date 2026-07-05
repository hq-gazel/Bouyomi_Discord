"""Twitchチャット受信BOT。

TwitchIO(2.x系, ext.commands.Bot)でTwitchチャンネルのチャットに接続し、
受信した全メッセージ(BOT自身の発言を除く)を LatestOnlyBridge 経由で
Discord側(TTS再生ループ)に橋渡しする。

TwitchIO 2.10.0(このプロジェクトにインストール済みのバージョン)を実機確認した
結果、`twitchio.ext.commands.Bot.__init__` は client_id や nick を引数として
受け取らない(`token`, `prefix`, `client_secret`, `initial_channels`,
`heartbeat`, `retain_cache` のみ)。client_id・login(nick)は接続時に
OAuthトークンを `https://id.twitch.tv/oauth2/validate` へ照会して自動的に
取得される仕組みになっているため、Settings.twitch_client_id /
twitch_bot_nick はこのBOTの接続処理では使用しない。
"""

from __future__ import annotations

from twitchio import Message
from twitchio.ext import commands

from lib.bridge import LatestOnlyBridge
from lib.config import Settings

# TwitchIOのcommands.Botはprefix引数を必須とするが、コマンド機能自体は
# 使わないため、ライブラリの要求を満たすためだけの固定値として扱う。
_UNUSED_COMMAND_PREFIX = "!"


class _ChatRelayBot(commands.Bot):
    """全チャットメッセージをbridgeへ転送するTwitchIO Bot本体。"""

    def __init__(
        self, *, token: str, initial_channels: list[str], bridge: LatestOnlyBridge
    ) -> None:
        super().__init__(
            token=token,
            prefix=_UNUSED_COMMAND_PREFIX,
            initial_channels=initial_channels,
        )
        self._bridge = bridge

    async def event_ready(self) -> None:
        """IRC認証・チャンネルJOINが完了した時点で呼ばれる。"""
        print(
            f"[twitch_bot] 接続完了: nick={self.nick} "
            f"joined_channels={[ch.name for ch in self.connected_channels]}"
        )

    async def event_message(self, message: Message) -> None:
        """PRIVMSG受信時に呼ばれる。BOT自身の発言(echo)は読み上げ対象から除外する。"""
        if message.echo:
            return
        if not message.content:
            return
        print(f"[twitch_bot] コメント受信: {message.content!r}")
        self._bridge.submit(message.content)


class TwitchChatBot:
    """Twitchチャンネルのチャットを受信し、bridgeに流し込むBOT。"""

    def __init__(self, settings: Settings, bridge: LatestOnlyBridge) -> None:
        self._settings = settings
        self._bridge = bridge
        # TwitchIOのClient.__init__はasyncio.get_event_loop()でその場の
        # イベントループを捕捉してしまうため、実行中のイベントループ上で
        # 呼ばれることが保証されている run() の中で初めて生成する。
        self._client: _ChatRelayBot | None = None

    async def run(self) -> None:
        """TwitchIOのBotを起動し、切断されるまでブロックする。"""
        self._client = _ChatRelayBot(
            token=self._settings.twitch_oauth_token,
            initial_channels=[self._settings.twitch_channel],
            bridge=self._bridge,
        )
        await self._client.start()

    async def shutdown(self) -> None:
        """TwitchIOのBotを安全にクローズする。"""
        if self._client is not None:
            await self._client.close()
