# -*- coding: utf-8 -*-
"""
楽天ROOM 半自動 出品アシスタント
====================================
このプログラムがやること（全部じどう）:
  1. 楽天の「公式ランキングAPI」から、今よく売れている商品を集める
  2. あなたの「アフィリエイトID」をつけたリンク（＝これで報酬が入る）を作る
  3. 楽天ROOMにそのまま貼れる「投稿文（キャプション）」を自動で書く
  4. スマホで見やすい「今日の投稿リスト（HTMLページ）」を出力する

あなたがやること:
  - 出力された today.html をスマホで開いて、気に入った商品の
    「投稿文をコピー」→ 楽天ROOMアプリで貼り付けて「投稿」ボタンをタップするだけ。

※「投稿ボタンを自動で押す」ことはしません。楽天ROOMの規約で禁止されていて、
   アカウント停止のリスクがあるからです。ここだけ人間がやる = 安全 & 楽ちん。

鍵（キー）がまだ無くても、デモモードで動きます（サンプル商品で中身を体験できます）。
"""

import os
import json
import html
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# 【設定】ここだけ変えれば、あなた好みにカスタマイズできます
# ---------------------------------------------------------------------------

# 楽天の「鍵」を環境変数から読み込みます（後述のREADMEで取り方を説明）
#   RAKUTEN_APP_ID       … 楽天Developersの applicationId（売れ筋データを取るのに必要）
#   RAKUTEN_AFFILIATE_ID … 楽天アフィリエイトID（報酬が入るリンクを作るのに必要）
#
# 鍵のセット方法は2つ（どちらでもOK）:
#   A) 同じフォルダに「keys.local」というファイルを作り、次のように書くだけ:
#        RAKUTEN_APP_ID=あなたのapplicationId
#        RAKUTEN_AFFILIATE_ID=0a0d370d.2e0b70f8.0a0d370e.fc9426b6
#   B) 環境変数（export）で渡す（GitHub Actionsではこちら）
# ※keys.local は .gitignore で除外されるので、GitHubには上がりません（安心）。

