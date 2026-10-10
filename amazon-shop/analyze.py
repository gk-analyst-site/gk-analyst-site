#!/usr/bin/env python3
"""Amazonのお店の「成績表(ビジネスレポートCSV)」を読んで、
どこを直せば売上が上がるかを自動で判定するプログラム。

使い方:
  1. セラーセントラル > レポート > ビジネスレポート >
     「(子)商品別詳細ページ 売上・トラフィック」をCSVでダウンロード
  2. amazon-shop/data/ に「2026-10-10.csv」のように日付の名前で置く
  3. python3 amazon-shop/analyze.py
  -> amazon-shop/output/report.html / todo.md / summary.json ができる

data/ にCSVが2つ以上あると、いちばん新しいものと1つ前のものを比べます。
CSVが1つも無いときは sample/ のお試しデータで動きます。
"""

import csv
import html
import json
import re
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
SAMPLE_DIR = BASE / "sample"
OUT_DIR = BASE / "output"
JST = timezone(timedelta(hours=9))

# 判定のしきい値（お店に合わせて変えてOK）
BUYBOX_OK = 90.0        # カート獲得率がこれ未満なら「カートを取られている」
CVR_LOW_RATIO = 0.6     # お店平均のCVRの何倍未満なら「買われにくいページ」
CVR_HIGH_RATIO = 1.3    # お店平均のCVRの何倍以上なら「買われやすいページ」
TRAFFIC_TOP = 0.7       # セッション数が上位何%の位置以上なら「人がよく来ている」

# CSVの列名は日本語版/英語版で違うので、キーワードで探す
COLUMNS = {
    "parent": [["親", "asin"], ["parent", "asin"]],
    "asin": [["子", "asin"], ["child", "asin"], ["asin"]],
    "title": [["タイトル"], ["商品名"], ["title"]],
    "sku": [["sku"]],
    "sessions": [["セッション", "合計"], ["sessions", "total"], ["セッション"], ["sessions"]],
    "pageviews": [["ページビュー", "合計"], ["page views", "total"], ["ページビュー"], ["page views"]],
    "buybox": [["カート"], ["おすすめ出品"], ["buy box"], ["featured offer"]],
    "units": [["注文された商品点数"], ["注文商品点数"], ["units ordered"]],
    "sales": [["売上"], ["ordered product sales"], ["sales"]],
    "orders": [["注文品目"], ["total order items"]],
}
# ↑「率」「b2b」が付いた列は別物なので除外する
EXCLUDE = ["率", "percentage", "b2b"]


def find_columns(header):
    lower = [h.strip().lower() for h in header]
    found = {}
    for key, patterns in COLUMNS.items():
        for words in patterns:
            for i, h in enumerate(lower):
                if i in found.values():
                    continue
                if key not in ("buybox",) and any(x in h for x in EXCLUDE):
                    continue
                if all(w in h for w in words):
                    found[key] = i
                    break
            if key in found:
                break
    return found


def num(text):
    """「￥1,234」「12.5%」「1,000」などを数字にする"""
    if text is None:
        return 0.0
    s = re.sub(r"[^\d.\-]", "", str(text))
    try:
        return float(s) if s not in ("", ".", "-") else 0.0
    except ValueError:
        return 0.0


def read_csv(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp932", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.reader(text.splitlines()))
    header, body = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]
    col = find_columns(header)
    missing = [k for k in ("asin", "sessions", "units", "sales") if k not in col]
    if missing:
        raise SystemExit(f"{path.name}: 必要な列が見つかりません {missing}\n列名: {header}")

    items = {}
    for r in body:
        get = lambda k: r[col[k]] if k in col and col[k] < len(r) else ""
        asin = get("asin").strip()
        if not asin:
            continue
        it = items.setdefault(asin, {
            "asin": asin, "title": get("title").strip(), "sku": get("sku").strip(),
            "sessions": 0.0, "pageviews": 0.0, "units": 0.0, "sales": 0.0,
            "orders": 0.0, "buybox": None,
        })
        for k in ("sessions", "pageviews", "units", "sales", "orders"):
            it[k] += num(get(k))
        if "buybox" in col and get("buybox").strip():
            it["buybox"] = num(get("buybox"))
    for it in items.values():
        it["cvr"] = it["units"] / it["sessions"] * 100 if it["sessions"] else 0.0
    return list(items.values())


