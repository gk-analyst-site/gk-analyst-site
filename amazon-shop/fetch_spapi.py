#!/usr/bin/env python3
"""Amazon公式の窓口(SP-API)から成績表を自動でもらってきて、
amazon-shop/data/YYYY-MM-DD.csv として保存するプログラム。

手作業のCSVダウンロードの代わりです。保存したCSVは analyze.py がそのまま読めます。

必要な鍵(環境変数 / GitHubのSecrets):
  SPAPI_CLIENT_ID      … アプリのクライアントID (amzn1.application-oa2-client....)
  SPAPI_CLIENT_SECRET  … アプリのクライアントシークレット
  SPAPI_REFRESH_TOKEN  … 自分のお店を許可したときにもらうトークン (Atzr|....)

取り方は2段構え:
  ① 売上・トラフィックレポート(セッション/カート獲得率つき) … ブランド分析の権限が必要
  ② ①が使えないときは注文レポート(売上と個数だけ)
"""

import csv
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
JST = timezone(timedelta(hours=9))

ENDPOINT = "https://sellingpartnerapi-fe.amazon.com"   # 日本は「極東(FE)」窓口
MARKETPLACE_JP = "A1VC38T7YXB528"
DAYS = 7          # 何日分を1つの成績表にするか
LAG_DAYS = 2      # 売上・トラフィックは反映に2日ほどかかるので、その分ずらす

HEADER = ["（親）ASIN", "（子）ASIN", "タイトル", "SKU", "セッション - 合計",
          "ページビュー - 合計", "おすすめ出品の獲得率", "注文された商品点数",
          "注文商品売上", "注文品目総数"]


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def http(method, url, headers=None, body=None, raw=False):
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                content = r.read()
                return content if raw else json.loads(content or b"{}")
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 4:      # 混んでいるので少し待ってやり直す
                time.sleep(2 ** attempt * 2)
                continue
            raise ApiError(e.code, text) from None


def access_token():
    need = ["SPAPI_CLIENT_ID", "SPAPI_CLIENT_SECRET", "SPAPI_REFRESH_TOKEN"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"鍵が足りません: {missing}（READMEの手順でSecretsに登録してください）")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": os.environ["SPAPI_REFRESH_TOKEN"],
        "client_id": os.environ["SPAPI_CLIENT_ID"],
        "client_secret": os.environ["SPAPI_CLIENT_SECRET"],
    }).encode()
    res = http("POST", "https://api.amazon.com/auth/o2/token",
               {"Content-Type": "application/x-www-form-urlencoded"}, body)
    return res["access_token"]


class SpApi:
    def __init__(self):
        self.token = access_token()

    def call(self, method, path, body=None):
        headers = {"x-amz-access-token": self.token, "Content-Type": "application/json"}
        return http(method, ENDPOINT + path, headers, body)

    def report(self, report_type, start, end, options=None):
        """レポートを注文 → できあがるまで待つ → 中身を受け取る"""
        body = {"reportType": report_type, "marketplaceIds": [MARKETPLACE_JP],
                "dataStartTime": start.isoformat(), "dataEndTime": end.isoformat()}
        if options:
            body["reportOptions"] = options
        rid = self.call("POST", "/reports/2021-06-30/reports", body)["reportId"]
        print(f"  レポート注文: {report_type} ({rid})")
        for _ in range(60):                       # 最大30分待つ
            time.sleep(30)
            st = self.call("GET", f"/reports/2021-06-30/reports/{rid}")
            status = st.get("processingStatus")
            if status == "DONE":
                break
            if status in ("CANCELLED", "FATAL"):
                raise ApiError(0, f"レポート作成に失敗しました ({status})")
        else:
            raise ApiError(0, "レポート作成が時間内に終わりませんでした")
        doc = self.call("GET", f"/reports/2021-06-30/documents/{st['reportDocumentId']}")
        content = http("GET", doc["url"], raw=True)
        if doc.get("compressionAlgorithm") == "GZIP":
            content = gzip.decompress(content)
        return content

    def title(self, asin):
        try:
            res = self.call("GET", f"/catalog/2022-04-01/items/{asin}?"
                            f"marketplaceIds={MARKETPLACE_JP}&includedData=summaries")
            sums = res.get("summaries") or []
            return sums[0].get("itemName", "") if sums else ""
        except ApiError:
            return ""


