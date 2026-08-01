"""lib.ng_word_filter の load_ng_words / mask_ng_words の挙動を検証するユニットテスト。"""

from __future__ import annotations

from pathlib import Path

from lib.ng_word_filter import load_ng_words, mask_ng_words


def test_load_ng_words_returns_empty_list_when_file_missing(tmp_path: Path) -> None:
    """ファイルが存在しない場合は空listを返す(オプトイン機能のため正常系)。"""
    result = load_ng_words(tmp_path / "ng_words.txt")
    assert result == []


def test_load_ng_words_loads_valid_file(tmp_path: Path) -> None:
    """正常なtxtファイルからNGワードを読み込めること。"""
    path = tmp_path / "ng_words.txt"
    path.write_text("死ね\nバカ\n", encoding="utf-8")

    result = load_ng_words(path)

    assert result == ["死ね", "バカ"]


def test_load_ng_words_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    """コメント行(#始まり)と空行が無視されること。"""
    path = tmp_path / "ng_words.txt"
    path.write_text(
        "# コメント行\n死ね\n\nバカ\n# 別のコメント\n\n",
        encoding="utf-8",
    )

    result = load_ng_words(path)

    assert result == ["死ね", "バカ"]


def test_load_ng_words_strips_surrounding_whitespace(tmp_path: Path) -> None:
    """各行の前後の空白がstripされること。"""
    path = tmp_path / "ng_words.txt"
    path.write_text("  死ね  \n\tバカ\t\n", encoding="utf-8")

    result = load_ng_words(path)

    assert result == ["死ね", "バカ"]


def test_mask_ng_words_replaces_matched_words() -> None:
    """NGワードが伏字プレースホルダーに置換されること。"""
    result = mask_ng_words("お前なんか死ねばいいのに", ["死ね"])

    assert result == "お前なんかピーばいいのに"


def test_mask_ng_words_matches_case_insensitively() -> None:
    """大文字小文字を無視してマッチすること。"""
    result = mask_ng_words("あいつマジでdqnだわ", ["DQN"])

    assert result == "あいつマジでピーだわ"


def test_mask_ng_words_returns_normalized_text_when_no_match() -> None:
    """NGワードが含まれないテキストはプレースホルダー未挿入で返ること
    (ただしNFKC正規化により全角英数字は半角化される)。"""
    result = mask_ng_words("こんにちはABC123", ["死ね"])

    assert result == "こんにちはABC123"


def test_mask_ng_words_normalizes_fullwidth_characters() -> None:
    """全角英数字がNFKC正規化により半角化されること。"""
    result = mask_ng_words("ＡＢＣ１２３", [])

    assert result == "ABC123"


def test_mask_ng_words_does_nothing_when_ng_words_empty() -> None:
    """空リストならプレースホルダーが一切挿入されないこと。"""
    result = mask_ng_words("死ねばいいのに", [])

    assert result == "死ねばいいのに"
