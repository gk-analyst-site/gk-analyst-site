# 引き継ぎメモ / Handoff (instagram-bot)

このリポジトリ (`gk-analyst-site/gk-analyst-site`) を別の Claude Code セッションで開けば、
コードも状態もすべて引き継げます。作業ディレクトリは `instagram-bot/`、デフォルトブランチは `main`。
Node.js (ESM)。依存: `@anthropic-ai/sdk`, `@napi-rs/canvas`。

新しいセッションでの進め方: このファイルを読んでから「## 残タスク」を上から進めてください。

---

## ✅ 稼働中（触らない）: 毎日の写真自動投稿

- 投稿先: Instagram **@just4keepers_japan**（J4K）
- ワークフロー: `.github/workflows/instagram-daily.yml`（cron `0 0 * * *` UTC = 毎日 JST 09:00、手動実行可）
- 動作: `content/images/` の画像をファイル名順に1日1枚、Claude(vision)がキャプション生成 → Graph APIで投稿 → `content/posted.json` に記録して自動コミット。任意の補足は `content/context.json`。
- コード: `post.js`, `lib/caption.js`(model `claude-opus-4-8`, 価格等の数字は捏造しない指示), `lib/instagram.js`(コンテナ作成→FINISHED待ち→publish、9007リトライ)
- GitHub Secrets: `ANTHROPIC_API_KEY`, `IG_USER_ID` = `17841400295285771`, `IG_ACCESS_TOKEN`(Just4keepers Japan ページ [id `420902401338436`] の無期限ページトークン)
- リポジトリは Public（Graph API が raw.githubusercontent.com から画像取得するため）

---

## 🔧 制作中(WIP): KEEPIX 教育系カルーセル投稿（新機能）

GKノウハウ記事を「文字入りスライドのスワイプ式カルーセル」で発信する新機能。写真投稿とは別枠。

### 決定済みの仕様
- 投稿先: **@KEEPIX.GK_OFFICIAL**（J4Kとは**別アカウント / 別トークンが必要**）
- スケジュール: **月・水・金** の JST 09:00（写真の毎日投稿はそのまま）
- 小出し: 長い記事を **Part 1 / 2 / 3**（1回あたり4〜6枚）の連載に自動分割
- 言語: 日本語＆英語の両対応
- デザイン: `lib/slides.js`（1080×1350、KEEPIXブランド）。ユーザー承認済み。
  - 背景 `#0B1512` / アクセント(ミント緑) `#5FE3A1` / 本文 `#D7DEDA` / 緑地の濃色 `#08110D`
  - ハンドル表記 `@KEEPIX.GK_OFFICIAL`
  - ロゴ: `assets/keepix-logo.png` があれば表紙/CTAに描画（なければ "KEEPIX" 文字で代替）
  - フォント: システムの Liberation Sans。日本語は fonts-noto-cjk（ランナーで `apt-get install -y fonts-noto-cjk`）を `J4KJP` として登録しフォールバック。
- プレビュー: `node scripts/preview-slides.js` → `preview-slides/`（gitignore済み）に9枚出力。※IG投稿はローカル検証不可（Secrets必要）。

### 残タスク（この順で）
1. **ロゴ配置**: `instagram-bot/assets/keepix-logo.png` を追加（ユーザーがアップロード予定）。
2. **KEEPIXアカウントのキー取得**: Graph APIエクスプローラで @KEEPIX.GK_OFFICIAL の
   - Instagram Business account id（`me/accounts?fields=name,instagram_business_account{username}` で `username == "keepix.gk_official"` の id を特定。前回一覧に「Keepix GK Training Builder」ページ有り。IG id は `17841436458021978` の可能性→username要確認）
   - 無期限ページトークン（ユーザートークンをデバッガーで延長→そのページの access_token）
   → GitHub Secrets に `KEEPIX_IG_USER_ID`, `KEEPIX_IG_ACCESS_TOKEN` を追加。
3. **記事→スライド分割 (`lib/article.js` 新規)**: Claude の structured output で、記事本文を
   `{ caption, slides:[{type:'cover'|'content'|'cta', ...}] }` の**連載パート**に分割。1パート4〜6枚。
   価格等の数字は捏造しない。caption は要約＋ハッシュタグ（2,200字以内）。
4. **カルーセル投稿 (`lib/carousel.js` 新規)**: 各スライドを item コンテナ化(`is_carousel_item=true`,`image_url`)→
   各 FINISHED 待ち→`media_type=CAROUSEL`＋`children`＋caption のコンテナ作成→ FINISHED 待ち→ publish。
   （`lib/instagram.js` の待機/リトライを流用）
5. **生成画像のホスティング**: 生成した slide PNG をリポジトリにコミット&プッシュし、
   **コミットSHA固定のraw URL**（`https://raw.githubusercontent.com/gk-analyst-site/gk-analyst-site/<SHA>/instagram-bot/content/slides/.../NN.png`）で参照。
   ブランチraw URLはCDNキャッシュ遅延があるためSHA固定necessary。ワークフローを「生成→commit&push→SHA取得→投稿」の順に。
6. **記事の入れ方**: `content/articles/*.md`（1ファイル=1記事）。ユーザーが本文を貼る→ファイル化でもOK。
   投稿済み/連載の進捗は `content/posted-articles.json` で管理。
7. **ワークフロー新規**: `.github/workflows/keepix-articles.yml`（cron `0 0 * * 1,3,5` UTC = 月水金 JST 09:00）。
   ステップで `apt-get install -y fonts-noto-cjk`（日本語）。Secrets は `KEEPIX_*` を使用。
8. 完成後 README 更新。

### 参考: カルーセル投稿の要点（Graph API）
- 各アイテム: `POST /{ig-user-id}/media` に `image_url` と `is_carousel_item=true`
- 親: `POST /{ig-user-id}/media` に `media_type=CAROUSEL`, `children=<id,id,...>`, `caption`
- 公開: `POST /{ig-user-id}/media_publish` に `creation_id=<親>`（FINISHED待ち＋9007リトライ）
- 画像は2〜10枚、公開URL必須。

---

## コミット規約
コミットメッセージ末尾に:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```
`node_modules/` と `preview-slides/` は gitignore 済み。push前に `git pull --rebase origin main`（毎日の自動コミットが入るため）。
