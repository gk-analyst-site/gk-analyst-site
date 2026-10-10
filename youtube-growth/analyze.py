# -*- coding: utf-8 -*-
"""
YouTube 毎朝の成長チェック（方向性きめ係）
==========================================
このプログラムがやること（全部じどう）:
  1. YouTube の「公式API」から、チャンネルと全動画の数字（再生・高評価・コメント・長さ・投稿日）を集める
  2. （鍵があれば）YouTube アナリティクスから「視聴時間・平均視聴率・登録者が増えた動画・どこから来たか」も集める
  3. 毎日の数字を history/ に保存して「昨日からどれだけ増えたか」を計算する
  4. 「どんな動画が伸びているか」を自動で分析する
       - ショート vs 長い動画 / 投稿した曜日・時間 / タイトルの型 / よく伸びたタグ / 投稿ペース
  5. 分析結果と「これまでの方針メモ」をもとに、今日の方向性（やること3つ・次の動画案・ためす実験）を決める
  6. スマホで見やすい output/today.html と、方針の日記 history/direction-log.md を作る

あなたがやること:
  - 毎朝 output/today.html を開いて「今日やること」を読むだけ。

鍵（キー）がまだ無くても、デモモードで動きます（サンプルの数字で中身を体験できます）。
"""

import os
import re
import json
import html
import glob
import statistics
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# 【設定】ここだけ変えれば、あなた好みにカスタマイズできます
# ---------------------------------------------------------------------------

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
            os.environ.setdefault(key.strip(), value.strip())

_load_local_keys()

# 分析するチャンネル（Studio の URL の /channel/ のうしろの文字）
CHANNEL_ID = os.environ.get("YT_CHANNEL_ID", "").strip() or "UCB_GT1-6OmO_A9GrT2M5f4g"

# 鍵1: 公開データ用の「APIキー」（必須。無ければデモモード）
YT_API_KEY = os.environ.get("YT_API_KEY", "").strip()

# 鍵2: アナリティクス用（任意。あると視聴維持率や流入元まで分かる）
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "").strip()
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "").strip()
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "").strip()

# 鍵3: 方向性の文章を書く係（任意。無ければルールで方向性を決める）
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = "claude-opus-5-5"

# この秒数以下の動画を「ショート」とみなす（ショートは最大3分）
SHORT_MAX_SECONDS = 180

# 何本まで動画をさかのぼるか（多すぎるとAPIの使用量が増える）
MAX_VIDEOS = 500

# 分析の目標（READMEで説明。自由に書き換えてOK）
GOAL = os.environ.get("YT_GOAL", "").strip() or "チャンネル登録者を増やし、見てくれた人の役に立つ動画を続けて出す"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "history", "snapshots")
DIRECTION_LOG = os.path.join(BASE_DIR, "history", "direction-log.md")
DIRECTION_JSON = os.path.join(BASE_DIR, "history", "directions.json")

JST = timezone(timedelta(hours=9))
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

DATA_API = "https://www.googleapis.com/youtube/v3/"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"
TOKEN_URL = "https://oauth2.googleapis.com/token"


