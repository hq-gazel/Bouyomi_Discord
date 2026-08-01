"""読み上げコメント中のNGワードをテキストファイルから読み込み、伏字に置換するモジュール。

`cfg/ng_words.txt`(1行1語)はオプトイン機能であるため、ファイルが存在しない
こと自体はエラーにしない(`lib.user_aliases.load_user_aliases` と同じ設計)。
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def load_ng_words(path: Path) -> list[str]:
    """`path` のテキストファイルからNGワード一覧を読み込む。

    ファイルが存在しない場合は空のlistを返す(オプトイン機能のため正常系)。
    行ごとに `strip()` し、空行と `#` で始まる行(コメント)は無視する。
    重複は順序を維持したまま除去する。
    """
    if not path.exists():
        return []

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"NGワードファイル '{path}' の読み込みに失敗しました: {e}") from e

    ng_words: list[str] = []
    for line in raw_text.splitlines():
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        if word not in ng_words:
            ng_words.append(word)

    return ng_words


def mask_ng_words(text: str, ng_words: list[str], placeholder: str = "ピー") -> str:
    """`text` に含まれるNGワードを `placeholder` に置換する(部分一致・大文字小文字無視)。

    `text` および各NGワードは `unicodedata.normalize("NFKC", ...)` で正規化した
    上で比較・置換する(全角英数字と半角英数字の表記揺れなどを吸収するため)。
    """
    result = unicodedata.normalize("NFKC", text)

    for word in ng_words:
        normalized_word = unicodedata.normalize("NFKC", word)
        if not normalized_word:
            continue
        result = re.sub(re.escape(normalized_word), placeholder, result, flags=re.IGNORECASE)

    return result
