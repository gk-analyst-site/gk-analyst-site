"""Playwright を使って note に記事を投稿するモジュール.

note には「記事を投稿する」ための公開APIが無いため、ブラウザ自動操作で
エディタを開いて下書き作成・公開を行う。有料note（価格・有料ライン）も
自動設定する。DOM は変わりやすいので、セレクタが効かなくなったら
このファイルを調整する（失敗時は shots/ にスクショを保存する）。

ログインは storage_state（Cookie/セッション）方式を推奨:
  1) `python -m note_auto.publisher login` を一度だけ実行し、
     開いたブラウザで手動ログイン（Googleログインでも可）。
  2) ログイン状態が state.json に保存され、以降は自動で再利用される。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state.json"
SHOTS_DIR = ROOT / "shots"
NOTE_NEW_URL = "https://note.com/notes/new"
NOTE_LOGIN_URL = "https://note.com/login"


def _has_state() -> bool:
    return STATE_FILE.exists()


def _shot(page: Page, name: str) -> None:
    """デバッグ用スクリーンショットを保存する."""
    SHOTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = SHOTS_DIR / f"{stamp}_{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"  [スクショ保存] {path}")
    except Exception:  # noqa: BLE001 - スクショ失敗は本処理を止めない
        pass


def _try_click(page: Page, selectors: list[str], *, timeout: int = 4000) -> bool:
    """候補セレクタを順に試し、最初にクリックできたら True."""
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=timeout, state="visible")
            page.click(sel)
            return True
        except PWTimeout:
            continue
    return False


def _try_click_by_text(page: Page, names: list[str], *, timeout: int = 4000) -> bool:
    """ボタン等をラベル文言で順に試してクリックする."""
    for name in names:
        try:
            page.get_by_role("button", name=name).first.click(timeout=timeout)
            return True
        except PWTimeout:
            continue
        except Exception:  # noqa: BLE001
            continue
    return False


def interactive_login() -> None:
    """ブラウザを開いて手動ログインし、セッションを保存する（初回セットアップ用）."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(NOTE_LOGIN_URL)
        print(
            "ブラウザで note にログインしてください。\n"
            "ログインが完了して自分のトップ画面が表示されたら、この画面で Enter を押します。"
        )
        input("ログイン完了後に Enter> ")
        context.storage_state(path=str(STATE_FILE))
        browser.close()
        print(f"ログイン状態を保存しました: {STATE_FILE}")


