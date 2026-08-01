"""環境変数を型変換付きで取得するヘルパー群。

lib.config(Bouyomi_Discord本体)と tts_server.py(別venv・別プロセス)の
両方から使われるため、**stdlibのみに依存**する(サードパーティ依存を持つと
tts_server.py側でimportできなくなるため)。tts_server.pyはcwd=プロジェクト
ルートで起動される前提のため、`from lib.env_utils import ...` でimportできる。
"""

from __future__ import annotations

import os


def get_raw(name: str) -> str:
    """環境変数を文字列として取得する(前後の空白は除去)。未設定なら空文字。"""
    return os.environ.get(name, "").strip()


def get_required(name: str) -> str:
    """必須環境変数を取得する。未設定または空文字ならエラー。"""
    value = get_raw(name)
    if not value:
        raise RuntimeError(
            f"環境変数 '{name}' が未設定です。.env ファイルに値を設定してください。"
        )
    return value


def get_optional(name: str) -> str | None:
    """任意環境変数を取得する。未設定または空文字なら None。"""
    value = get_raw(name)
    return value if value else None


def parse_int(name: str, value: str) -> int:
    """文字列を int に変換する。失敗時はどの変数が原因かが分かるエラーを送出。"""
    try:
        return int(value)
    except ValueError as e:
        raise RuntimeError(
            f"環境変数 '{name}' の値 '{value}' を整数に変換できません。"
        ) from e


def get_optional_int(name: str) -> int | None:
    value = get_optional(name)
    if value is None:
        return None
    return parse_int(name, value)


def get_float(name: str, default: float) -> float:
    value = get_raw(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as e:
        raise RuntimeError(
            f"環境変数 '{name}' の値 '{value}' を数値(float)に変換できません。"
        ) from e


def get_int(name: str, default: int) -> int:
    value = get_raw(name)
    if not value:
        return default
    return parse_int(name, value)


def get_bool(name: str, default: bool) -> bool:
    """環境変数を真偽値として取得する。未設定(空文字)なら default を返す。"""
    value = get_raw(name).lower()
    if not value:
        return default
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise RuntimeError(
        f"環境変数 '{name}' の値 '{value}' を真偽値に変換できません"
        "('true'/'false' 等を指定してください)。"
    )
