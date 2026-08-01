"""lib.ng_word_filter の load_ng_words / NgWordMasker の挙動を検証するユニットテスト。"""

from __future__ import annotations

from pathlib import Path

from lib.ng_word_filter import NgWordMasker, load_ng_words, mask_urls_and_emails


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


def test_load_ng_words_deduplicates_preserving_order(tmp_path: Path) -> None:
    """重複するNGワードは順序を維持したまま除去されること。"""
    path = tmp_path / "ng_words.txt"
    path.write_text("死ね\nバカ\n死ね\n", encoding="utf-8")

    result = load_ng_words(path)

    assert result == ["死ね", "バカ"]


def test_mask_replaces_matched_words() -> None:
    """NGワードが伏字プレースホルダーに置換されること。"""
    result = NgWordMasker(["死ね"]).mask("お前なんか死ねばいいのに")

    assert result == "お前なんかピーばいいのに"


def test_mask_matches_case_insensitively() -> None:
    """大文字小文字を無視してマッチすること。"""
    result = NgWordMasker(["DQN"]).mask("あいつマジでdqnだわ")

    assert result == "あいつマジでピーだわ"


def test_mask_returns_normalized_text_when_no_match() -> None:
    """NGワードが含まれないテキストはプレースホルダー未挿入で返ること
    (ただしNFKC正規化により全角英数字は半角化される)。"""
    result = NgWordMasker(["死ね"]).mask("こんにちはABC123")

    assert result == "こんにちはABC123"


def test_mask_normalizes_fullwidth_characters() -> None:
    """全角英数字がNFKC正規化により半角化されること。"""
    result = NgWordMasker([]).mask("ＡＢＣ１２３")

    assert result == "ABC123"


def test_mask_does_nothing_when_ng_words_empty() -> None:
    """空リストならプレースホルダーが一切挿入されないこと。"""
    result = NgWordMasker([]).mask("死ねばいいのに")

    assert result == "死ねばいいのに"


def test_mask_skips_empty_ng_word() -> None:
    """空文字のNGワードが混じっていてもエラーにならず無視されること。"""
    result = NgWordMasker(["", "死ね"]).mask("死ねばいいのに")

    assert result == "ピーばいいのに"


def test_mask_prefers_longer_word_match() -> None:
    """短い語と長い語が両方登録されている場合、長い語優先でマッチすること。"""
    result = NgWordMasker(["死ね", "死ねばいい"]).mask("死ねばいいのに")

    assert result == "ピーのに"


def test_mask_urls_and_emails_replaces_https_url() -> None:
    """`https://`で始まるURLが`URL省略`に置換されること。"""
    result = mask_urls_and_emails("見て https://example.com/page です")

    assert result == "見て URL省略 です"


def test_mask_urls_and_emails_replaces_www_url_without_scheme() -> None:
    """スキームなしの`www.`始まりURLが`URL省略`に置換されること。"""
    result = mask_urls_and_emails("見て www.example.com/page です")

    assert result == "見て URL省略 です"


def test_mask_urls_and_emails_replaces_email_address() -> None:
    """メールアドレスが`メールアドレス省略`に置換されること。"""
    result = mask_urls_and_emails("連絡先は test@example.com です")

    assert result == "連絡先は メールアドレス省略 です"


def test_mask_urls_and_emails_replaces_both_url_and_email() -> None:
    """1つのテキストにURLとメールアドレス両方が含まれる場合、両方とも置換されること。"""
    result = mask_urls_and_emails(
        "サイトは https://example.com/page 、連絡先は test@example.com です"
    )

    assert result == "サイトは URL省略 、連絡先は メールアドレス省略 です"


def test_mask_urls_and_emails_does_not_double_process_at_sign_in_url() -> None:
    """URL中に`@`を含む場合、メールアドレス側の正規表現に二重処理されないこと。"""
    result = mask_urls_and_emails("これ http://user@example.com/path を見て")

    assert result == "これ URL省略 を見て"


def test_mask_urls_and_emails_returns_unchanged_text_without_url_or_email() -> None:
    """URL・メールアドレスを含まないテキストは無変化で返ること。"""
    result = mask_urls_and_emails("こんにちは、元気ですか?")

    assert result == "こんにちは、元気ですか?"
