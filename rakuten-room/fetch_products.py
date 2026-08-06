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
import re
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
# 部品2a: 商品名から「検索しやすいキーワード」を作る
# （楽天ROOMアプリの「商品キーワード検索から投稿」で使う用）
# ---------------------------------------------------------------------------
# 検索のじゃまになる宣伝ワード（含まれていたらそのトークンを捨てる）
_PROMO_WORDS = (
    "送料無料", "送料込", "あす楽", "楽天", "クーポン", "セール", "ポイント",
    "まとめ買い", "選べる", "公式", "正規品", "訳あり", "本日", "限り",
    "期間限定", "数量限定", "再入荷", "予約", "即納", "新品", "最大",
    "第1位", "1位", "ランキング", "神トク", "完売", "割引", "OFF", "off",
    "返品", "交換", "あたり", "無料", "半額", "在庫", "特価", "お得",
)

def build_search_keywords(name, max_words=4):
    """商品名から宣伝文句を除き、検索用の短いキーワードを作る。"""
    s = name
    # 【…】[…]（…）〔…〕≪…≫ で囲まれた宣伝文句を除去
    s = re.sub(r"[【\[（(〔≪].*?[】\]）)〕≫]", " ", s)
    s = re.sub(r"★.*?★", " ", s)
    # 区切り記号を空白にそろえる
    s = re.sub(r"[／/｜|,、・×＋+=＝~〜～!！?？。．\.:：;；★☆♪【】\[\]（）()]+", " ", s)
    tokens = s.split()

    picked = []
    for t in tokens:
        if any(w in t for w in _PROMO_WORDS):
            continue
        # 価格や割合を含むトークンは捨てる（例: 144円, 25％, 1,144）
        if "円" in t or "%" in t or "％" in t:
            continue
        # 数字・単位・％だけのトークンは捨てる
        if re.fullmatch(r"[0-9０-９,，.%％台点本枚箱個組ml入]+", t):
            continue
        picked.append(t)
        if len(picked) >= max_words:
            break

    kw = " ".join(picked).strip()
    if len(kw) < 2:  # うまく取れなければ、括弧を除いた先頭20文字
        kw = re.sub(r"\s+", " ", s).strip()[:20]
    return kw


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
              f"気になったら下の商品をタップしてチェックしてね👇\n" \
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

        # 新APIは順位の降順(30→1)で返すことがあるので、1位から順に並べ直す
        def _rank_of(wrap):
            it = wrap.get("Item", wrap)
            try:
                return int(it.get("rank", 9999))
            except (ValueError, TypeError):
                return 9999
        items.sort(key=_rank_of)

        picked = 0
        for wrap in items:
            item = wrap.get("Item", wrap)  # APIは {"Item": {...}} の形
            name = item.get("itemName", "")
            # 価格は文字列("2480")で返ることがあるので、数字に変換する
            try:
                price = int(str(item.get("itemPrice", 0)).replace(",", "").strip() or 0)
            except (ValueError, TypeError):
                price = 0
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
                "keywords": build_search_keywords(name),
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
            "keywords": build_search_keywords(name),
            "caption": build_caption(name, price, genre),
        })
    return posts


# ---------------------------------------------------------------------------
# 部品3b: 売れ筋の中から「今日の推し」を選ぶ
# ---------------------------------------------------------------------------
def pick_todays_picks(posts, n=3):
    """順位・価格・画像・ジャンルの多様性で採点し、今日イチ推しのn件を選ぶ。"""
    def score(p):
        s = 0
        try:
            rank = int(p.get("rank") or 30)
        except (ValueError, TypeError):
            rank = 30
        s += (30 - min(rank, 30)) * 2          # 上位ほど高得点
        pr = p.get("price") or 0
        if 500 <= pr <= 5000:                  # 買われやすい価格帯を優遇
            s += 12
        elif pr <= 8000:
            s += 5
        if p.get("image"):
            s += 4
        return s

    order = sorted(range(len(posts)), key=lambda i: score(posts[i]), reverse=True)
    picks, seen = [], set()
    for i in order:                            # まずジャンル違いで選ぶ
        g = posts[i].get("genre")
        if g in seen:
            continue
        picks.append(i)
        seen.add(g)
        if len(picks) >= n:
            break
    for i in order:                            # 足りなければ埋める
        if len(picks) >= n:
            break
        if i not in picks:
            picks.append(i)
    return picks[:n]


