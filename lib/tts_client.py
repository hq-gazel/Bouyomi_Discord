"""TTSサイドカーサーバー(tts_server.py)を呼び出す非同期HTTPクライアント。

Bouyomi_Discordのvenv側(discord bot等)から、別プロセスで動くIrodori-TTS
サイドカーサーバーにHTTP経由でアクセスするためのクライアント。
"""

from __future__ import annotations

import asyncio

import httpx


class TtsClient:
    """TTSサイドカーサーバーへのHTTPクライアント。

    httpx.AsyncClient(≒コネクション)は呼び出しごとに作り直さず、
    インスタンス生成時に1つだけ保持して使い回す(接続確立コストの削減)。
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        synthesize_timeout_seconds: float = 60.0,
        health_check_timeout_seconds: float = 5.0,
    ) -> None:
        self._base_url = f"http://{host}:{port}"
        # 音声合成は数秒〜数十秒かかりうるため、余裕を持ったタイムアウトを設定する。
        self._synthesize_timeout_seconds = synthesize_timeout_seconds
        # ヘルスチェックは軽量なので短めのタイムアウトで十分。
        self._health_check_timeout_seconds = health_check_timeout_seconds
        self._client = httpx.AsyncClient(timeout=self._synthesize_timeout_seconds)

    async def synthesize(self, text: str) -> bytes:
        """POST /synthesize を呼び出し、WAVバイト列を返す。

        非200応答やタイムアウト時は分かりやすいメッセージ付きのRuntimeErrorを
        送出する。
        """
        try:
            response = await self._client.post(
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

    async def shutdown(self) -> None:
        """POST /shutdown を呼び出し、TTSサーバー側のクリーンアップを完了させる。

        WindowsではPopen.terminate()/kill()が猶予なく即死させるため、強制終了
        前にこれを呼んでlifespanのシャットダウンフック相当の処理を実行させる。
        サーバーが既に停止/未起動の場合の接続エラーは無視して安全に呼べる。
        呼び出し後、保持していたhttpx.AsyncClientをクローズする。
        """
        try:
            await self._client.post(
                f"{self._base_url}/shutdown", timeout=self._health_check_timeout_seconds
            )
        except httpx.RequestError:
            pass
        finally:
            await self._client.aclose()

    async def wait_until_healthy(self, timeout: float = 120.0, interval: float = 1.0) -> None:
        """GET /health を timeout秒に達するまで interval秒間隔でポーリングする。

        healthyにならないまま timeout に達したら TimeoutError を送出する。
        サーバー起動途中の接続拒否も許容してリトライを続ける。
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            try:
                response = await self._client.get(
                    f"{self._base_url}/health", timeout=self._health_check_timeout_seconds
                )
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