# ---------------------------------------------------------------------------
# 部品1: インターネットからデータを取る
# ---------------------------------------------------------------------------
def http_json(url, params=None, headers=None, data=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "yt-growth/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from None


def yt(endpoint, **params):
    params["key"] = YT_API_KEY
    return http_json(DATA_API + endpoint, params)


def parse_duration(iso):
    """'PT1H2M3S' → 3723 秒"""
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def fetch_public_data():
    """チャンネル情報と全動画の数字を公式APIから集める。"""
    ch = yt("channels", part="snippet,statistics,contentDetails,brandingSettings", id=CHANNEL_ID)
    if not ch.get("items"):
        raise RuntimeError(f"チャンネルが見つかりません: {CHANNEL_ID}")
    c = ch["items"][0]
    stats = c.get("statistics", {})
    channel = {
        "id": CHANNEL_ID,
        "title": c["snippet"].get("title", ""),
        "description": c["snippet"].get("description", "")[:600],
        "keywords": c.get("brandingSettings", {}).get("channel", {}).get("keywords", ""),
        "published_at": c["snippet"].get("publishedAt", ""),
        "subscribers": int(stats.get("subscriberCount", 0) or 0),
        "views": int(stats.get("viewCount", 0) or 0),
        "video_count": int(stats.get("videoCount", 0) or 0),
    }
    uploads = c["contentDetails"]["relatedPlaylists"]["uploads"]

    # アップロード一覧から動画IDを集める
    ids, token = [], None
    while len(ids) < MAX_VIDEOS:
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if token:
            p["pageToken"] = token
        page = yt("playlistItems", **p)
        ids += [it["contentDetails"]["videoId"] for it in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break

    # 50本ずつ、動画の詳しい数字を取る
    videos = []
    for i in range(0, len(ids), 50):
        page = yt("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50]))
        for v in page.get("items", []):
            st = v.get("statistics", {})
            videos.append({
                "id": v["id"],
                "title": v["snippet"].get("title", ""),
                "published_at": v["snippet"].get("publishedAt", ""),
                "tags": v["snippet"].get("tags", [])[:20],
                "duration": parse_duration(v["contentDetails"].get("duration")),
                "views": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                "comments": int(st.get("commentCount", 0) or 0),
            })
    return channel, videos


def get_access_token():
    res = http_json(TOKEN_URL, data={
        "client_id": YT_CLIENT_ID,
        "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    })
    return res["access_token"]


def analytics_report(token, start, end, metrics, dimensions=None, sort=None, max_results=None):
    p = {"ids": "channel==MINE", "startDate": start, "endDate": end, "metrics": metrics}
    if dimensions:
        p["dimensions"] = dimensions
    if sort:
        p["sort"] = sort
    if max_results:
        p["maxResults"] = max_results
    res = http_json(ANALYTICS_API, p, headers={"Authorization": f"Bearer {token}"})
    cols = [h["name"] for h in res.get("columnHeaders", [])]
    return [dict(zip(cols, row)) for row in res.get("rows", [])]


def fetch_analytics():
    """YouTubeアナリティクス（Studioの数字）を直近28日分集める。鍵が無ければ None。"""
    if not (YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN):
        return None
    token = get_access_token()
    end = (datetime.now(JST) - timedelta(days=2)).strftime("%Y-%m-%d")  # 直近2日は確定前なので除く
    start = (datetime.now(JST) - timedelta(days=29)).strftime("%Y-%m-%d")
    out = {"start": start, "end": end}
    jobs = {
        "daily": dict(metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost",
                      dimensions="day", sort="day"),
        "videos": dict(metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,shares",
                       dimensions="video", sort="-views", max_results=50),
        "traffic": dict(metrics="views,estimatedMinutesWatched", dimensions="insightTrafficSourceType", sort="-views"),
        "audience": dict(metrics="viewerPercentage", dimensions="ageGroup,gender"),
        "devices": dict(metrics="views", dimensions="deviceType", sort="-views"),
    }
    for name, kw in jobs.items():
        try:
            out[name] = analytics_report(token, start, end, **kw)
        except Exception as e:  # 1つ失敗しても他は続ける
            print(f"  ! アナリティクス {name} の取得に失敗: {e}")
            out[name] = []
    return out


# ---------------------------------------------------------------------------
# 部品2: デモ用のサンプルデータ（鍵が無いとき用）
# ---------------------------------------------------------------------------
def demo_data():
    import random
    rnd = random.Random(datetime.now(JST).strftime("%Y%m%d"))
    now = datetime.now(timezone.utc)
    themes = ["キャッチングの基本", "【保存版】1対1で止めるコツ", "ハイボール処理 3つのポイント",
              "GKの立ち位置はここ！", "逆足キックを伸ばす練習", "パントキックが飛ぶ理由",
              "【小学生GK】怖さをなくす練習", "セービングの着地", "なぜ失点した？試合分析",
              "グローブの選び方", "PKを止める読み方", "ステップワーク5分ドリル"]
    videos = []
    for i in range(40):
        short = rnd.random() < 0.55
        days = rnd.randint(1, 400)
        base = rnd.randint(200, 3000) * (2.5 if short else 1)
        if "【" in themes[i % len(themes)]:
            base *= 1.6
        views = int(base * (1 + days / 120))
        videos.append({
            "id": f"demo{i:03d}",
            "title": themes[i % len(themes)] + ("" if short else "（解説）"),
            "published_at": (now - timedelta(days=days, hours=rnd.randint(0, 23))).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tags": ["ゴールキーパー", "GK", "サッカー"] + (["ショート"] if short else ["練習"]),
            "duration": rnd.randint(15, 59) if short else rnd.randint(300, 1100),
            "views": views,
            "likes": int(views * rnd.uniform(0.01, 0.05)),
            "comments": int(views * rnd.uniform(0.001, 0.006)),
        })
    channel = {"id": CHANNEL_ID, "title": "（デモ）GKチャンネル", "description": "ゴールキーパー向けの練習と解説",
               "keywords": "", "published_at": "2024-01-01T00:00:00Z",
               "subscribers": 1200 + rnd.randint(0, 30), "views": sum(v["views"] for v in videos),
               "video_count": len(videos)}
    return channel, videos


# ---------------------------------------------------------------------------
# 部品3: 毎日の記録（スナップショット）
# ---------------------------------------------------------------------------
def save_snapshot(today, channel, videos):
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snap = {"date": today, "channel": {k: channel[k] for k in ("subscribers", "views", "video_count")},
            "videos": {v["id"]: [v["views"], v["likes"], v["comments"]] for v in videos}}
    with open(os.path.join(SNAPSHOT_DIR, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, separators=(",", ":"))


def load_snapshots(today):
    snaps = []
    for path in sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        if s.get("date", "") < today:
            snaps.append(s)
    return snaps


# ---------------------------------------------------------------------------
# 部品4: 分析（どんな動画が伸びているか）
# ---------------------------------------------------------------------------
def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else 0


def title_features(t):
    return {
        "数字が入っている": bool(re.search(r"[0-9０-９]", t)),
        "【】で強調": "【" in t or "[" in t,
        "疑問形（？）": "?" in t or "？" in t,
        "「！」で強調": "!" in t or "！" in t,
        "対象を指定（小学生/初心者 など）": bool(re.search(r"小学生|中学生|高校生|初心者|ジュニア|社会人|子ども|親", t)),
        "タイトル30文字以上": len(t) >= 30,
    }


def compare_groups(videos, key_fn, metric="vpd", min_n=2):
    """グループごとの中央値を比べる。metric は 1日あたり再生(vpd) を使う。"""
    groups = defaultdict(list)
    for v in videos:
        k = key_fn(v)
        if k is not None:
            groups[k].append(v[metric])
    return {k: {"n": len(xs), "median": round(median(xs), 1)} for k, xs in groups.items() if len(xs) >= min_n}


def analyze(channel, videos, snaps, analytics, now):
    for v in videos:
        pub = datetime.strptime(v["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        v["pub_jst"] = pub.astimezone(JST)
        v["age_days"] = max((now - pub).total_seconds() / 86400, 0.5)
        v["vpd"] = v["views"] / v["age_days"]
        v["engagement"] = (v["likes"] + v["comments"]) / v["views"] * 100 if v["views"] else 0
        v["is_short"] = v["duration"] <= SHORT_MAX_SECONDS

    mature = [v for v in videos if v["age_days"] >= 7] or videos
    base_views = median(v["views"] for v in mature) or 1
    for v in videos:
        v["score"] = round(v["views"] / base_views, 2)  # チャンネルの“ふつう”の何倍か

    # 昨日からの伸び
    prev = snaps[-1] if snaps else None
    delta = None
    if prev:
        days = max((datetime.strptime(now.astimezone(JST).strftime("%Y-%m-%d"), "%Y-%m-%d")
                    - datetime.strptime(prev["date"], "%Y-%m-%d")).days, 1)
        delta = {
            "since": prev["date"], "days": days,
            "subscribers": channel["subscribers"] - prev["channel"]["subscribers"],
            "views": channel["views"] - prev["channel"]["views"],
        }
        for v in videos:
            old = prev["videos"].get(v["id"])
            v["views_gain"] = (v["views"] - old[0]) if old else v["views"]
        delta["rising"] = [slim(v) for v in sorted(videos, key=lambda x: -x.get("views_gain", 0))[:5]
                           if v.get("views_gain", 0) > 0]

    # 7日前・30日前との比較（スナップショットがあるとき）
    trend = {}
    by_date = {s["date"]: s for s in snaps}
    for label, d in (("7日", 7), ("30日", 30)):
        key = (now.astimezone(JST) - timedelta(days=d)).strftime("%Y-%m-%d")
        old = by_date.get(key) or next((s for s in reversed(snaps) if s["date"] <= key), None)
        if old:
            trend[label] = {"since": old["date"],
                            "subscribers": channel["subscribers"] - old["channel"]["subscribers"],
                            "views": channel["views"] - old["channel"]["views"]}

    shorts = [v for v in mature if v["is_short"]]
    longs = [v for v in mature if not v["is_short"]]
    fmt = {
        "ショート": {"n": len(shorts), "median_views": round(median(v["views"] for v in shorts)),
                    "median_vpd": round(median(v["vpd"] for v in shorts), 1),
                    "median_engagement": round(median(v["engagement"] for v in shorts), 2)},
        "長い動画": {"n": len(longs), "median_views": round(median(v["views"] for v in longs)),
                    "median_vpd": round(median(v["vpd"] for v in longs), 1),
                    "median_engagement": round(median(v["engagement"] for v in longs), 2)},
    }

    # 曜日・時間帯（日本時間）。比べやすいように「ふつうの何倍か(score)」で比べる
    weekday = compare_groups(mature, lambda v: WEEKDAYS[v["pub_jst"].weekday()], metric="score")
    hour = compare_groups(mature, lambda v: f"{v['pub_jst'].hour // 3 * 3:02d}-{v['pub_jst'].hour // 3 * 3 + 3:02d}時",
                          metric="score")

    title = {}
    for feat in title_features("").keys():
        yes = [v["score"] for v in mature if title_features(v["title"])[feat]]
        no = [v["score"] for v in mature if not title_features(v["title"])[feat]]
        if len(yes) >= 2 and len(no) >= 2:
            title[feat] = {"あり": round(median(yes), 2), "なし": round(median(no), 2), "n": len(yes)}

    # 伸びた動画に多いタグ
    ranked = sorted(mature, key=lambda v: -v["score"])
    top_n = max(len(ranked) // 4, 3)
    top_tags = Counter(t for v in ranked[:top_n] for t in v["tags"])
    all_tags = Counter(t for v in mature for t in v["tags"])
    tag_lift = sorted(((t, c, all_tags[t]) for t, c in top_tags.items() if all_tags[t] >= 2),
                      key=lambda x: -(x[1] / x[2]))[:10]

    recent30 = [v for v in videos if v["age_days"] <= 30]
    last = min(videos, key=lambda v: v["age_days"]) if videos else None
    cadence = {
        "uploads_30d": len(recent30),
        "shorts_30d": sum(v["is_short"] for v in recent30),
        "days_since_last": round(last["age_days"], 1) if last else None,
        "last_title": last["title"] if last else "",
    }

    result = {
        "channel": channel,
        "base_views": round(base_views),
        "delta": delta,
        "trend": trend,
        "format": fmt,
        "weekday": weekday,
        "hour": hour,
        "title": title,
        "tag_lift": [{"tag": t, "top": c, "all": a} for t, c, a in tag_lift],
        "cadence": cadence,
        "top": [slim(v) for v in ranked[:8]],
        "bottom": [slim(v) for v in ranked[-5:]] if len(ranked) > 10 else [],
        "recent": [slim(v) for v in sorted(videos, key=lambda v: v["age_days"])[:8]],
        "analytics": summarize_analytics(analytics, videos),
        "history": [{"date": s["date"], "subscribers": s["channel"]["subscribers"], "views": s["channel"]["views"]}
                    for s in snaps[-60:]],
    }
    return result


def slim(v):
    return {"id": v["id"], "title": v["title"], "views": v["views"], "score": v.get("score"),
            "vpd": round(v["vpd"], 1), "engagement": round(v["engagement"], 2), "short": v["is_short"],
            "age_days": round(v["age_days"], 1), "published": v["pub_jst"].strftime("%Y-%m-%d %a %H:%M"),
            "gain": v.get("views_gain")}


TRAFFIC_JA = {
    "YT_SEARCH": "YouTube検索", "SUGGESTED": "関連動画", "BROWSE": "ホーム/登録チャンネル",
    "SHORTS": "ショートフィード", "EXT_URL": "外部サイト/SNS", "NO_LINK_OTHER": "直接/不明",
    "PLAYLIST": "再生リスト", "CHANNEL": "チャンネルページ", "NOTIFICATION": "通知",
    "SUBSCRIBER": "登録者フィード", "END_SCREEN": "終了画面", "ANNOTATION": "カード",
    "HASHTAGS": "ハッシュタグ", "RELATED_VIDEO": "関連動画", "YT_OTHER_PAGE": "YouTubeのその他",
    "SOUND_PAGE": "サウンドページ", "LIVE_REDIRECT": "ライブ", "CAMPAIGN_CARD": "キャンペーン",
    "VIDEO_REMIXES": "リミックス", "IMMERSIVE_LIVE": "ライブ",
}


def summarize_analytics(a, videos):
    if not a:
        return None
    titles = {v["id"]: v["title"] for v in videos}
    daily = a.get("daily", [])
    tot_views = sum(r.get("views", 0) for r in daily)
    out = {
        "period": f"{a['start']} 〜 {a['end']}",
        "views_28d": tot_views,
        "watch_hours_28d": round(sum(r.get("estimatedMinutesWatched", 0) for r in daily) / 60, 1),
        "subs_net_28d": sum(r.get("subscribersGained", 0) - r.get("subscribersLost", 0) for r in daily),
        "avg_view_duration_sec": round(median(r.get("averageViewDuration") for r in daily)),
        "daily": [{"day": r["day"], "views": r.get("views", 0),
                   "subs": r.get("subscribersGained", 0) - r.get("subscribersLost", 0)} for r in daily],
        "traffic": [{"source": TRAFFIC_JA.get(r["insightTrafficSourceType"], r["insightTrafficSourceType"]),
                     "views": r["views"],
                     "share": round(r["views"] / tot_views * 100, 1) if tot_views else 0}
                    for r in a.get("traffic", [])[:8]],
        "devices": [{"device": r["deviceType"], "views": r["views"]} for r in a.get("devices", [])],
        "audience": sorted([{"age": r["ageGroup"].replace("age", ""), "gender": r["gender"],
                             "pct": round(r["viewerPercentage"], 1)} for r in a.get("audience", [])],
                           key=lambda x: -x["pct"])[:6],
    }
    vids = []
    for r in a.get("videos", []):
        vids.append({"title": titles.get(r["video"], r["video"]), "views": r["views"],
                     "avg_view_pct": round(r.get("averageViewPercentage", 0), 1),
                     "avg_view_sec": r.get("averageViewDuration", 0),
                     "subs_gained": r.get("subscribersGained", 0), "shares": r.get("shares", 0)})
    out["videos"] = vids[:15]
    out["best_retention"] = sorted([v for v in vids if v["views"] >= 50], key=lambda v: -v["avg_view_pct"])[:5]
    out["best_subscribe"] = sorted(vids, key=lambda v: -v["subs_gained"])[:5]
    return out


# ---------------------------------------------------------------------------
# 部品5: ルールで決める方向性（鍵が無くても必ず動く）
# ---------------------------------------------------------------------------
def rule_direction(r):
    actions, notes = [], []
    f = r["format"]
    s, l = f["ショート"], f["長い動画"]
    if s["n"] >= 3 and l["n"] >= 3:
        if s["median_vpd"] > l["median_vpd"] * 1.5:
            notes.append(f"ショートは長い動画の約{s['median_vpd'] / max(l['median_vpd'], 0.1):.1f}倍のペースで見られている。")
            actions.append("ショートを週3本以上出し、説明欄と固定コメントで関連する長い動画へ誘導する")
        elif l["median_vpd"] > s["median_vpd"] * 1.2:
            notes.append("長い動画のほうが1日あたりの再生が多い。検索・関連動画で長く見られている。")
            actions.append("伸びた長い動画と同じテーマの『続編・応用編』を1本つくる")

    c = r["cadence"]
    if c["days_since_last"] is not None and c["days_since_last"] > 7:
        actions.insert(0, f"最後の投稿から{c['days_since_last']:.0f}日空いている。まず今週中に1本出す（ショートでOK）")
    elif c["uploads_30d"] < 8:
        notes.append(f"直近30日の投稿は{c['uploads_30d']}本。伸び始めのチャンネルは週2本以上が目安。")

    if r["weekday"]:
        best = max(r["weekday"].items(), key=lambda kv: kv[1]["median"])
        notes.append(f"{best[0]}曜日に出した動画がいちばん伸びやすい（ふつうの{best[1]['median']}倍）。")
    if r["hour"]:
        best = max(r["hour"].items(), key=lambda kv: kv[1]["median"])
        notes.append(f"投稿時間は {best[0]} が好成績。")

    good_titles = [k for k, v in r["title"].items() if v["あり"] > v["なし"] * 1.2]
    if good_titles:
        actions.append("次のタイトルは「" + "」「".join(good_titles[:2]) + "」の型を使う")

    if r["top"]:
        t = r["top"][0]
        actions.append(f"いちばん伸びた「{t['title']}」（ふつうの{t['score']}倍）の“別角度バージョン”を企画する")

    a = r.get("analytics")
    if a and a["traffic"]:
        src = a["traffic"][0]
        notes.append(f"再生の入口の1位は「{src['source']}」（{src['share']}%）。")
        if src["source"] == "YouTube検索":
            actions.append("検索で見つけてもらえている。悩みそのままの言葉をタイトルの先頭に置く")
        elif src["source"] in ("ショートフィード",):
            actions.append("ショートの最初の1秒に『答え』か『失敗シーン』を置いてスワイプを止める")
    if a and a["best_subscribe"]:
        notes.append(f"登録者をいちばん増やした動画は「{a['best_subscribe'][0]['title']}」。")

    while len(actions) < 3:
        actions.append(["コメント欄の質問から次の動画テーマを1つ選ぶ",
                        "サムネイルの文字を7文字以内にして大きく見せる",
                        "動画の最後で『次に見る動画』を1本だけ案内する"][len(actions) % 3])
    return {
        "headline": "数字から見た今日の方向性",
        "summary": " ".join(notes) or "まだデータが少ないので、まずは投稿を続けて記録をためる段階です。",
        "today_actions": actions[:3],
        "next_videos": [],
        "experiment": None,
        "stop_doing": [],
        "source": "rule",
    }


# ---------------------------------------------------------------------------
# 部品6: Claude に方向性を決めてもらう（鍵があるとき）
# ---------------------------------------------------------------------------
def load_past_directions(n=7):
    try:
        with open(DIRECTION_JSON, encoding="utf-8") as f:
            return json.load(f)[-n:]
    except Exception:
        return []


def claude_direction(r, past):
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
    except ImportError:
        print("  ! anthropic ライブラリが無いのでルールで方向性を決めます（pip install anthropic）")
        return None

    data = {k: v for k, v in r.items() if k != "history"}
    prompt = f"""あなたはYouTubeチャンネルの成長コンサルタントです。毎朝、最新の数字を見て「今日の方向性」を決めます。

# チャンネルの目標
{GOAL}

# 今日のデータ（JSON）
- score = チャンネルの“ふつう”(7日以上たった動画の再生中央値)の何倍再生されたか
- vpd = 1日あたり再生数 / engagement = (高評価+コメント)/再生 %
- weekday/hour = 投稿した曜日・時間帯ごとの score 中央値
- analytics = YouTubeアナリティクス直近28日（null なら未接続）
```json
{json.dumps(data, ensure_ascii=False, default=str)}
```

# これまでの方針（古い→新しい）
```json
{json.dumps(past, ensure_ascii=False)}
```

# お願い
1. 前回までの方針・実験が数字にどう出たかを、まず一言で評価してください（初回なら「初回」）。
2. データに根拠のあることだけを言ってください。推測のときは「仮説」と書いてください。
3. 方針は毎日ころころ変えず、根拠が変わったときだけ変えてください。
4. 今日1日でできる具体的な行動にしてください。

次のJSONだけを返してください（説明文やコードブロックは不要）:
{{
  "headline": "今日の方向性を20文字前後で",
  "review": "前回の方針・実験の評価（1〜2文）",
  "summary": "数字から分かったこと（3文以内）",
  "today_actions": ["今日やること1", "今日やること2", "今日やること3"],
  "next_videos": [{{"title": "動画タイトル案", "format": "ショート or 長い動画", "why": "根拠"}}, ... 3本],
  "experiment": {{"hypothesis": "ためす仮説", "how": "やり方", "measure": "何の数字が何日後にどうなれば成功か"}},
  "stop_doing": ["やめること（無ければ空配列）"],
  "weekly_focus": "今週ずっと意識すること1つ"
}}"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        print("  ! 方向性の作成が断られたので、ルールで決めます")
        return None
    text = "".join(b.text for b in resp.content if b.type == "text")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("方向性のJSONが見つかりません")
    d = json.loads(text[start:end + 1])
    d["source"] = "claude"
    return d


def record_direction(today, d):
    os.makedirs(os.path.dirname(DIRECTION_JSON), exist_ok=True)
    allp = load_past_directions(n=10_000)
    allp = [p for p in allp if p.get("date") != today]
    allp.append({"date": today, **{k: d.get(k) for k in ("headline", "today_actions", "experiment", "weekly_focus")}})
    with open(DIRECTION_JSON, "w", encoding="utf-8") as f:
        json.dump(allp[-120:], f, ensure_ascii=False, indent=1)

    lines = [f"## {today}　{d.get('headline', '')}", ""]
    if d.get("review"):
        lines.append(f"- 前回の評価: {d['review']}")
    lines.append(f"- 分かったこと: {d.get('summary', '')}")
    for a in d.get("today_actions", []):
        lines.append(f"- [ ] {a}")
    if d.get("experiment"):
        e = d["experiment"]
        lines.append(f"- 実験: {e.get('hypothesis', '')} → {e.get('measure', '')}")
    lines.append("")
    old = ""
    if os.path.exists(DIRECTION_LOG):
        with open(DIRECTION_LOG, encoding="utf-8") as f:
            old = f.read()
        old = re.sub(rf"## {today}.*?(?=\n## |\Z)", "", old, flags=re.S).replace("# 方向性の日記\n\n", "")
    with open(DIRECTION_LOG, "w", encoding="utf-8") as f:
        f.write("# 方向性の日記\n\n" + "\n".join(lines) + "\n" + old.lstrip())


# ---------------------------------------------------------------------------
# 部品7: スマホで見やすいページを作る
# ---------------------------------------------------------------------------
def esc(x):
    return html.escape(str(x))


def fmt_num(n):
    return f"{n:,}" if isinstance(n, int) else str(n)


def signed(n):
    return f"+{n:,}" if n > 0 else f"{n:,}"


def sparkline(values, w=320, h=60):
    if len(values) < 2:
        return '<p class="muted">グラフは2日分たまると表示されます。</p>'
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(values) - 1):.1f},{h - 4 - (v - lo) / rng * (h - 8):.1f}"
                   for i, v in enumerate(values))
    return (f'<svg viewBox="0 0 {w} {h}" class="spark" preserveAspectRatio="none" role="img" '
            f'aria-label="推移"><polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2"/></svg>')


def bars(d, label_fmt="{:.2f}倍"):
    if not d:
        return '<p class="muted">データがまだ足りません。</p>'
    mx = max(v["median"] for v in d.values()) or 1
    rows = []
    for k, v in sorted(d.items(), key=lambda kv: -kv[1]["median"]):
        pct = v["median"] / mx * 100
        rows.append(f'<div class="bar"><span class="bl">{esc(k)}</span><span class="bt">'
                    f'<i style="width:{pct:.0f}%"></i></span><span class="bv">{label_fmt.format(v["median"])}'
                    f' <small>({v["n"]}本)</small></span></div>')
    return "".join(rows)


def video_rows(vs, extra=None):
    out = []
    for v in vs:
        tag = '<b class="pill s">ショート</b>' if v.get("short") else '<b class="pill l">長い動画</b>'
        ex = extra(v) if extra else f'ふつうの <b>{v["score"]}倍</b>'
        link = "" if v["id"].startswith("demo") else f' href="https://www.youtube.com/watch?v={esc(v["id"])}"'
        out.append(f'<li><a{link}>{esc(v["title"])}</a><div class="meta">{tag} {fmt_num(v["views"])}回 ・ '
                   f'{ex} ・ {esc(v["published"])}</div></li>')
    return "<ol class='vids'>" + "".join(out) + "</ol>"


def render_html(r, d, mode, today):
    ch = r["channel"]
    delta = r["delta"]
    kpi = [("登録者", fmt_num(ch["subscribers"]), signed(delta["subscribers"]) if delta else "—"),
           ("総再生", fmt_num(ch["views"]), signed(delta["views"]) if delta else "—"),
           ("動画数", fmt_num(ch["video_count"]), f'30日で{r["cadence"]["uploads_30d"]}本')]
    kpi_html = "".join(f'<div class="kpi"><span>{a}</span><b>{b}</b><small>{c}</small></div>' for a, b, c in kpi)

    trend = "".join(f'<li>{k}前({esc(v["since"])})から 登録者 <b>{signed(v["subscribers"])}</b> ・ 再生 '
                    f'<b>{signed(v["views"])}</b></li>' for k, v in r["trend"].items())

    actions = "".join(f"<li>{esc(a)}</li>" for a in d.get("today_actions", []))
    ideas = "".join(f'<li><b>{esc(i.get("title", ""))}</b> <span class="pill">{esc(i.get("format", ""))}</span>'
                    f'<div class="meta">{esc(i.get("why", ""))}</div></li>' for i in d.get("next_videos", []))
    exp = d.get("experiment")
    exp_html = (f'<p><b>仮説：</b>{esc(exp.get("hypothesis", ""))}</p><p><b>やり方：</b>{esc(exp.get("how", ""))}</p>'
                f'<p><b>成功の目安：</b>{esc(exp.get("measure", ""))}</p>') if exp else ""
    stop = "".join(f"<li>{esc(s)}</li>" for s in d.get("stop_doing", []))

    f = r["format"]
    fmt_html = "".join(f'<div class="kpi"><span>{k}（{v["n"]}本）</span><b>{fmt_num(v["median_views"])}回</b>'
                       f'<small>1日{v["median_vpd"]}回 ・ 反応率{v["median_engagement"]}%</small></div>'
                       for k, v in f.items())

    title_rows = "".join(f'<tr><td>{esc(k)}</td><td>{v["あり"]}倍</td><td>{v["なし"]}倍</td>'
                         f'<td>{"◎" if v["あり"] > v["なし"] * 1.2 else ("×" if v["あり"] < v["なし"] * 0.8 else "ー")}</td></tr>'
                         for k, v in r["title"].items())
    tags = " ".join(f'<span class="pill">#{esc(t["tag"])} {t["top"]}/{t["all"]}</span>' for t in r["tag_lift"])

    rising = ""
    if delta and delta.get("rising"):
        rising = ("<section><h2>📈 昨日から伸びている動画</h2>" +
                  video_rows(delta["rising"], lambda v: f'<b>{signed(v["gain"])}回</b>') + "</section>")

    a = r.get("analytics")
    if a:
        traffic = "".join(f'<div class="bar"><span class="bl">{esc(t["source"])}</span><span class="bt">'
                          f'<i style="width:{t["share"]:.0f}%"></i></span><span class="bv">{t["share"]}%</span></div>'
                          for t in a["traffic"])
        ret = "".join(f'<li>{esc(v["title"])}<div class="meta">平均 {v["avg_view_pct"]}% 視聴 ・ {fmt_num(v["views"])}回</div></li>'
                      for v in a["best_retention"])
        sub = "".join(f'<li>{esc(v["title"])}<div class="meta">登録 +{v["subs_gained"]} ・ {fmt_num(v["views"])}回</div></li>'
                      for v in a["best_subscribe"])
        aud = " ".join(f'<span class="pill">{esc(x["age"])}歳 {esc(x["gender"])} {x["pct"]}%</span>' for x in a["audience"])
        analytics_html = f"""<section><h2>🔍 アナリティクス（{esc(a['period'])}）</h2>
<div class="kpis"><div class="kpi"><span>再生</span><b>{fmt_num(a['views_28d'])}</b></div>
<div class="kpi"><span>総再生時間</span><b>{a['watch_hours_28d']}h</b></div>
<div class="kpi"><span>登録者(純増)</span><b>{signed(a['subs_net_28d'])}</b></div></div>
{sparkline([x['views'] for x in a['daily']])}
<h3>どこから見に来たか</h3>{traffic}
<h3>最後まで見られている動画</h3><ol class="vids">{ret}</ol>
<h3>登録者を増やした動画</h3><ol class="vids">{sub}</ol>
<h3>見ている人</h3><p>{aud or '<span class="muted">データなし</span>'}</p></section>"""
    else:
        analytics_html = ('<section><h2>🔍 アナリティクス</h2><p class="muted">未接続です。README の「鍵2」を設定すると、'
                          '平均視聴率・流入元・登録者が増えた動画まで分析できます。</p></section>')

    banner = {"demo": '<p class="banner">デモモード（サンプルの数字）です。README の「鍵1」を設定すると本物の数字になります。</p>',
              "public": "", "full": ""}[mode]
    src = "数字の分析＋文章作成" if d.get("source") == "claude" else "数字のルール判定"
    hist = r["history"] + [{"subscribers": ch["subscribers"], "views": ch["views"]}]

    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YouTube 成長チェック</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;--muted:#69707a;--line:#e3e6ea;--accent:#d93025;--soft:#fdecea}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#111315;--card:#1a1d21;--fg:#e8eaed;--muted:#9aa0a6;--line:#2c3036;--accent:#ff6b5e;--soft:#3a1f1d}}}}
:root[data-theme="dark"]{{--bg:#111315;--card:#1a1d21;--fg:#e8eaed;--muted:#9aa0a6;--line:#2c3036;--accent:#ff6b5e;--soft:#3a1f1d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:16px}}h1{{font-size:20px;margin:4px 0}}h2{{font-size:17px;margin:0 0 10px}}h3{{font-size:14px;margin:16px 0 6px;color:var(--muted)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:14px 0}}
.hero{{border-color:var(--accent);background:var(--soft)}}.hero h2{{font-size:19px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}}.kpi span{{display:block;color:var(--muted);font-size:12px}}
.kpi b{{font-size:20px}}.kpi small{{display:block;color:var(--muted)}}
.muted,.meta{{color:var(--muted);font-size:13px}}.banner{{background:#fff4d6;color:#5c4400;padding:8px 12px;border-radius:10px}}
ol,ul{{padding-left:20px}}li{{margin:6px 0}}.vids a{{color:var(--fg);text-decoration:none;font-weight:600}}
.pill{{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:0 8px;font-size:12px;font-weight:400;margin:2px 0}}
.pill.s{{border-color:var(--accent);color:var(--accent)}}
.bar{{display:grid;grid-template-columns:7.5em 1fr 6.5em;gap:8px;align-items:center;font-size:13px;margin:4px 0}}
.bt{{background:var(--line);border-radius:6px;height:10px;overflow:hidden}}.bt i{{display:block;height:100%;background:var(--accent)}}
.bv{{text-align:right}}table{{width:100%;border-collapse:collapse;font-size:13px}}td,th{{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left}}
.spark{{width:100%;height:60px}}.actions li{{font-size:16px;font-weight:600}}
</style></head><body><main>
<p class="muted">{esc(today)} 更新 ・ {esc(ch['title'])}</p>
<h1>📺 YouTube 毎朝の成長チェック</h1>
{banner}
<section class="hero"><h2>🧭 {esc(d.get('headline', ''))}</h2>
{f"<p><b>前回の評価：</b>{esc(d['review'])}</p>" if d.get('review') else ''}
<p>{esc(d.get('summary', ''))}</p>
<h3>今日やること</h3><ol class="actions">{actions}</ol>
{f"<p><b>今週の意識：</b>{esc(d['weekly_focus'])}</p>" if d.get('weekly_focus') else ''}
<p class="muted">判定方法：{src}</p></section>
<div class="kpis">{kpi_html}</div>
<section><h2>📊 登録者の推移</h2>{sparkline([x['subscribers'] for x in hist])}<ul>{trend or '<li class="muted">7日分たまると比較が出ます。</li>'}</ul></section>
{f'<section><h2>🎬 次の動画案</h2><ol>{ideas}</ol></section>' if ideas else ''}
{f'<section><h2>🧪 今週の実験</h2>{exp_html}</section>' if exp_html else ''}
{f'<section><h2>🛑 やめること</h2><ul>{stop}</ul></section>' if stop else ''}
{rising}
<section><h2>🏆 伸びた動画ベスト</h2><p class="muted">“ふつう”＝7日以上たった動画の再生の真ん中（{fmt_num(r['base_views'])}回）</p>{video_rows(r['top'])}</section>
<section><h2>🆕 最近の動画</h2>{video_rows(r['recent'])}</section>
<section><h2>⚖️ ショート vs 長い動画</h2><div class="kpis">{fmt_html}</div></section>
<section><h2>📅 投稿した曜日（ふつうの何倍）</h2>{bars(r['weekday'])}<h3>時間帯（日本時間）</h3>{bars(r['hour'])}</section>
<section><h2>✍️ タイトルの型</h2><table><tr><th>型</th><th>あり</th><th>なし</th><th>判定</th></tr>{title_rows}</table>
<h3>伸びた動画に多いタグ（上位動画での数/全体の数）</h3><p>{tags or '<span class="muted">タグのデータが少ないです</span>'}</p></section>
{analytics_html}
<p class="muted">過去の方針は history/direction-log.md に毎日たまっていきます。</p>
</main></body></html>"""


# ---------------------------------------------------------------------------
# 本体
# ---------------------------------------------------------------------------
def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(JST).strftime("%Y-%m-%d")

    if YT_API_KEY:
        print(f"▶ チャンネル {CHANNEL_ID} のデータを集めています…")
        channel, videos = fetch_public_data()
        mode = "public"
    else:
        print("▶ 鍵(YT_API_KEY)が無いので、デモモードで動かします")
        channel, videos = demo_data()
        mode = "demo"
    print(f"  動画 {len(videos)} 本 / 登録者 {channel['subscribers']:,} 人")

    analytics = None
    if mode == "public":
        try:
            analytics = fetch_analytics()
            if analytics:
                mode = "full"
                print("  アナリティクスも取得しました")
        except Exception as e:
            print(f"  ! アナリティクスに接続できませんでした: {e}")

    snaps = load_snapshots(today) if mode != "demo" else []
    result = analyze(channel, videos, snaps, analytics, now)
    if mode != "demo":
        save_snapshot(today, channel, videos)

    direction = None
    try:
        direction = claude_direction(result, load_past_directions())
    except Exception as e:
        print(f"  ! 方向性の文章づくりに失敗したので、ルールで決めます: {e}")
    if not direction:
        direction = rule_direction(result)
    if mode != "demo":
        record_direction(today, direction)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "today.html"), "w", encoding="utf-8") as f:
        f.write(render_html(result, direction, mode, today))
    with open(os.path.join(OUTPUT_DIR, "today.json"), "w", encoding="utf-8") as f:
        json.dump({"date": today, "mode": mode, "direction": direction, "analysis": result},
                  f, ensure_ascii=False, indent=1, default=str)

    print(f"✅ できました: {os.path.join(OUTPUT_DIR, 'today.html')}")
    print(f"🧭 今日の方向性: {direction.get('headline')}")
    for i, a in enumerate(direction.get("today_actions", []), 1):
        print(f"   {i}. {a}")


if __name__ == "__main__":
    main()
