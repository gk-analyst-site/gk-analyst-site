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

**画像を `content/images/` にまとめて入れるだけ。** あとは毎日1枚ずつ、ファイル名の順に自動投稿されます。リストの手動編集は不要です。

1. 投稿したい画像を `content/images/` にアップロード（jpg / png / webp）
2. コミット & プッシュ

- **投稿順**：ファイル名の昇順（例：`01.jpg` → `02.jpg` → `10.jpg`）。順番を決めたいときは `01_`, `02_`… と番号を付けてください。
- **投稿済みの管理**：投稿された画像は `content/posted.json` に自動で記録され、二度と投稿されません（この記録は自動でコミットされます）。
- **未投稿がなくなった日**：その日は何もせず終了します。次の画像を入れれば再開します。

### 任意：画像に補足（コンテキスト）を付けたいとき

AIキャプションの精度を上げたい場合は、`content/context.json`（任意）にファイル名→補足のメモを書けます。無ければ無視されます。

```json
{
  "01_training.jpg": "シュートストップの反応スピード強化ドリル",
  "02_match.jpg": "公式戦でのビッグセーブ"
}
```

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
