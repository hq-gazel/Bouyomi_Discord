"""Twitchチャット受信BOT。

TwitchIO(2.x系, ext.commands.Bot)でTwitchチャンネルのチャットに接続し、
受信した全メッセージ(BOT自身の発言を除く)を CommentQueueBridge 経由で
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

from twitchio import Chatter, Message
from twitchio.ext import commands

from lib.bridge import CommentQueueBridge
from lib.config import Settings
from lib.ng_word_filter import mask_ng_words

# TwitchIOのcommands.Botはprefix引数を必須とするが、コマンド機能自体は
# 使わないため、ライブラリの要求を満たすためだけの固定値として扱う。
_UNUSED_COMMAND_PREFIX = "!"


def _resolve_display_name(
    user_aliases: dict[str, str], login: str, fallback_display_name: str
) -> str:
    """発言者の読み上げ名を解決する。

    `login`(小文字ログイン名)がエイリアス辞書に登録されていればそれを、
    未設定なら `fallback_display_name`(Twitchの表示名)を返す。
    """
    return user_aliases.get(login.lower(), fallback_display_name)


def _build_comment_text(template: str, username: str, comment: str) -> str:
    """テンプレート文字列にユーザー名・コメントを埋め込んで読み上げテキストを組み立てる。"""
    return template.format(username=username, comment=comment)


class _ChatRelayBot(commands.Bot):
    """全チャットメッセージをbridgeへ転送するTwitchIO Bot本体。"""

    def __init__(
        self,
        *,
        token: str,
        initial_channels: list[str],
        bridge: CommentQueueBridge,
        template: str,
        user_aliases: dict[str, str],
        ng_words: list[str],
    ) -> None:
        super().__init__(
            token=token,
            prefix=_UNUSED_COMMAND_PREFIX,
            initial_channels=initial_channels,
        )
        self._bridge = bridge
        self._template = template
        self._user_aliases = user_aliases
        self._ng_words = ng_words

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

        author = message.author
        if isinstance(author, Chatter) and author.name and author.display_name:
            username = _resolve_display_name(
                self._user_aliases, author.name, author.display_name
            )
            comment = mask_ng_words(message.content, self._ng_words)
            text = _build_comment_text(self._template, username, comment)
            print(f"[twitch_bot] コメント受信: {text!r}")
            self._bridge.submit(text)
            return

        comment = mask_ng_words(message.content, self._ng_words)
        print(f"[twitch_bot] コメント受信(発言者不明): {comment!r}")
        self._bridge.submit(comment)


class TwitchChatBot:
    """Twitchチャンネルのチャットを受信し、bridgeに流し込むBOT。"""

    def __init__(
        self,
        settings: Settings,
        bridge: CommentQueueBridge,
        user_aliases: dict[str, str],
        ng_words: list[str],
    ) -> None:
        self._settings = settings
        self._bridge = bridge
        self._user_aliases = user_aliases
        self._ng_words = ng_words
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
            template=self._settings.twitch_comment_template,
            user_aliases=self._user_aliases,
            ng_words=self._ng_words,
        )
        await self._client.start()

    async def shutdown(self) -> None:
        """TwitchIOのBotを安全にクローズする。"""
        if self._client is not None:
            await self._client.close()
