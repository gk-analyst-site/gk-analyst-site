"""既存の .md 原稿（STORY MINING STUDIO の出力など）を note 投稿用に解析する.

対応フォーマット:
- 1行目の `# タイトル` を記事タイトルとして取り出す
- 有料ラインの区切りは、次のいずれかを最初に見つけた位置とする:
    1) `<!-- PAYWALL -->`
    2) 単独行の `---`（STORY MINING STUDIO の結論後の区切り）
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedDoc:
    title: str
    body: str  # 有料ラインを含まない本文全体
    free_body: str | None = None  # 有料時: 無料パート
    paid_body: str | None = None  # 有料時: 有料パート

    @property
    def is_paid(self) -> bool:
        return self.paid_body is not None


_PAYWALL_MARKERS = ["<!-- PAYWALL -->"]


def parse(text: str, *, paid: bool) -> ParsedDoc:
    """.md 文字列を解析する.

    paid=True のとき、有料ラインで無料/有料パートに分割する。
    区切りが見つからなければ全文を無料パートとして扱い、呼び出し側に委ねる。
    """
    text = text.strip()

    # タイトル抽出（先頭の `# ...`）
    title = "無題"
    body = text
    m = re.match(r"^#\s+(.+?)\s*(?:\n|$)", text)
    if m:
        title = m.group(1).strip()
        body = text[m.end():].lstrip()

    if not paid:
        return ParsedDoc(title=title, body=body)

    # 有料ラインの位置を探す（明示マーカー優先、なければ最初の単独 `---`）
    split_at = -1
    marker_len = 0
    for marker in _PAYWALL_MARKERS:
        idx = body.find(marker)
        if idx != -1:
            split_at = idx
            marker_len = len(marker)
            break
    if split_at == -1:
        hr = re.search(r"^\s*---\s*$", body, flags=re.MULTILINE)
        if hr:
            split_at = hr.start()
            marker_len = hr.end() - hr.start()

    if split_at == -1:
        # 区切りが無い → 全文無料として返す（呼び出し側で警告）
        return ParsedDoc(title=title, body=body, free_body=body, paid_body="")

    free_body = body[:split_at].rstrip()
    paid_body = body[split_at + marker_len :].lstrip()
    return ParsedDoc(
        title=title,
        body=body,
        free_body=free_body,
        paid_body=paid_body,
    )