# ---------------------------------------------------------------------------
# 部品4: スマホで見やすい「今日の投稿リスト」HTMLを書き出す
# ---------------------------------------------------------------------------
# PCで「楽天ROOMに投稿する」ボタンを自動で探して押す補助（ブックマークレット）
BOOKMARKLET = (
    "javascript:(function(){var q=document.querySelectorAll('a,button,[role=button],span,div');"
    "var h=null,i,e,t;for(i=0;i<q.length;i++){e=q[i];t=(e.textContent||'').replace(/\\s+/g,'');"
    "if(t&&t.length<=12&&(t.indexOf('ROOMに投稿')>=0||t.indexOf('ROOMで紹介')>=0||t.indexOf('ROOM投稿')>=0)){h=e;break;}}"
    "if(!h){for(i=0;i<q.length;i++){var u=q[i].getAttribute&&q[i].getAttribute('href');"
    "if(u&&/room\\.rakuten\\.co\\.jp/.test(u)){h=q[i];break;}}}"
    "if(h){h.scrollIntoView({behavior:'smooth',block:'center'});var o=h.style.outline;"
    "h.style.outline='4px solid #bf0000';setTimeout(function(){h.style.outline=o;},2500);"
    "try{h.click();}catch(x){}}else{alert('「楽天ROOMに投稿する」ボタンが見つかりませんでした。"
    "楽天市場の商品ページを開いて、ログインした状態でお試しください。');}})();"
)


def _render_card(i, p, featured=False):
    name = html.escape(p["name"])
    genre = html.escape(p["genre"])
    caption = html.escape(p["caption"])
    keywords = html.escape(p.get("keywords", ""))
    link = html.escape(p["link"])
    price = f'{p["price"]:,}円' if p["price"] else "価格は商品ページで"
    img = f'<img src="{html.escape(p["image"])}" alt="" loading="lazy">' if p["image"] else \
          '<div class="noimg">画像なし（デモ）</div>'
    star = '<span class="featured">⭐ 今日の推し</span>' if featured else ''
    fcls = ' featured' if featured else ''
    return f"""
        <div class="card{fcls}" id="card{i}" data-key="{link}">
          <div class="cardtop">
            <div class="badge">{genre}・{p['rank']}位</div>
            {star}
            <span class="donetag">✅ 投稿済み</span>
          </div>
          {img}
          <h3>{name}</h3>
          <p class="price">{price}</p>
          <textarea id="cap{i}" readonly>{caption}</textarea>
          <div class="steps">
            <button class="stepk" onclick="copyKw({i})">① 🔍 検索用キーワードをコピー</button>
            <button class="step1" onclick="copyCap({i})">② 投稿文をコピー</button>
            <button class="step2" onclick="copyLink({i})">商品リンクをコピー</button>
            <a class="step3" href="{link}" target="_blank" rel="noopener">↗ 商品ページを開く</a>
            <input type="hidden" id="lnk{i}" value="{link}">
            <input type="hidden" id="kw{i}" value="{keywords}">
          </div>
          <button class="donebtn" onclick="toggleDone({i})">✓ 投稿済みにする</button>
        </div>"""


