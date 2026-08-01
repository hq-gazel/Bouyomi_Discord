"""lib.user_aliases.load_user_aliases の挙動を検証するユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.user_aliases import load_user_aliases


def test_load_user_aliases_returns_empty_dict_when_file_missing(tmp_path: Path) -> None:
    """ファイルが存在しない場合は空dictを返す(オプトイン機能のため正常系)。"""
    result = load_user_aliases(tmp_path / "user_aliases.json")
    assert result == {}


def test_load_user_aliases_loads_and_lowercases_keys(tmp_path: Path) -> None:
    """正常なJSONを読み込み、キーが小文字化されて返ること。"""
    path = tmp_path / "user_aliases.json"
    path.write_text(
        '{"TwitchUser1": "ゆーざーいち", "another_login": "アナザー"}',
        encoding="utf-8",
    )

    result = load_user_aliases(path)

    assert result == {"twitchuser1": "ゆーざーいち", "another_login": "アナザー"}


def test_load_user_aliases_raises_on_json_syntax_error(tmp_path: Path) -> None:
    """JSON構文エラーの場合は RuntimeError になること。"""
    path = tmp_path / "user_aliases.json"
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_user_aliases(path)


def test_load_user_aliases_raises_when_top_level_is_not_object(tmp_path: Path) -> None:
    """トップレベルがobjectでない場合は RuntimeError になること。"""
    path = tmp_path / "user_aliases.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_user_aliases(path)


def test_load_user_aliases_raises_when_value_is_not_string(tmp_path: Path) -> None:
    """値が文字列でない場合は RuntimeError になること。"""
    path = tmp_path / "user_aliases.json"
    path.write_text('{"twitchuser1": 123}', encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_user_aliases(path)
