"""CommentQueueBridge の挙動を検証するユニットテスト。

いずれのテストも、万一デッドロックした場合にテストスイート全体が
ハングしないよう asyncio.wait_for でタイムアウトを設けている。
"""

from __future__ import annotations

import asyncio

import pytest

from lib.bridge import CommentQueueBridge

_TIMEOUT_SECONDS = 2.0


@pytest.mark.asyncio
async def test_wait_and_take_blocks_until_submit() -> None:
    """submit() されるまで wait_and_take() はブロックされ、
    submit() 後に正しいテキストが返ること。"""
    bridge = CommentQueueBridge()

    async def submit_after_delay() -> None:
        await asyncio.sleep(0.1)
        bridge.submit("hello")

    task = asyncio.create_task(submit_after_delay())

    result = await asyncio.wait_for(bridge.wait_and_take(), timeout=_TIMEOUT_SECONDS)

    assert result == "hello"
    await task


@pytest.mark.asyncio
async def test_wait_and_take_returns_all_submissions_in_order() -> None:
    """待機中に複数回 submit されても、破棄されず到着順(FIFO)に
    全件が返ること(キューイング保証の核心ロジック)。"""
    bridge = CommentQueueBridge()

    async def submit_multiple() -> None:
        bridge.submit("A")
        bridge.submit("B")
        bridge.submit("C")

    task = asyncio.create_task(submit_multiple())

    results = [
        await asyncio.wait_for(bridge.wait_and_take(), timeout=_TIMEOUT_SECONDS)
        for _ in range(3)
    ]

    assert results == ["A", "B", "C"]
    await task


@pytest.mark.asyncio
async def test_queue_is_empty_after_all_items_taken() -> None:
    """溜まっていた分を全件 take し終えた後、次に submit() されるまで
    再度 wait_and_take() がブロックされること。"""
    bridge = CommentQueueBridge()

    bridge.submit("first")
    first_result = await asyncio.wait_for(
        bridge.wait_and_take(), timeout=_TIMEOUT_SECONDS
    )
    assert first_result == "first"

    # キューが空になっているので、submit() が来るまでブロックされるはず
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bridge.wait_and_take(), timeout=0.2)

    # 改めて submit すれば、その値が取れること
    bridge.submit("second")
    second_result = await asyncio.wait_for(
        bridge.wait_and_take(), timeout=_TIMEOUT_SECONDS
    )
    assert second_result == "second"


@pytest.mark.asyncio
async def test_multiple_submit_take_cycles() -> None:
    """複数回の submit -> take のサイクルを繰り返しても正しく動作すること。"""
    bridge = CommentQueueBridge()

    for i in range(5):
        text = f"comment-{i}"
        bridge.submit(text)
        result = await asyncio.wait_for(
            bridge.wait_and_take(), timeout=_TIMEOUT_SECONDS
        )
        assert result == text
