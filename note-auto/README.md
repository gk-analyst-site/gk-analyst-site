# note 自動投稿システム

トピック（ネタ）を登録しておくと、**Claude（AI）が記事本文を自動生成**し、
**Playwright で note のエディタを自動操作して下書き作成・公開**まで行うシステムです。
有料note（販売）の構成にも対応しています。

```
topics.yaml（ネタ） ──▶ generator.py（Claudeで本文生成） ──▶ publisher.py（noteへ投稿）
        ▲                                                              │
        └────────────── 投稿済みは status=posted に自動更新 ◀──────────┘
```

---

## ⚠️ 最初に知っておくこと

- **note には「記事を投稿する」公式APIがありません。** そのため投稿は
  ブラウザ自動操作（Playwright）で実現しています。note の画面（DOM）は
  変わることがあり、その場合は `note_auto/publisher.py` のセレクタ調整が必要です。
- **連続大量投稿はアカウント制限のリスク**があります。`config.yaml` の
  `publish.max_per_run` で1回あたりの件数を絞り、頻度も控えめにしてください。
- 既定は **下書き保存（draft）** です。まずは下書きで内容を確認し、
  問題なければ公開する運用を推奨します。

---

## セットアップ

```bash
cd note-auto
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# 設定ファイルを用意
cp .env.example .env   # ANTHROPIC_API_KEY などを記入
```

`.env` に最低限 `ANTHROPIC_API_KEY` を設定します（[Console](https://console.anthropic.com/) で取得）。

### note へのログイン（初回だけ）

Googleログインを使っている場合も含め、**手動ログイン方式**が確実です:

```bash
python -m note_auto.publisher login
```

ブラウザが開くので note にログイン → ターミナルで Enter。
ログイン状態が `state.json` に保存され、以降は自動で再利用されます。

（メール＋パスワードで自動ログインする場合は `.env` に
`NOTE_EMAIL` / `NOTE_PASSWORD` を設定すればOKです。）

---

## 使い方

```bash
# 1件だけ生成して画面に表示（投稿はしない・動作確認向け）
python -m note_auto.main preview

# 生成して out/ に Markdown 保存（投稿はしない）
python -m note_auto.main generate

# 生成 → note へ投稿（config.yaml の publish.mode に従う）
python -m note_auto.main run
```

投稿が成功すると、`topics.yaml` の該当トピックが `status: posted` になり、
次回以降スキップされます。

---

## ネタの追加

`topics.yaml` の末尾に足すだけ:

```yaml
  - title: "記事タイトルの案"
    brief: >
      書いてほしい内容のメモ。箇条書きでもOK。
    status: pending
```

---

## 設定（config.yaml）

| 項目 | 説明 |
|---|---|
| `author.persona` | AIが記事を書くときの人物像・専門性 |
| `article.min_chars` / `max_chars` | 本文の文字数目安 |
| `article.call_to_action` | 記事末尾に入れる問い合わせ導線 |
| `article.default_tags` | 付けるハッシュタグ |
| `sale.enabled` | 有料noteにするか |
| `sale.price` | 販売価格（円） |
| `sale.free_intro_chars` | 無料で読める導入パートの文字数目安 |
| `publish.mode` | `draft`（下書き）/ `publish`（公開） |
| `publish.max_per_run` | 1回で処理する記事数の上限 |

### 有料note（販売）について

`sale.enabled: true` にすると、AIが「無料導入パート」と「有料本編」を
書き分け、本文に区切りを反映します。
**価格設定と有料ラインの最終確定は現状 note 上での手動操作**が確実です
（noteの有料設定UIは変わりやすいため）。まず下書きで作られた記事を開き、
noteの「有料エリア設定」で価格と区切り位置を確定してください。

---

## モデルについて

記事生成には Claude を使用します。既定は `claude-opus-5`。
コストを抑えたい場合は `.env` の `NOTE_AUTO_MODEL=claude-sonnet-5` に変更できます。

---

## 定期実行（自動化）

`.github/workflows/note-auto.yml` にスケジュール実行のひな型があります。
ただし note のログイン状態（`state.json`）が必要なため、GitHub Actions で
完全自動化する場合は state.json を Secrets 経由で渡す等の工夫が要ります。
まずはローカルの cron で `python -m note_auto.main run` を回すのが簡単で安全です。
