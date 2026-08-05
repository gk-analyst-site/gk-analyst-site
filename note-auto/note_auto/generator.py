"""Claude API を使って note 記事を自動生成するモジュール."""

from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic

# モデルは環境変数で上書き可能。未指定なら最新の Opus。
DEFAULT_MODEL = os.environ.get("NOTE_AUTO_MODEL", "claude-opus-5")


@dataclass
class Article:
    """生成された記事。"""

    title: str
    body: str
    # 有料noteのとき、無料で読める導入パートの末尾位置（本文中の文字インデックス）。
    # None のときは有料ライン未設定（全文無料）。
    paywall_index: int | None = None
    tags: list[str] | None = None


def _build_system_prompt(cfg: dict) -> str:
    author = cfg["author"]
    article = cfg["article"]
    lines = [
        f"あなたは note のプロのライターであり、{author['role']}本人として記事を書きます。",
        "",
        "# 発信者の人物像",
        author["persona"].strip(),
        "",
        "# 執筆ルール",
        f"- 言語: 日本語で書く。",
        f"- 本文の長さの目安: {article['min_chars']}〜{article['max_chars']}文字。",
        "- 読者は指導者・選手・保護者・クラブ関係者。専門的だが平易に。",
        "- 見出し（##）を使って構造化し、具体例や実践的な示唆を入れる。",
        "- 一般論の羅列ではなく、この発信者ならではの視点・経験を感じさせる。",
        "- 誇張・断定しすぎない。読者の学びになることを最優先にする。",
        "- 記事の最後に、次の一文を自然な形で織り込んで導線を作る:",
        f"  「{article['call_to_action'].strip()}」",
    ]
    return "\n".join(lines)


def _build_user_prompt(topic: dict, cfg: dict) -> str:
    sale = cfg["sale"]
    parts = [
        f"次のテーマで note 記事を1本書いてください。",
        "",
        f"## テーマ案\n{topic['title']}",
        "",
        f"## 盛り込みたい内容\n{topic.get('brief', '').strip()}",
    ]
    if sale.get("enabled"):
        parts += [
            "",
            "## 有料note構成の指定",
            f"この記事は有料note（{sale['price']}円）として販売します。",
            f"冒頭から約{sale['free_intro_chars']}文字を『無料で読める導入パート』とし、"
            "読者が続きを読みたくなる所で区切ってください。",
            "無料パートの終わりに、区切り記号として本文中に単独行で "
            "`<!-- PAYWALL -->` を1回だけ入れてください。"
            "それ以降が有料パート（本編）になります。",
        ]
    return "\n".join(parts)


def _split_paywall(body: str) -> tuple[str, int | None]:
    """本文中の `<!-- PAYWALL -->` マーカーを取り除き、その位置を返す."""
    marker = "<!-- PAYWALL -->"
    idx = body.find(marker)
    if idx == -1:
        return body, None
    cleaned = (body[:idx].rstrip() + "\n\n" + body[idx + len(marker):].lstrip())
    # マーカーより前の文字数を有料ライン位置とする
    return cleaned, len(body[:idx].rstrip())


def generate(topic: dict, cfg: dict, *, client: anthropic.Anthropic | None = None) -> Article:
    """1件のトピックから記事を生成して返す."""
    client = client or anthropic.Anthropic()
    system = _build_system_prompt(cfg)
    user = _build_user_prompt(topic, cfg)

    # 出力が長くなり得るのでストリーミングで受ける（HTTP タイムアウト回避）。
    with client.messages.stream(
        model=DEFAULT_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError("記事生成がモデルに拒否されました（内容を見直してください）。")

    text = "".join(b.text for b in message.content if b.type == "text").strip()

    # 1行目を見出し（# ...）として使えるなら抜き出し、タイトルにする。
    title = topic["title"]
    body = text
    if text.startswith("# "):
        first_nl = text.find("\n")
        title = text[2:first_nl].strip() if first_nl != -1 else text[2:].strip()
        body = text[first_nl + 1 :].lstrip() if first_nl != -1 else ""

    paywall_index = None
    if cfg["sale"].get("enabled"):
        body, paywall_index = _split_paywall(body)

    return Article(
        title=title,
        body=body,
        paywall_index=paywall_index,
        tags=cfg["article"].get("default_tags", []),
    )