def from_sales_traffic(content):
    """①売上・トラフィックレポート(JSON) → 行のリスト"""
    data = json.loads(content.decode("utf-8"))
    rows = []
    for a in data.get("salesAndTrafficByAsin", []):
        s, t = a.get("salesByAsin", {}), a.get("trafficByAsin", {})
        rows.append({
            "parent": a.get("parentAsin", ""), "asin": a.get("childAsin") or a.get("parentAsin", ""),
            "title": "", "sku": a.get("sku", ""),
            "sessions": t.get("sessions", 0), "pageviews": t.get("pageViews", 0),
            "buybox": t.get("buyBoxPercentage"),
            "units": s.get("unitsOrdered", 0),
            "sales": (s.get("orderedProductSales") or {}).get("amount", 0),
            "orders": s.get("totalOrderItems", 0),
        })
    return rows


def from_orders(content):
    """②注文レポート(タブ区切り) → 商品ごとに合計した行のリスト"""
    text = content.decode("utf-8", errors="replace")
    if text and not text.lstrip().startswith("amazon-order-id"):
        text = content.decode("cp932", errors="replace")
    items = {}
    for r in csv.DictReader(io.StringIO(text), delimiter="\t"):
        if (r.get("order-status") or "").lower() == "cancelled":
            continue
        asin = r.get("asin", "").strip()
        if not asin:
            continue
        it = items.setdefault(asin, {
            "parent": "", "asin": asin, "title": r.get("product-name", ""), "sku": r.get("sku", ""),
            "sessions": "", "pageviews": "", "buybox": None, "units": 0, "sales": 0.0, "orders": 0})
        it["units"] += int(float(r.get("quantity") or 0))
        it["sales"] += float(r.get("item-price") or 0)
        it["orders"] += 1
    return list(items.values())


def write_csv(rows, path):
    DATA_DIR.mkdir(exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for r in rows:
            bb = "" if r["buybox"] is None else f"{r['buybox']}%"
            w.writerow([r["parent"], r["asin"], r["title"], r["sku"], r["sessions"],
                        r["pageviews"], bb, r["units"], r["sales"], r["orders"]])


def main():
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today - timedelta(days=LAG_DAYS) - timedelta(seconds=1)
    start = (end - timedelta(days=DAYS - 1)).replace(hour=0, minute=0, second=0)
    out = DATA_DIR / f"{end:%Y-%m-%d}.csv"
    print(f"期間: {start:%Y-%m-%d} 〜 {end:%Y-%m-%d}")

    api = SpApi()
    try:
        content = api.report("GET_SALES_AND_TRAFFIC_REPORT", start, end,
                             {"dateGranularity": "DAY", "asinGranularity": "CHILD"})
        rows = from_sales_traffic(content)
        for r in rows[:100]:                    # 商品名をもらう(多すぎると時間がかかるので100件まで)
            r["title"] = api.title(r["asin"])
            time.sleep(0.5)
        mode = "売上・トラフィック"
    except ApiError as e:
        print(f"  売上・トラフィックレポートが使えません → 注文レポートに切り替えます\n  理由: {e}")
        content = api.report("GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL", start, end)
        rows = from_orders(content)
        mode = "注文データのみ（セッション・カート獲得率なし）"

    write_csv(rows, out)
    print(f"保存しました: {out}（{mode} / {len(rows)}商品）")


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        sys.exit(f"SP-APIでエラー: {e}")
