"""note 自動投稿システムのエントリーポイント（CLI）.

使い方:
  # 1件生成してプレビュー表示（投稿しない）
  python -m note_auto.main preview

  # 生成した記事をファイルに書き出す（out/ ディレクトリ）
  python -m note_auto.main generate

  # 生成 → note へ投稿（config.yaml の publish.mode に従う）
  python -m note_auto.main run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import generator

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
TOPICS_PATH = ROOT / "topics.yaml"
OUT_DIR = ROOT / "out"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_topics(data: dict) -> None:
    with TOPICS_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _pending_topics(topics_data: dict) -> list[dict]:
    return [t for t in topics_data.get("topics", []) if t.get("status") != "posted"]


def _article_to_markdown(article: generator.Article) -> str:
    lines = [f"# {article.title}", ""]
    if article.paywall_index is not None:
        head = article.body[: article.paywall_index]
        tail = article.body[article.paywall_index :]
        lines += [head, "", "----（ここから有料）----", "", tail]
    else:
        lines.append(article.body)
    if article.tags:
        lines += ["", "タグ: " + " ".join(f"#{t}" for t in article.tags)]
    return "\n".join(lines)


def cmd_preview(cfg: dict, topics_data: dict) -> int:
    pending = _pending_topics(topics_data)
    if not pending:
        print("未投稿のトピックがありません。topics.yaml に追加してください。")
        return 1
    article = generator.generate(pending[0], cfg)
    print("=" * 60)
    print(_article_to_markdown(article))
    print("=" * 60)
    return 0


def cmd_generate(cfg: dict, topics_data: dict) -> int:
    pending = _pending_topics(topics_data)
    if not pending:
        print("未投稿のトピックがありません。")
        return 1
    OUT_DIR.mkdir(exist_ok=True)
    limit = cfg["publish"].get("max_per_run", 1)
    for topic in pending[:limit]:
        article = generator.generate(topic, cfg)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe = "".join(c for c in article.title if c.isalnum() or c in " 　-_")[:40].strip()
        path = OUT_DIR / f"{stamp}_{safe}.md"
        path.write_text(_article_to_markdown(article), encoding="utf-8")
        print(f"生成しました: {path}")
    return 0


def cmd_run(cfg: dict, topics_data: dict) -> int:
    # publisher は Playwright に依存するので、実行時にだけ import する。
    from . import publisher

    pending = _pending_topics(topics_data)
    if not pending:
        print("未投稿のトピックがありません。")
        return 1

    limit = cfg["publish"].get("max_per_run", 1)
    mode = cfg["publish"].get("mode", "draft")

    for topic in pending[:limit]:
        print(f"生成中: {topic['title']}")
        article = generator.generate(topic, cfg)

        # 有料note設定が有効で、有料ラインが生成されている場合は
        # 無料パート／有料パートに分割し、価格つきで投稿する。
        if cfg["sale"].get("enabled") and article.paywall_index is not None:
            free_body = article.body[: article.paywall_index].rstrip()
            paid_body = article.body[article.paywall_index :].lstrip()
            price = int(cfg["sale"]["price"])
            print(f"投稿中（有料 {price}円 / mode={mode}）...")
            publisher.publish(
                article.title,
                free_body,
                paid_body=paid_body,
                price=price,
                mode=mode,
            )
        else:
            print(f"投稿中（無料 / mode={mode}）...")
            publisher.publish(article.title, article.body, mode=mode)

        # 投稿できたら topics.yaml のステータスを更新
        topic["status"] = "posted"
        _save_topics(topics_data)
        print(f"完了: {topic['title']}")

    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="note 自動投稿システム")
    parser.add_argument(
        "command",
        choices=["preview", "generate", "run"],
        help="preview: 生成して表示 / generate: ファイル出力 / run: note へ投稿",
    )
    args = parser.parse_args(argv)

    cfg = _load_yaml(CONFIG_PATH)
    topics_data = _load_yaml(TOPICS_PATH)

    if args.command == "preview":
        return cmd_preview(cfg, topics_data)
    if args.command == "generate":
        return cmd_generate(cfg, topics_data)
    if args.command == "run":
        return cmd_run(cfg, topics_data)
    return 1


if __name__ == "__main__":
    sys.exit(main())
