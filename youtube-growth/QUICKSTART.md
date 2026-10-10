# ⚡ かんたんスタート（鍵1つだけ・約5分）

これだけで毎朝の分析が動きます。むずかしい「鍵2」は**やらなくてOK**です。

---

## ステップ1：APIキーを作る（3分）

1. スマホかパソコンでこのページを開く（チャンネルのGoogleアカウントでログイン）

```
https://console.cloud.google.com/apis/library/youtube.googleapis.com
```

2. 「プロジェクトを選択」と出たら →「新しいプロジェクト」→ 名前に `yt-growth` と入れて「作成」
3. **「有効にする」**（青いボタン）を押す
4. 次のページを開く

```
https://console.cloud.google.com/apis/credentials
```

5. 上の **「＋認証情報を作成」** →「**APIキー**」を押す
6. 出てきた長い文字（`AIza...` ではじまる）を **コピー**

---

## ステップ2：GitHub に貼る（1分）

1. 次のページを開く

```
https://github.com/gk-analyst-site/gk-analyst-site/settings/secrets/actions/new
```

2. **Name** にこれを貼る

```
YT_API_KEY
```

3. **Secret** にステップ1でコピーしたキーを貼る
4. 「**Add secret**」を押す

---

## ステップ3：動かす（1分）

1. このしくみを main ブランチに入れる（プルリクエストをマージ）
2. 次のページを開く

```
https://github.com/gk-analyst-site/gk-analyst-site/actions/workflows/youtube-growth-daily.yml
```

3. 「**Run workflow**」→「**Run workflow**」を押す
4. 1〜2分で緑のチェックになったら完成！

---

## 毎朝見るところ

```
https://github.com/gk-analyst-site/gk-analyst-site/blob/main/youtube-growth/output/today.html
```

以後は**毎朝6:30に自動で更新**されます。あなたは何もしなくてOK。

> もっと詳しく（視聴率・流入元など）見たくなったら、README.md の「鍵2」をあとから足せます。