def percentile_rank(values, v):
    if not values:
        return 0
    return sum(1 for x in values if x <= v) / len(values)


def diagnose(items):
    total_ses = sum(i["sessions"] for i in items)
    total_units = sum(i["units"] for i in items)
    store_cvr = total_units / total_ses * 100 if total_ses else 0
    ses_list = [i["sessions"] for i in items]

    for it in items:
        ses_rank = percentile_rank(ses_list, it["sessions"])
        busy = ses_rank >= TRAFFIC_TOP and it["sessions"] > 0
        cvr_low = it["cvr"] < store_cvr * CVR_LOW_RATIO
        cvr_high = it["cvr"] >= store_cvr * CVR_HIGH_RATIO and it["units"] > 0
        bb = it["buybox"]

        if bb is not None and bb < BUYBOX_OK and it["sessions"] > 0:
            it["type"], it["priority"] = "カートを取られている", 1
            it["why"] = f"カート獲得率が{bb:.0f}%。来た人の一部が他のお店から買っている"
            it["todo"] = ["価格を最安・送料込みで見直す", "在庫切れ・発送日数を確認（FBA化も検討）",
                          "相乗り出品者がいないか確認、ブランド登録を検討"]
        elif busy and cvr_low:
            it["type"], it["priority"] = "見られているのに買われない", 1
            it["why"] = f"人はよく来ている(上位)のに、買う率{it['cvr']:.1f}%がお店平均{store_cvr:.1f}%より低い"
            it["todo"] = ["メイン画像を白背景で大きく・サブ画像に使っている場面を追加",
                          "タイトル先頭に「何の商品か＋一番の売り」を入れる",
                          "レビュー数・星を確認し、低ければ改善点を説明文で先回り",
                          "競合と価格・ポイントを比べる"]
        elif not busy and cvr_high:
            it["type"], it["priority"] = "買われやすいのに人が来ない", 2
            it["why"] = f"買う率{it['cvr']:.1f}%と高いのに、見に来る人が少ない"
            it["todo"] = ["スポンサープロダクト広告を少額でスタート（オートで検索語を集める）",
                          "検索キーワード（バックエンド）を見直して追加",
                          "クーポン・タイムセールで露出を増やす"]
        elif busy and not cvr_low and it["units"] > 0:
            it["type"], it["priority"] = "勝ち商品", 3
            it["why"] = "人も来て、買われてもいる。お店の柱"
            it["todo"] = ["在庫切れを絶対に起こさない（在庫日数を毎週チェック）",
                          "広告予算を少し増やして伸ばす", "色違い・セット品などの関連商品を作る"]
        elif it["sessions"] == 0 or (not busy and it["units"] == 0):
            it["type"], it["priority"] = "ほとんど動いていない", 4
            it["why"] = "見に来る人も売れた数も少ない"
            it["todo"] = ["検索で出てくるか確認（出品停止・カテゴリ違いがないか）",
                          "3か月動かなければ値下げ処分か出品停止で在庫コストを減らす"]
        else:
            it["type"], it["priority"] = "ふつう", 5
            it["why"] = "目立った問題なし"
            it["todo"] = []
    items.sort(key=lambda i: (i["priority"], -i["sales"]))
    return store_cvr


def compare(cur, prev):
    if not prev:
        return None
    p = {i["asin"]: i for i in prev}
    for it in cur:
        o = p.get(it["asin"])
        it["sales_prev"] = o["sales"] if o else 0.0
    keys = ("sales", "units", "sessions")
    return {k: (sum(i[k] for i in cur), sum(i[k] for i in prev)) for k in keys}


def yen(v):
    return f"¥{v:,.0f}"


def pct_change(a, b):
    if not b:
        return ""
    d = (a - b) / b * 100
    return f"{'+' if d >= 0 else ''}{d:.0f}%"


