"""note 自動投稿システムのエントリーポイント（CLI）.

使い方:
  # 1件生成してプレビュー表示（投稿しない）
  python -m note_auto.main preview

  # 生成した記事をファイルに書き出す（out/ ディレクトリ）
  python -m note_auto.main generate

  # 生成 → note へ投稿（config.yaml の publish.mode に従う）
  python -m note_auto.main run

  # 既存の .md 原稿（STORY MINING STUDIO の出力など）を note へ投稿
  python -m note_auto.main publish-file 原稿.md --paid --price 9800 --publish
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

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
    from . import generator

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
    from . import generator

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
    # generator は anthropic、publisher は Playwright に依存するので実行時に import。
    from . import generator, publisher

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


def cmd_publish_file(cfg: dict, args) -> int:
    """既存の .md 原稿（STORY MINING STUDIO の出力など）を note に投稿する."""
    from . import mdfile

    path = Path(args.path)
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        return 1

    paid = args.paid or cfg["sale"].get("enabled", False)
    doc = mdfile.parse(path.read_text(encoding="utf-8"), paid=paid)
    mode = "publish" if args.publish else cfg["publish"].get("mode", "draft")
    is_paid = paid and doc.is_paid and bool(doc.paid_body)
    price = int(args.price if args.price else cfg["sale"]["price"]) if is_paid else None

    # --dry-run: ブラウザを起動せず、投稿内容の解析結果だけ表示する
    if args.dry_run:
        print("=" * 60)
        print("[DRY RUN] 実際の投稿は行いません。解析結果を表示します。")
        print(f"タイトル : {doc.title}")
        print(f"投稿モード: {mode}（publish=公開 / draft=下書き）")
        if is_paid:
            print(f"販売    : 有料 {price}円")
            print(f"無料パート: {len(doc.free_body or '')}字")
            print(f"有料パート: {len(doc.paid_body or '')}字")
            print("-" * 60)
            print("【無料パート 末尾（有料ラインの直前）】")
            print((doc.free_body or "")[-200:])
            print("-" * 60)
            print("【有料パート 冒頭】")
            print((doc.paid_body or "")[:200])
        else:
            if paid:
                print("販売    : 有料指定だが有料ライン未検出 → 無料扱い")
            else:
                print("販売    : 無料")
            print(f"本文    : {len(doc.body)}字")
        print("=" * 60)
        return 0

    from . import publisher

    print(f"タイトル: {doc.title}")
    if is_paid:
        print(f"投稿中（有料 {price}円 / mode={mode}）...")
        publisher.publish(
            doc.title,
            doc.free_body or "",
            paid_body=doc.paid_body,
            price=price,
            mode=mode,
        )
    else:
        if paid:
            print(
                "※ 有料指定ですが本文に有料ライン（<!-- PAYWALL --> か 単独行の ---）が"
                "見つかりませんでした。無料の下書きとして投稿します。"
            )
        print(f"投稿中（無料 / mode={mode}）...")
        publisher.publish(doc.title, doc.body, mode=mode)
    print("完了。note の下書き/記事一覧で確認してください。")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="note 自動投稿システム")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preview", help="トピックから1件生成して表示（投稿しない）")
    sub.add_parser("generate", help="生成して out/ にファイル出力（投稿しない）")
    sub.add_parser("run", help="トピックから生成して note へ投稿")

    pf = sub.add_parser(
        "publish-file", help="既存の .md 原稿を note へ投稿（STORY MINING STUDIO 連携）"
    )
    pf.add_argument("path", help="投稿する .md ファイルのパス")
    pf.add_argument("--paid", action="store_true", help="有料noteとして投稿する")
    pf.add_argument("--price", type=int, default=None, help="価格（円）。未指定なら config の値")
    pf.add_argument("--publish", action="store_true", help="下書きでなく公開まで行う")
    pf.add_argument(
        "--dry-run",
        action="store_true",
        help="投稿せず、解析結果（タイトル/有料ライン/価格）だけ表示する",
    )

    args = parser.parse_args(argv)

    cfg = _load_yaml(CONFIG_PATH)

    if args.command == "publish-file":
        return cmd_publish_file(cfg, args)

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