def _load_local_keys():
    """同じフォルダの keys.local から鍵を読み込む（環境変数が無いとき用）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.local")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            # 環境変数が優先。ファイルの値は環境変数が空のときだけ使う
            os.environ.setdefault(key.strip(), value.strip())

_load_local_keys()

RAKUTEN_APP_ID = os.environ.get("RAKUTEN_APP_ID", "").strip()
RAKUTEN_AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "").strip()
# 新しい楽天API（openapi.rakuten.co.jp）では、アプリIDに加えて
# 「アクセスキー」も必要です。Rakuten Developersのアプリ画面に表示されます。
RAKUTEN_ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "").strip()

# どのジャンルの売れ筋を集めるか。genreId=0 は「総合ランキング」。
# 他のジャンルを足したいときは (ジャンルID, "表示名") を追加してください。
# ジャンルIDの調べ方はREADMEに書いてあります。
GENRES = [
    (0,      "総合"),
    (100371, "レディースファッション"),
    (551177, "メンズファッション"),
    (100939, "美容・コスメ・香水"),
    (100227, "食品"),
    (100804, "インテリア・寝具・収納"),
]

# 各ジャンルから上位いくつを拾うか（1〜30くらいがおすすめ）
ITEMS_PER_GENRE = 5

# 出力先フォルダ
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# 楽天 商品ランキングAPI のURL
# ※2026年の移行で、入り口が app.rakuten.co.jp → openapi.rakuten.co.jp に変わりました。
#   新しいUUID形式のアプリIDは、この新しい入り口でだけ有効です。
RANKING_API = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"

# 日本時間
JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 部品1: 楽天APIから売れ筋商品を取ってくる
# ---------------------------------------------------------------------------
def fetch_ranking(genre_id):
    """指定ジャンルの売れ筋ランキングを楽天APIから取得して、商品リストを返す。"""
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "genreId": genre_id,
        "format": "json",
    }
    # 新APIはアクセスキーも必須
    if RAKUTEN_ACCESS_KEY:
        params["accessKey"] = RAKUTEN_ACCESS_KEY
    # アフィリエイトIDがあれば、APIが「報酬つきリンク」も一緒に返してくれる
    if RAKUTEN_AFFILIATE_ID:
        params["affiliateId"] = RAKUTEN_AFFILIATE_ID

    url = RANKING_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "rakuten-room-helper/1.0",
        # 新APIは Referer と Origin の両方で「許可されたWebサイト」を確認する。
        # アプリ登録の room.rakuten.co.jp に合わせておく（403リファラー対策）。
        "Referer": "https://room.rakuten.co.jp/",
        "Origin": "https://room.rakuten.co.jp",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # エラーの本文には「何がダメか」が書いてあるので、それも一緒に見せる
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}") from None
    return data.get("Items", [])


# ---------------------------------------------------------------------------
# 部品2: 投稿文（キャプション）を自動で書く
# ---------------------------------------------------------------------------
def build_caption(name, price, genre_name):
    """楽天ROOMにそのまま貼れる投稿文を作る。ルールベースなので無料＆完全自動。"""
    # 商品名が長すぎると読みにくいので、ほどよく短くする
    short_name = name if len(name) <= 40 else name[:39] + "…"

    # 「暮らしのポチ袋」の統一トーン：やさしく語りかける暮らし系の人らしいひとこと
    hooks = {
        "総合":                 "暮らしがちょっとラクになる、見つけたよ〜🛍️",
        "レディースファッション": "肩の力を抜いて着られる、お気に入りになりそう🌷",
        "メンズファッション":     "毎日さらっと使える、こういうの探してた👕",
        "美容・コスメ・香水":     "がんばった自分に、小さなごほうびを🫧",
        "食品":                 "おうち時間がほっとする、我が家の定番になりそう☕",
        "インテリア・寝具・収納":  "置くだけでお部屋が整う、地味に神アイテム🏠",
    }
    hook = hooks.get(genre_name, "暮らしの「あってよかった」、そっとおすそ分け🍀")

    # ハッシュタグ（暮らし系で見つけてもらいやすいタグに統一）
    tags = ["#楽天ROOM", "#暮らしを楽しむ", "#買ってよかった",
            "#暮らしの記録", "#日々のこと", "#楽天room初心者"]
    genre_tag = {
        "レディースファッション": "#大人カジュアル",
        "メンズファッション":     "#シンプルコーデ",
        "美容・コスメ・香水":     "#自分にごほうび",
        "食品":                 "#おうちごはん",
        "インテリア・寝具・収納":  "#丁寧な暮らし",
    }.get(genre_name)
    if genre_tag:
        tags.insert(1, genre_tag)

    price_line = f"💰 {price:,}円（送料などは商品ページで確認してね）" if price else ""

    caption = f"{hook}\n\n【{short_name}】\n{price_line}\n\n" \
              f"気になったらプロフィールのリンクから見てみてね👀\n" \
              f"フォローしてくれたら嬉しいです☺️\n\n" \
              + " ".join(tags)
    return caption.strip()


# ---------------------------------------------------------------------------
# 部品3: 集めた全商品を「投稿ネタ」に整える
# ---------------------------------------------------------------------------
def collect_posts():
    """全ジャンルを回って、投稿ネタのリストを作って返す。"""
    posts = []
    demo = not RAKUTEN_APP_ID  # 鍵が無ければデモモード

    if demo:
        print("⚠️  RAKUTEN_APP_ID が設定されていないので【デモモード】で動きます。")
        print("    → サンプル商品で表示します。本番は README を見て鍵を設定してください。\n")
        return demo_posts()

    for genre_id, genre_name in GENRES:
        try:
            items = fetch_ranking(genre_id)
        except Exception as e:
            print(f"  × ジャンル『{genre_name}』の取得に失敗（スキップします）: {e}")
            continue

        picked = 0
        for wrap in items:
            item = wrap.get("Item", wrap)  # APIは {"Item": {...}} の形
            name = item.get("itemName", "")
            price = item.get("itemPrice", 0)
            rank = item.get("rank", picked + 1)
            # アフィリンクがあればそれを、無ければ通常リンクを使う
            link = item.get("affiliateUrl") or item.get("itemUrl", "")
            images = item.get("mediumImageUrls", [])
            image = ""
            if images:
                first = images[0]
                image = first.get("imageUrl", "") if isinstance(first, dict) else str(first)
                # サムネの ?_ex=128x128 を大きめに置き換え
                image = image.replace("?_ex=128x128", "?_ex=300x300")

            posts.append({
                "genre": genre_name,
                "rank": rank,
                "name": name,
                "price": price,
                "link": link,
                "image": image,
                "caption": build_caption(name, price, genre_name),
            })
            picked += 1
            if picked >= ITEMS_PER_GENRE:
                break
        print(f"  ○ ジャンル『{genre_name}』から {picked} 件ゲット")

    return posts


def demo_posts():
    """鍵が無いときに、動きを体験するためのサンプルデータ。"""
    samples = [
        ("総合", "ふわふわ タオル 5枚セット 今治産 まとめ買い", 2480,
         "https://item.rakuten.co.jp/demo/towel/"),
        ("美容・コスメ・香水", "薬用 リップクリーム 高保湿 無香料 3本セット", 980,
         "https://item.rakuten.co.jp/demo/lip/"),
        ("食品", "北海道 チーズ お取り寄せ 詰め合わせ", 3200,
         "https://item.rakuten.co.jp/demo/cheese/"),
    ]
    posts = []
    for i, (genre, name, price, link) in enumerate(samples, start=1):
        posts.append({
            "genre": genre, "rank": i, "name": name, "price": price,
            "link": link, "image": "",
            "caption": build_caption(name, price, genre),
        })
    return posts


# ---------------------------------------------------------------------------
# 部品4: スマホで見やすい「今日の投稿リスト」HTMLを書き出す
# ---------------------------------------------------------------------------
def write_html(posts, path):
    now = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")
    cards = []
    for i, p in enumerate(posts):
        name = html.escape(p["name"])
        genre = html.escape(p["genre"])
        caption = html.escape(p["caption"])
        link = html.escape(p["link"])
        price = f'{p["price"]:,}円' if p["price"] else "価格は商品ページで"
        img = f'<img src="{html.escape(p["image"])}" alt="" loading="lazy">' if p["image"] else \
              '<div class="noimg">画像なし（デモ）</div>'
        cards.append(f"""
        <div class="card">
          <div class="badge">{genre}・{p['rank']}位</div>
          {img}
          <h3>{name}</h3>
          <p class="price">{price}</p>
          <textarea id="cap{i}" readonly>{caption}</textarea>
          <div class="btns">
            <button onclick="copyCap({i})">📋 投稿文をコピー</button>
            <a class="link" href="{link}" target="_blank" rel="noopener">🔗 商品ページ</a>
          </div>
        </div>""")

    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>今日の楽天ROOM投稿リスト</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Kaku Gothic ProN", sans-serif;
         margin:0; background:#f5f5f7; color:#222; }}
  header {{ background:#bf0000; color:#fff; padding:16px; text-align:center; }}
  header h1 {{ margin:0; font-size:18px; }}
  header p {{ margin:6px 0 0; font-size:12px; opacity:.9; }}
  .wrap {{ max-width:520px; margin:0 auto; padding:12px; }}
  .card {{ background:#fff; border-radius:14px; padding:14px; margin-bottom:14px;
          box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  .badge {{ display:inline-block; background:#ffe4e4; color:#bf0000; font-size:12px;
           font-weight:bold; padding:3px 10px; border-radius:20px; }}
  .card img, .noimg {{ width:100%; height:220px; object-fit:contain; margin:10px 0;
                      background:#fafafa; border-radius:10px; }}
  .noimg {{ display:flex; align-items:center; justify-content:center; color:#aaa; }}
  .card h3 {{ font-size:15px; margin:6px 0; line-height:1.4; }}
  .price {{ color:#bf0000; font-weight:bold; margin:2px 0 10px; }}
  textarea {{ width:100%; height:120px; box-sizing:border-box; border:1px solid #ddd;
             border-radius:8px; padding:8px; font-size:13px; line-height:1.5; resize:vertical; }}
  .btns {{ display:flex; gap:8px; margin-top:10px; }}
  button, .link {{ flex:1; text-align:center; padding:11px; border-radius:10px; font-size:14px;
                  font-weight:bold; border:none; cursor:pointer; text-decoration:none; }}
  button {{ background:#bf0000; color:#fff; }}
  .link {{ background:#fff; color:#bf0000; border:2px solid #bf0000; line-height:1.2; }}
  .done {{ background:#2a8f3c !important; }}
</style></head><body>
<header>
  <h1>🛒 今日の楽天ROOM投稿リスト</h1>
  <p>{now} 時点の売れ筋 / 全 {len(posts)} 件 ・ コピーして楽天ROOMに貼るだけ</p>
</header>
<div class="wrap">
  {''.join(cards)}
</div>
<script>
  function copyCap(i) {{
    var t = document.getElementById('cap'+i);
    navigator.clipboard.writeText(t.value).then(function() {{
      var b = event.target;
      var old = b.textContent;
      b.textContent = '✅ コピーしました！';
      b.classList.add('done');
      setTimeout(function(){{ b.textContent = old; b.classList.remove('done'); }}, 1500);
    }});
  }}
</script>
</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


# ---------------------------------------------------------------------------
# メイン: 上の部品を順番に呼ぶだけ
# ---------------------------------------------------------------------------
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("▶ 楽天の売れ筋を集めています...\n")
    posts = collect_posts()

    if not posts:
        print("\n商品が1件も取れませんでした。鍵の設定やジャンルIDを確認してください。")
        return

    # データ(JSON)を保存（あとで別の使い方をしたいとき用）
    json_path = os.path.join(OUTPUT_DIR, "today.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

    # 見やすいHTMLを保存
    html_path = os.path.join(OUTPUT_DIR, "today.html")
    write_html(posts, html_path)

    print(f"\n✅ 完成！ {len(posts)} 件の投稿ネタを作りました。")
    print(f"   - スマホ用ページ: {html_path}")
    print(f"   - データ:         {json_path}")
    print("\n👉 today.html を開いて、投稿文をコピー → 楽天ROOMに貼って投稿しよう！")


if __name__ == "__main__":
    main()