def build(files):
    cur_file = files[-1]
    cur = read_csv(cur_file)
    prev = read_csv(files[-2]) if len(files) >= 2 else None
    store_cvr = diagnose(cur)
    diff = compare(cur, prev)

    total = {
        "sales": sum(i["sales"] for i in cur),
        "units": sum(i["units"] for i in cur),
        "sessions": sum(i["sessions"] for i in cur),
        "cvr": store_cvr,
        "items": len(cur),
    }
    total["aov"] = total["sales"] / total["units"] if total["units"] else 0

    by_sales = sorted(cur, key=lambda i: -i["sales"])
    top_n = max(1, round(len(cur) * 0.2))
    top_share = sum(i["sales"] for i in by_sales[:top_n]) / total["sales"] * 100 if total["sales"] else 0

    groups = {}
    for it in cur:
        groups.setdefault(it["type"], []).append(it)

    # 売上が上がる余地の目安：CVRが低い商品がお店平均まで上がったら？
    upside = 0.0
    for it in groups.get("見られているのに買われない", []):
        price = it["sales"] / it["units"] if it["units"] else total["aov"]
        upside += max(0, it["sessions"] * store_cvr / 100 - it["units"]) * price

    summary = {
        "generated_at": datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "source": cur_file.name,
        "compared_with": files[-2].name if prev else None,
        "total": total,
        "top20_share": top_share,
        "upside_yen": upside,
        "diff": diff,
        "counts": {k: len(v) for k, v in groups.items()},
        "items": cur,
    }
    return summary


def render_todo(s):
    lines = [f"# 今週やること（{s['generated_at']} / {s['source']}）", ""]
    lines.append("上から順にやると効果が大きいです。終わったら [x] にしましょう。")
    lines.append("")
    for it in s["items"]:
        if not it["todo"]:
            continue
        lines.append(f"## [{it['type']}] {it['title'][:40] or it['asin']}（{it['asin']}）")
        lines.append(f"理由: {it['why']}")
        lines += [f"- [ ] {t}" for t in it["todo"]]
        lines.append("")
    lines += ["## お店全体", "- [ ] 在庫が30日分を切っている商品がないか確認",
              "- [ ] 広告レポートで「売れていないのにお金がかかっている検索語」を除外",
              "- [ ] 新しい成績表CSVを data/ に置く（毎週同じ曜日がおすすめ）"]
    return "\n".join(lines) + "\n"


def render_html(s):
    t = s["total"]
    e = html.escape
    d = s["diff"]

    def kpi(label, value, key=None):
        ch = ""
        if d and key:
            ch = f'<span class="chg">前回比 {pct_change(*d[key])}</span>'
        return f'<div class="kpi"><div class="lbl">{label}</div><div class="val">{value}</div>{ch}</div>'

    order = ["カートを取られている", "見られているのに買われない", "買われやすいのに人が来ない",
             "勝ち商品", "ほとんど動いていない", "ふつう"]
    color = {"カートを取られている": "red", "見られているのに買われない": "red",
             "買われやすいのに人が来ない": "amber", "勝ち商品": "green",
             "ほとんど動いていない": "gray", "ふつう": "gray"}

    chips = "".join(
        f'<span class="chip {color[k]}">{k} <b>{s["counts"].get(k, 0)}</b></span>'
        for k in order if s["counts"].get(k))

    cards = []
    for it in s["items"]:
        todo = "".join(f"<li>{e(x)}</li>" for x in it["todo"])
        bb = f"{it['buybox']:.0f}%" if it["buybox"] is not None else "-"
        prev = ""
        if "sales_prev" in it:
            prev = f"<span>前回 {yen(it['sales_prev'])}</span>"
        cards.append(f"""
<article class="card">
  <div class="tag {color[it['type']]}">{e(it['type'])}</div>
  <h3>{e(it['title'] or it['asin'])}</h3>
  <div class="meta">{e(it['asin'])}{(' / ' + e(it['sku'])) if it['sku'] else ''}</div>
  <div class="nums">
    <span>売上 <b>{yen(it['sales'])}</b></span>{prev}
    <span>販売数 <b>{it['units']:,.0f}</b></span>
    <span>セッション <b>{it['sessions']:,.0f}</b></span>
    <span>買う率 <b>{it['cvr']:.1f}%</b></span>
    <span>カート <b>{bb}</b></span>
  </div>
  <p class="why">{e(it['why'])}</p>
  {f'<ul>{todo}</ul>' if todo else ''}
</article>""")

    cmp_note = f"（前回 {e(s['compared_with'])} と比較）" if s["compared_with"] else "（比較データなし：CSVを2回以上置くと前回比が出ます）"

    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Amazon店舗レポート</title>