def write_html(posts, path):
    now = datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")

    picks = pick_todays_picks(posts, 3)
    pick_set = set(picks)
    featured_html = "".join(_render_card(i, posts[i], True) for i in picks)
    rest_html = "".join(_render_card(i, posts[i], False)
                        for i in range(len(posts)) if i not in pick_set)
    rest_n = len(posts) - len(picks)

    # PC1クリック投稿の案内ブロック（f-stringの外で組み立て、波かっこ問題を回避）
    bm_esc = html.escape(BOOKMARKLET)
    bookmarklet_html = (
        '<details class="bm"><summary>💻 PCで1クリック投稿する（初回だけ設定・任意）</summary>'
        '<div class="bmbody">'
        '<p>楽天市場の商品ページで、公式の「楽天ROOMに投稿する」ボタンを自動で探して押す補助ツールです。'
        '（自動投稿ではなく、ボタン押しをラクにするだけの安全な補助です）</p>'
        '<ol><li>下の「コードをコピー」を押す</li>'
        '<li>ブラウザでブックマークを新規作成し、<b>名前</b>=「ROOM投稿」、<b>URL</b>欄に貼り付けて保存</li>'
        '<li>商品ページを開いて、そのブックマークを1回クリック → 投稿画面へジャンプ</li></ol>'
        '<textarea id="bmcode" readonly>' + bm_esc + '</textarea>'
        '<button class="bmcopy" onclick="copyText('
        "document.getElementById('bmcode').value, event.target, '✅ コピー！')"
        '">📋 コードをコピー</button>'
        '</div></details>'
    )

    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>今日の楽天ROOM投稿リスト</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Kaku Gothic ProN", sans-serif;
         margin:0; background:#f5f5f7; color:#222; }}
  header {{ background:#bf0000; color:#fff; padding:16px; text-align:center;
           position:sticky; top:0; z-index:10; }}
  header h1 {{ margin:0; font-size:18px; }}
  header p {{ margin:6px 0 0; font-size:12px; opacity:.9; }}
  .counter {{ margin-top:8px; font-size:13px; font-weight:bold;
             background:rgba(255,255,255,.2); border-radius:20px;
             display:inline-block; padding:4px 14px; }}
  .wrap {{ max-width:520px; margin:0 auto; padding:12px; }}
  .card {{ background:#fff; border-radius:14px; padding:14px; margin-bottom:14px;
          box-shadow:0 1px 4px rgba(0,0,0,.08); transition:opacity .2s; }}
  .cardtop {{ display:flex; align-items:center; justify-content:space-between; }}
  .badge {{ display:inline-block; background:#ffe4e4; color:#bf0000; font-size:12px;
           font-weight:bold; padding:3px 10px; border-radius:20px; }}
  .donetag {{ display:none; color:#2a8f3c; font-weight:bold; font-size:13px; }}
  .card img, .noimg {{ width:100%; height:220px; object-fit:contain; margin:10px 0;
                      background:#fafafa; border-radius:10px; }}
  .noimg {{ display:flex; align-items:center; justify-content:center; color:#aaa; }}
  .card h3 {{ font-size:15px; margin:6px 0; line-height:1.4; }}
  .price {{ color:#bf0000; font-weight:bold; margin:2px 0 10px; }}
  textarea {{ width:100%; height:120px; box-sizing:border-box; border:1px solid #ddd;
             border-radius:8px; padding:8px; font-size:13px; line-height:1.5; resize:vertical; }}
  .steps {{ display:flex; flex-direction:column; gap:8px; margin-top:10px; }}
  .steps button, .steps a {{ text-align:center; padding:13px; border-radius:10px;
                  font-size:15px; font-weight:bold; border:none; cursor:pointer;
                  text-decoration:none; display:block; }}
  .step1 {{ background:#bf0000; color:#fff; }}
  .stepk {{ background:#0a7d3c; color:#fff; }}
  .step2 {{ background:#ff7a00; color:#fff; }}
  .step3 {{ background:#fff; color:#bf0000; border:2px solid #bf0000 !important;
           box-sizing:border-box; }}
  .donebtn {{ width:100%; margin-top:10px; padding:11px; border-radius:10px;
             border:2px solid #2a8f3c; background:#fff; color:#2a8f3c;
             font-weight:bold; font-size:14px; cursor:pointer; }}
  .flash {{ background:#2a8f3c !important; color:#fff !important; }}
  /* 投稿済みカードは薄く＆折りたたむ */
  .card.done {{ opacity:.5; }}
  .card.done .donetag {{ display:inline; }}
  .card.done img, .card.done textarea, .card.done .steps {{ display:none; }}
  .card.done .donebtn {{ background:#2a8f3c; color:#fff; }}
  /* 今日の推し */
  .sec {{ font-size:16px; color:#bf0000; font-weight:bold; margin:6px 2px 10px; }}
  .featured {{ display:inline-block; background:#fff3cd; color:#a6791a; font-size:12px;
              font-weight:bold; padding:3px 10px; border-radius:20px; }}
  .card.featured {{ border:2px solid #ffcc00; }}
  /* 折りたたみ（残りの売れ筋・PC投稿の案内） */
  details.more, details.bm {{ background:#fff; border-radius:12px; padding:2px 12px;
              margin-bottom:14px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  details.more > summary, details.bm > summary {{ cursor:pointer; font-weight:bold;
              padding:13px 2px; font-size:14px; color:#333; }}
  .bmbody {{ padding:2px 2px 12px; font-size:13px; line-height:1.7; }}
  .bmbody ol {{ padding-left:20px; }}
  .bmbody textarea {{ width:100%; height:88px; box-sizing:border-box; border:1px solid #ddd;
              border-radius:8px; padding:8px; font-size:12px; }}
  .bmcopy {{ width:100%; margin-top:8px; padding:11px; border:none; border-radius:10px;
              background:#333; color:#fff; font-weight:bold; font-size:14px; cursor:pointer; }}
</style></head><body>
<header>
  <h1>🛒 今日の楽天ROOM投稿リスト</h1>
  <p>{now} 時点の売れ筋 / 全 {len(posts)} 件</p>
  <div class="counter" id="counter">投稿済み 0 / {len(posts)} 件</div>
</header>
<div class="wrap">
  {bookmarklet_html}
  <div class="sec">⭐ 今日の推し {len(picks)}件（まずはここから！）</div>
  {featured_html}
  <details class="more"><summary>▼ ほかの売れ筋も見る（残り {rest_n} 件）</summary>
  {rest_html}
  </details>
</div>
<script>
  var TOTAL = {len(posts)};

  function flash(btn, msg) {{
    var old = btn.textContent;
    btn.textContent = msg;
    btn.classList.add('flash');
    setTimeout(function(){{ btn.textContent = old; btn.classList.remove('flash'); }}, 1400);
  }}
  function copyText(txt, btn, msg) {{
    function done() {{ flash(btn, msg); }}
    // clipboard APIが使えない環境（プレビュー内など）向けの予備手段
    function fallback() {{
      var ta = document.createElement('textarea');
      ta.value = txt; ta.setAttribute('readonly', '');
      ta.style.position = 'fixed'; ta.style.top = '0'; ta.style.left = '0';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus(); ta.select();
      try {{ ta.setSelectionRange(0, ta.value.length); }} catch (e) {{}}
      var ok = false;
      try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
      document.body.removeChild(ta);
      flash(btn, ok ? msg : '↑の文字を長押しでコピーしてね');
    }}
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(txt).then(done).catch(fallback);
    }} else {{
      fallback();
    }}
  }}
  function copyCap(i) {{
    copyText(document.getElementById('cap'+i).value, event.target, '✅ 投稿文をコピー！');
  }}
  function copyLink(i) {{
    copyText(document.getElementById('lnk'+i).value, event.target, '✅ リンクをコピー！');
  }}
  function copyKw(i) {{
    copyText(document.getElementById('kw'+i).value, event.target, '✅ キーワードをコピー！');
  }}

  // どこまで投稿したかをこのスマホに記憶する
  function doneStore() {{
    try {{ return JSON.parse(localStorage.getItem('room_done') || '{{}}'); }}
    catch(e) {{ return {{}}; }}
  }}
  function updateCounter() {{
    var n = document.querySelectorAll('.card.done').length;
    document.getElementById('counter').textContent = '投稿済み ' + n + ' / ' + TOTAL + ' 件';
  }}
  function toggleDone(i) {{
    var card = document.getElementById('card'+i);
    var key = card.getAttribute('data-key');
    var store = doneStore();
    if (card.classList.contains('done')) {{
      card.classList.remove('done'); delete store[key];
    }} else {{
      card.classList.add('done'); store[key] = 1;
    }}
    localStorage.setItem('room_done', JSON.stringify(store));
    updateCounter();
  }}
  // ページを開いたとき、前回までの「投稿済み」を復元
  (function() {{
    var store = doneStore();
    document.querySelectorAll('.card').forEach(function(card) {{
      if (store[card.getAttribute('data-key')]) card.classList.add('done');
    }});
    updateCounter();
  }})();
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
