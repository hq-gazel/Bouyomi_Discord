"""lib.config の _validate_template_placeholders の挙動を検証するユニットテスト。"""

from __future__ import annotations

import pytest

from lib.config import _validate_template_placeholders

_ALLOWED = frozenset({"username", "comment"})


def test_validate_template_placeholders_accepts_allowed_placeholders() -> None:
    """許可されたプレースホルダーのみのテンプレートはエラーにならないこと。"""
    _validate_template_placeholders(
        "TWITCH_COMMENT_TEMPLATE", "{username}さん、{comment}", _ALLOWED
    )


def test_validate_template_placeholders_accepts_no_placeholder() -> None:
    """プレースホルダーを含まないテンプレートもエラーにならないこと。"""
    _validate_template_placeholders("TWITCH_COMMENT_TEMPLATE", "固定文言", _ALLOWED)


def test_validate_template_placeholders_rejects_unknown_placeholder() -> None:
    """許可リスト外のプレースホルダーは RuntimeError になること。"""
    with pytest.raises(RuntimeError, match="unknown"):
        _validate_template_placeholders(
            "TWITCH_COMMENT_TEMPLATE", "{unknown}さん、{comment}", _ALLOWED
        )


def test_validate_template_placeholders_rejects_attribute_access() -> None:
    """属性アクセス({username.foo})は許可リストと完全一致しないため弾かれること。"""
    with pytest.raises(RuntimeError):
        _validate_template_placeholders(
            "TWITCH_COMMENT_TEMPLATE", "{username.foo}", _ALLOWED
        )


def test_validate_template_placeholders_rejects_empty_field_name() -> None:
    """空フィールド名({})は弾かれること。"""
    with pytest.raises(RuntimeError):
        _validate_template_placeholders("TWITCH_COMMENT_TEMPLATE", "{}", _ALLOWED)