<style>
:root{{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--sub:#6b6b70;--line:#e4e4e0;
--red:#c8372d;--amber:#b7791f;--green:#2f855a;--gray:#77777c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151516;--card:#1f1f21;--ink:#ececec;--sub:#a0a0a6;--line:#333;
--red:#ff6b5e;--amber:#f0b54a;--green:#58c48b;--gray:#9a9aa0}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}}
main{{max-width:860px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:22px;margin:0 0 4px}} .sub{{color:var(--sub);font-size:13px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:18px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}}
.lbl{{color:var(--sub);font-size:12px}} .val{{font-size:22px;font-weight:700}} .chg{{font-size:12px;color:var(--sub)}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}}
.box h2{{font-size:16px;margin:0 0 6px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}}
.chip{{border:1px solid currentColor;border-radius:99px;padding:2px 10px;font-size:13px}}
.red{{color:var(--red)}} .amber{{color:var(--amber)}} .green{{color:var(--green)}} .gray{{color:var(--gray)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}}
.card h3{{font-size:15px;margin:4px 0 0;word-break:break-word}}
.tag{{font-size:12px;font-weight:700}} .meta{{color:var(--sub);font-size:12px}}
.nums{{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;margin:8px 0;color:var(--sub)}}
.nums b{{color:var(--ink)}} .why{{margin:6px 0;font-size:14px}}
ul{{margin:4px 0 0;padding-left:20px}} li{{margin:2px 0}}
</style></head><body><main>
<h1>Amazon 店舗レポート</h1>
<div class="sub">{e(s['generated_at'])} 作成 / 元データ: {e(s['source'])} {cmp_note}</div>

<div class="kpis">
{kpi("売上", yen(t['sales']), "sales")}
{kpi("販売数", f"{t['units']:,.0f}", "units")}
{kpi("セッション", f"{t['sessions']:,.0f}", "sessions")}
{kpi("買う率(CVR)", f"{t['cvr']:.1f}%")}
{kpi("1個あたり単価", yen(t['aov']))}
</div>

<div class="box">
<h2>ひとことでいうと</h2>
<p>売上 = <b>見に来た人</b> × <b>買う率</b> × <b>単価</b>。この3つのどれが弱いかを商品ごとに判定しました。</p>
<p>上位20%の商品で売上の<b>{s['top20_share']:.0f}%</b>を作っています。
「見られているのに買われない」商品の買う率をお店平均まで上げると、
売上は約<b>{yen(s['upside_yen'])}</b>増える見込みです。</p>
<div class="chips">{chips}</div>
</div>

<h2 style="font-size:17px;margin-top:24px">商品ごとの診断（やる順）</h2>
{''.join(cards)}
</main></body></html>
"""


def main():
    files = sorted(DATA_DIR.glob("*.csv")) if DATA_DIR.exists() else []
    if not files:
        files = sorted(SAMPLE_DIR.glob("*.csv"))
        print("data/ にCSVがないので、お試しデータで作ります。")
    if not files:
        raise SystemExit("CSVがありません。amazon-shop/data/ に置いてください。")

    s = build(files)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "report.html").write_text(render_html(s), encoding="utf-8")
    (OUT_DIR / "todo.md").write_text(render_todo(s), encoding="utf-8")
    (OUT_DIR / "summary.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    t = s["total"]
    print(f"完了: 売上 {yen(t['sales'])} / CVR {t['cvr']:.1f}% / 商品 {t['items']}件")
    print(f"  {OUT_DIR / 'report.html'}")


if __name__ == "__main__":
    main()
