"""TTSサイドカーサーバー(tts_server.py)を呼び出す非同期HTTPクライアント。

Bouyomi_Discordのvenv側(discord bot等)から、別プロセスで動くIrodori-TTS
サイドカーサーバーにHTTP経由でアクセスするためのクライアント。
"""

from __future__ import annotations

import asyncio

import httpx

# 音声合成は数秒〜数十秒かかりうるため、余裕を持ったタイムアウトを設定する。
_SYNTHESIZE_TIMEOUT_SECONDS = 60.0
# ヘルスチェックは軽量なので短めのタイムアウトで十分。
_HEALTH_CHECK_TIMEOUT_SECONDS = 5.0


class TtsClient:
    """TTSサイドカーサーバーへのHTTPクライアント。"""

    def __init__(self, host: str, port: int) -> None:
        self._base_url = f"http://{host}:{port}"

    async def synthesize(self, text: str) -> bytes:
        """POST /synthesize を呼び出し、WAVバイト列を返す。

        非200応答やタイムアウト時は分かりやすいメッセージ付きのRuntimeErrorを
        送出する。
        """
        try:
            async with httpx.AsyncClient(timeout=_SYNTHESIZE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self._base_url}/synthesize", json={"text": text}
                )
        except httpx.TimeoutException as e:
            raise RuntimeError(
                f"TTSサーバーへのsynthesizeリクエストがタイムアウトしました: {self._base_url}"
            ) from e
        except httpx.RequestError as e:
            raise RuntimeError(
                f"TTSサーバーへの接続に失敗しました: {self._base_url} ({e})"
            ) from e

        if response.status_code != 200:
            raise RuntimeError(
                f"TTSサーバーがエラーを返しました(status={response.status_code}): "
                f"{response.text}"
            )
        return response.content

    async def wait_until_healthy(self, timeout: float = 120.0, interval: float = 1.0) -> None:
        """GET /health を timeout秒に達するまで interval秒間隔でポーリングする。

        healthyにならないまま timeout に達したら TimeoutError を送出する。
        サーバー起動途中の接続拒否も許容してリトライを続ける。
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        async with httpx.AsyncClient(timeout=_HEALTH_CHECK_TIMEOUT_SECONDS) as client:
            while True:
                try:
                    response = await client.get(f"{self._base_url}/health")
                    if response.status_code == 200:
                        return
                except httpx.RequestError:
                    # サーバー起動途中の接続拒否等は許容してリトライを続ける。
                    pass

                if loop.time() >= deadline:
                    raise TimeoutError(
                        f"TTSサーバーが{timeout}秒以内にhealthyになりませんでした: "
                        f"{self._base_url}"
                    )
                await asyncio.sleep(interval)
