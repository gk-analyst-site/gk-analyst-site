# J4K Instagram 自動投稿

Just4Keepers Japan（J4K）の Instagram に、毎日1回 **AIがキャプションを生成して自動投稿** する仕組みです。

- **実行場所**: GitHub Actions（サーバー不要・無料枠）
- **スケジュール**: 毎日 JST 09:00（`.github/workflows/instagram-daily.yml` の cron で変更可）
- **キャプション**: Claude が画像を見て日本語キャプション＋ハッシュタグを生成
- **投稿方式**: `content/images/` に入れた画像を、キュー（`content/queue.json`）の順に1日1枚投稿

---

## 仕組み

1. `content/queue.json` から未投稿（`"posted": false`）の投稿を1件選ぶ
2. その画像を Claude に渡してキャプションを生成
3. Instagram Graph API で投稿
4. `queue.json` に `posted: true` と結果を記録してコミット

---

## セットアップ（初回のみ）

### 1. Instagram の準備

Instagram Graph API での投稿には以下が必要です：

- Instagram の **ビジネス** または **クリエイター** アカウント
- そのアカウントに連携された **Facebookページ**
- [Meta for Developers](https://developers.facebook.com/) でアプリを作成
- **長期アクセストークン（long-lived access token）** と **Instagram Business Account ID**

参考：Meta 公式ドキュメント「[Instagram API with Instagram Login / Content Publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)」

> 取得した長期トークンは約60日で失効します。失効前に更新（再取得）して、下記の `IG_ACCESS_TOKEN` を差し替えてください。

### 2. GitHub Secrets を登録

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で以下を登録します：

| Secret 名 | 内容 |
| --- | --- |
| `ANTHROPIC_API_KEY` | Claude（Anthropic）の API キー |
| `IG_USER_ID` | Instagram Business Account ID |
| `IG_ACCESS_TOKEN` | 長期アクセストークン |

### 3. リポジトリを Public にする（重要）

Instagram Graph API は投稿画像を **公開URL** から取得します。この仕組みは既定で
`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/instagram-bot/content/images/<file>`
を使うため、**リポジトリが Public である必要があります**。

Private のまま運用したい場合は、画像を別の公開ストレージ（S3 / Cloudinary など）に置き、
Actions の env に `IMAGE_BASE_URL`（画像フォルダの公開URLのベース）を設定してください。

---

## 使い方（日々の運用）

1. 投稿したい画像を `content/images/` に追加（jpg / png / webp）
2. `content/queue.json` の `posts` 配列に項目を追加：

   ```json
   {
     "image": "training_20260716.jpg",
     "context": "シュートストップの反応スピード強化ドリル",
     "posted": false
   }
   ```

   - `image`: `content/images/` 内のファイル名と一致させる
   - `context`: 任意。画像の補足（AIキャプションの精度が上がります）
   - `posted`: `false` のままにしておく（投稿後に自動で `true` になります）
3. コミット & プッシュ。あとは毎日1件ずつ自動投稿されます。

キューが空（全部 `posted: true`）になると、その日は何もせず終了します。

---

## 手動でテスト実行

GitHub の **Actions → J4K Instagram daily post → Run workflow** から手動実行できます。

ローカルで試す場合：

```bash
cd instagram-bot
npm install
export ANTHROPIC_API_KEY=...
export IG_USER_ID=...
export IG_ACCESS_TOKEN=...
export IMAGE_BASE_URL="https://raw.githubusercontent.com/<owner>/<repo>/main/instagram-bot/content/images"
npm run post
```

---

## カスタマイズ

- **投稿時刻**: `.github/workflows/instagram-daily.yml` の `cron`（UTC）
- **キャプションのトーン・言語・ハッシュタグ**: `lib/caption.js` の `BRAND_CONTEXT`
- **使用モデル**: `lib/caption.js` の `model`（既定 `claude-opus-4-8`）