def _login_with_password(page: Page) -> None:
    """メール＋パスワードで自動ログイン（.env の NOTE_EMAIL / NOTE_PASSWORD）."""
    email = os.environ.get("NOTE_EMAIL")
    password = os.environ.get("NOTE_PASSWORD")
    if not (email and password):
        raise RuntimeError(
            "ログイン状態がありません。先に `python -m note_auto.publisher login` を実行するか、"
            ".env に NOTE_EMAIL / NOTE_PASSWORD を設定してください。"
        )
    page.goto(NOTE_LOGIN_URL)
    page.fill('input[type="email"], input[name="email"]', email)
    page.fill('input[type="password"], input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")


# --- エディタ操作 -------------------------------------------------------------

TITLE_SELECTORS = [
    'textarea[placeholder*="タイトル"]',
    'input[placeholder*="タイトル"]',
    '[contenteditable="true"][data-placeholder*="タイトル"]',
]
BODY_SELECTORS = [
    'div[contenteditable="true"][data-placeholder*="本文"]',
    'div[role="textbox"][contenteditable="true"]',
    '.note-common-styles__textnote-body [contenteditable="true"]',
]


def _fill_title(page: Page, title: str) -> None:
    for sel in TITLE_SELECTORS:
        try:
            page.wait_for_selector(sel, timeout=4000)
            page.click(sel)
            el = page.query_selector(sel)
            if el and el.evaluate("el => el.tagName") in ("TEXTAREA", "INPUT"):
                page.fill(sel, title)
            else:
                page.keyboard.type(title)
            return
        except PWTimeout:
            continue
    _shot(page, "title_not_found")
    raise RuntimeError("タイトル入力欄が見つかりませんでした（note のUI変更の可能性）。")


def _focus_body(page: Page) -> str:
    for sel in BODY_SELECTORS:
        try:
            page.wait_for_selector(sel, timeout=4000)
            page.click(sel)
            return sel
        except PWTimeout:
            continue
    _shot(page, "body_not_found")
    raise RuntimeError("本文入力欄が見つかりませんでした（note のUI変更の可能性）。")


def _type_paragraphs(page: Page, text: str) -> None:
    """段落ごとに入力する（Enter で段落を分ける）."""
    paragraphs = [p for p in text.split("\n") if True]
    for i, para in enumerate(paragraphs):
        if para.strip():
            page.keyboard.type(para)
        if i < len(paragraphs) - 1:
            page.keyboard.press("Enter")


def _insert_paywall_line(page: Page) -> bool:
    """本文カーソル位置に『ここから先は有料』の境界線を挿入する.

    note のエディタでは、空行に出る『＋』メニューから有料ラインを追加する。
    UI差異に備えて複数の方法を試す。
    """
    # 有料ラインの前後は空行にしておく
    page.keyboard.press("Enter")

    # 方法1: 行頭に出る「＋」ボタン → メニューの「有料エリア設定 / 有料ライン」
    plus_selectors = [
        'button[aria-label*="追加"]',
        'button[aria-label*="メニュー"]',
        '[data-testid="add-block-button"]',
        'button:has-text("＋")',
    ]
    if _try_click(page, plus_selectors, timeout=3000):
        page.wait_for_timeout(500)
        if _try_click_by_text(
            page, ["有料エリア設定", "有料ライン", "ここから先を有料にする", "有料"], timeout=3000
        ):
            page.wait_for_timeout(500)
            return True

    # 方法2: ツールバー等に有料ライン挿入ボタンがある場合
    line_selectors = [
        'button[aria-label*="有料"]',
        '[data-testid*="paid"]',
    ]
    if _try_click(page, line_selectors, timeout=3000):
        page.wait_for_timeout(500)
        return True

    _shot(page, "paywall_line_not_found")
    print(
        "  [警告] 本文中への有料ライン挿入UIが見つかりませんでした。"
        "公開設定側での有料範囲指定にフォールバックします。"
    )
    return False


def _fill_editor(
    page: Page,
    title: str,
    free_body: str,
    paid_body: str | None,
) -> bool:
    """エディタにタイトル・本文を入力。有料の場合は境界線も挿入する.

    戻り値: 本文中に有料ラインを挿入できたか（公開設定での価格入力は別途行う）。
    """
    page.goto(NOTE_NEW_URL)
    page.wait_for_load_state("networkidle")

    _fill_title(page, title)
    _focus_body(page)

    paywall_inserted = False
    if paid_body is not None:
        _type_paragraphs(page, free_body)
        paywall_inserted = _insert_paywall_line(page)
        page.keyboard.press("Enter")
        _type_paragraphs(page, paid_body)
    else:
        _type_paragraphs(page, free_body)

    page.wait_for_timeout(2000)  # 自動保存を待つ
    return paywall_inserted


# --- 公開設定（価格） ---------------------------------------------------------

def _configure_paid_and_publish(
    page: Page,
    price: int,
    mode: str,
    paywall_inserted: bool,
) -> None:
    """公開設定画面で有料・価格を設定し、mode に応じて公開する."""
    # 公開設定画面へ進む
    if not _try_click_by_text(page, ["公開に進む", "公開設定", "投稿する"], timeout=8000):
        _shot(page, "proceed_button_not_found")
        print("  [警告] 『公開に進む』ボタンが見つかりませんでした。下書きは保存されています。")
        return

    page.wait_for_timeout(1500)

    # 有料を選択（ラジオ/トグル/タブのいずれか）
    _try_click_by_text(page, ["有料", "有料で販売", "有料note"], timeout=4000)
    page.wait_for_timeout(500)

    # 価格入力欄に価格を入れる
    price_selectors = [
        'input[name*="price"]',
        'input[placeholder*="価格"]',
        'input[type="number"]',
        'input[inputmode="numeric"]',
    ]
    filled = False
    for sel in price_selectors:
        try:
            page.wait_for_selector(sel, timeout=3000, state="visible")
            page.fill(sel, str(price))
            filled = True
            break
        except PWTimeout:
            continue
    if not filled:
        _shot(page, "price_field_not_found")
        print("  [警告] 価格入力欄が見つかりませんでした。公開設定を手動で確認してください。")

    if not paywall_inserted:
        # 本文に有料ラインを挿入できなかった場合、公開設定側の
        # 有料範囲指定UIがあれば試す（無ければ note 上で手動指定が必要）。
        print(
            "  [注意] 有料ラインが本文に無いため、公開設定側で範囲指定が必要な場合があります。"
        )

    page.wait_for_timeout(500)

    if mode == "publish":
        if _try_click_by_text(page, ["投稿する", "公開する", "有料で公開する"], timeout=8000):
            page.wait_for_timeout(2500)
            print("  有料記事を公開しました。")
        else:
            _shot(page, "publish_button_not_found")
            print("  [警告] 公開ボタンが見つかりませんでした。設定は入力済みです。note上で確認してください。")
    else:
        print("  有料設定を入力し、下書き段階で停止しました。note上で内容を確認してください。")


def publish(
    title: str,
    free_body: str,
    *,
    paid_body: str | None = None,
    price: int | None = None,
    mode: str = "draft",
    headless: bool = True,
) -> None:
    """記事をエディタに入力し、下書き保存または公開する.

    - paid_body / price を指定すると有料note（価格・有料ライン）を自動設定する。
    - mode: "draft"（下書き・推奨） / "publish"（公開まで行う）
    """
    is_paid = paid_body is not None and price is not None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        if _has_state():
            context = browser.new_context(storage_state=str(STATE_FILE))
        else:
            context = browser.new_context()
        page = context.new_page()

        if not _has_state():
            _login_with_password(page)
            context.storage_state(path=str(STATE_FILE))

        paywall_inserted = _fill_editor(page, title, free_body, paid_body if is_paid else None)

        if is_paid:
            _configure_paid_and_publish(page, price, mode, paywall_inserted)
        else:
            # 無料記事
            if mode == "publish":
                if _try_click_by_text(page, ["公開に進む"], timeout=8000):
                    page.wait_for_timeout(1500)
                    if _try_click_by_text(page, ["投稿する", "公開する"], timeout=8000):
                        page.wait_for_timeout(2000)
                        print("  記事を公開しました。")
                    else:
                        _shot(page, "publish_button_not_found")
                        print("  [警告] 公開ボタンが見つかりませんでした。下書きは保存されています。")
                else:
                    _shot(page, "proceed_button_not_found")
                    print("  [警告] 『公開に進む』が見つかりませんでした。下書きは保存されています。")
            else:
                _try_click_by_text(page, ["下書き保存"], timeout=5000)
                print("  下書きとして保存しました。")

        browser.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "login":
        interactive_login()
    else:
        print("使い方: python -m note_auto.publisher login")
