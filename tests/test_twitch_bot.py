"""lib.twitch_bot のpure関数(_resolve_display_name / _build_comment_text)を
検証するユニットテスト。twitchioの実オブジェクトなしで検証できる。
"""

from __future__ import annotations

from lib.twitch_bot import _build_comment_text, _resolve_display_name


def test_resolve_display_name_uses_alias_when_registered() -> None:
    """ログイン名がエイリアス辞書に登録されている場合、エイリアスを返すこと。"""
    aliases = {"twitchuser1": "ゆーざーいち"}

    result = _resolve_display_name(aliases, "twitchuser1", "TwitchUser1")

    assert result == "ゆーざーいち"


def test_resolve_display_name_falls_back_to_display_name_when_not_registered() -> None:
    """エイリアス未登録の場合、fallback_display_nameを返すこと。"""
    aliases: dict[str, str] = {}

    result = _resolve_display_name(aliases, "someuser", "SomeUser")

    assert result == "SomeUser"


def test_resolve_display_name_matches_login_case_insensitively() -> None:
    """ログイン名の大文字小文字にかかわらずエイリアスが解決されること
    (エイリアス辞書のキーは小文字化されている前提)。"""
    aliases = {"twitchuser1": "ゆーざーいち"}

    result = _resolve_display_name(aliases, "TwitchUser1", "TwitchUser1")

    assert result == "ゆーざーいち"


def test_build_comment_text_formats_template() -> None:
    """テンプレートにusername/commentが正しく埋め込まれること。"""
    result = _build_comment_text("{username}さん、{comment}", "ゆーざーいち", "こんにちは")

    assert result == "ゆーざーいちさん、こんにちは"


def test_build_comment_text_allows_custom_order_and_wording() -> None:
    """語順や敬称を変えたテンプレートでも正しく整形されること。"""
    result = _build_comment_text(
        "{username} からのコメント: {comment}", "テストユーザー", "やっほー"
    )

    assert result == "テストユーザー からのコメント: やっほー"
