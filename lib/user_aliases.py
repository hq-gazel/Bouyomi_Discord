"""Twitchユーザーの呼び方エイリアスをJSONファイルから読み込むモジュール。

エイリアス設定は個人の視聴者情報を含みうるため、`.env`とは別に
`cfg/user_aliases.json`(gitignore対象)として管理する。オプトイン機能
であるため、ファイルが存在しないこと自体はエラーにしない。
"""

from __future__ import annotations

import json
from pathlib import Path


def load_user_aliases(path: Path) -> dict[str, str]:
    """`path` のJSONファイルからユーザーエイリアス辞書を読み込む。

    ファイルが存在しない場合は空のdictを返す(オプトイン機能のため正常系)。
    JSON構文エラー、トップレベルがobjectでない、キーまたは値が文字列でない
    場合は、それぞれ区別できるメッセージ付きの RuntimeError を送出する。
    キーは `.lower()` して返す(Twitchのログイン名は小文字で照合するため)。
    """
    if not path.exists():
        return {}

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"ユーザーエイリアスファイル '{path}' の読み込みに失敗しました: {e}") from e

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"ユーザーエイリアスファイル '{path}' のJSON構文が不正です: {e}"
        ) from e

    if not isinstance(data, dict):
        # 設定エラーはRuntimeErrorに統一する方針のため、TypeErrorは使わない。
        raise RuntimeError(  # noqa: TRY004
            f"ユーザーエイリアスファイル '{path}' のトップレベルはobject(辞書)"
            "である必要があります。"
        )

    aliases: dict[str, str] = {}
    for key, value in data.items():
        is_valid_entry = isinstance(key, str) and isinstance(value, str)
        if not is_valid_entry:
            raise RuntimeError(
                f"ユーザーエイリアスファイル '{path}' のキーと値はすべて文字列で"
                f"ある必要があります(不正なエントリ: {key!r}: {value!r})。"
            )
        aliases[key.lower()] = value

    return aliases
