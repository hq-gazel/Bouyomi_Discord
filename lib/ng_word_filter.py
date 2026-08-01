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

    words = (
        line.strip()
        for line in raw_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    # dict.fromkeys()はO(n)で順序を維持したまま重複除去できる。
    return list(dict.fromkeys(words))


class NgWordMasker:
    """NGワード一覧を事前コンパイルし、テキストへの伏字置換を高速に行うクラス。

    コメント1件ごとに全NGワードを正規化・再コンパイルしていた旧実装
    (`mask_ng_words`)に対し、構築時に1本の正規表現へまとめておくことで
    `mask()` 呼び出しのたびの再コンパイルコストを排除する。
    """

    def __init__(self, ng_words: list[str], placeholder: str = "ピー") -> None:
        self._placeholder = placeholder
        self._pattern: re.Pattern[str] | None = self._build_pattern(ng_words)

    @staticmethod
    def _build_pattern(ng_words: list[str]) -> re.Pattern[str] | None:
        normalized_words = [
            unicodedata.normalize("NFKC", word) for word in ng_words if word
        ]
        normalized_words = [word for word in normalized_words if word]
        if not normalized_words:
            return None

        # 長い語を優先してマッチさせるため、長さ降順に並べてから`|`結合する
        # (例: "死ね"と"死ねばいい"が両方登録されていた場合の部分一致順序対策)。
        normalized_words.sort(key=len, reverse=True)
        combined = "|".join(re.escape(word) for word in normalized_words)
        return re.compile(combined, flags=re.IGNORECASE)

    def mask(self, text: str) -> str:
        """`text` に含まれるNGワードを伏字プレースホルダーに置換する(部分一致・大文字小文字無視)。

        `text` は `unicodedata.normalize("NFKC", ...)` で正規化した上で比較・
        置換する(全角英数字と半角英数字の表記揺れなどを吸収するため)。
        NGワードが0件の場合もNFKC正規化したtextを返す(現行挙動と同じ)。
        """
        normalized_text = unicodedata.normalize("NFKC", text)
        if self._pattern is None:
            return normalized_text
        return self._pattern.sub(self._placeholder, normalized_text)
