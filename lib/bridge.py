"""Twitchコメント受信とTTS再生の間を橋渡しするモジュール。

読み上げは「絶対にコメントを取りこぼさない」ことが要件のため、受信した
コメントは古いものから順に破棄せず全件キューイングし、到着順(FIFO)に
1件ずつ取り出せる `CommentQueueBridge` を提供する。

キューは無制限(上限なし)。合成・再生が詰まってコメントが積み上がっても
破棄は行わない(体感速度は別途、合成/再生のパイプライン化等で対応する)。
"""

from __future__ import annotations

import asyncio


class CommentQueueBridge:
    """受信したテキストを到着順に全件保持するFIFOキューのブリッジ。

    Producer側(Twitch BOT)は submit() で新しいコメントをキューへ積む。
    Consumer側(Discord BOT)は wait_and_take() でキューの先頭にある
    テキストを1件取り出す(キューが空の間はブロックする)。

    内部は asyncio.Queue(無制限)そのもので、複数producer/単一consumerの
    どちらも安全に扱える。
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def submit(self, text: str) -> None:
        """新しいテキストをキューの末尾に積む(同期メソッド、awaitしない)。

        asyncio.Queue.put_nowait() は上限なしキューに対しては即座に成功する
        (QueueFullが発生しない)ため、awaitを挟まずに呼び出せる。
        """
        self._queue.put_nowait(text)

    async def wait_and_take(self) -> str:
        """キューの先頭にあるテキストが現れるまで非同期に待機し、取り出して返す。

        到着順(FIFO)に1件ずつ取り出されるため、待機中に複数回 submit()
        されても、それらは破棄されずすべて後続の呼び出しで順番に返る。
        """
        return await self._queue.get()
