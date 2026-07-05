"""Twitchコメント受信とTTS再生の間を橋渡しするモジュール。

Twitchチャットは高頻度でコメントが流れることがあるため、単純なFIFOキューで
全コメントを溜め込むと、読み上げ(TTS合成+Discord再生)が詰まっている間に
未処理コメントがどんどん積み上がり、配信からどんどん遅延した内容を延々と
読み上げ続けることになってしまう。

これを避けるため、保留中のコメントは常に最新の1件だけを保持し、古い未処理
コメントは破棄する `LatestOnlyBridge` を提供する。
"""

from __future__ import annotations

import asyncio


class LatestOnlyBridge:
    """保留スロットに常に最新1件のテキストだけを保持するブリッジ。

    Producer側(Twitch BOT)は submit() で新しいコメントを積む。
    Consumer側(Discord BOT)は wait_and_take() で「次に読み上げるべき最新の
    コメント」を1件取り出す(取り出すまでブロックする)。

    consumer は単一(wait_and_take() を同時に複数箇所から呼ばない)前提の
    シンプルな実装。
    """

    def __init__(self) -> None:
        self._pending_text: str | None = None
        self._event = asyncio.Event()

    def submit(self, text: str) -> None:
        """新しいテキストを保留スロットにセットする(同期メソッド、awaitしない)。

        既に未取得のテキストが保留中であれば、それを上書き(破棄)して
        新しいテキストに置き換える。asyncioのイベントループが動いている
        コンテキストから呼ばれる想定。

        単一変数への代入と Event.set() のみなので、asyncio のシングル
        スレッドイベントループ上では await を挟まない限り他のコルーチンに
        制御が渡らず、ロックは不要。
        """
        self._pending_text = text
        self._event.set()

    async def wait_and_take(self) -> str:
        """保留中のテキストが現れるまで非同期に待機し、取り出して返す。

        取り出した後は保留スロットをクリアするため、呼び出し中に複数回
        submit() されても、実際に take される時点で保留されている最新の
        1件だけが返る。
        """
        await self._event.wait()
        text = self._pending_text
        assert text is not None
        self._pending_text = None
        self._event.clear()
        return text
