"""Playwright を使って note に記事を投稿するモジュール.

note には「記事を投稿する」ための公開APIが無いため、ブラウザ自動操作で
エディタを開いて下書き作成・公開を行う。DOM は変わりやすいので、
セレクタが効かなくなったらこのファイルを調整する。

ログインは storage_state（Cookie/セッション）方式を推奨:
  1) `python -m note_auto.publisher login` を一度だけ実行し、
     開いたブラウザで手動ログイン（Googleログインでも可）。
  2) ログイン状態が state.json に保存され、以降は自動で再利用される。
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

STATE_FILE = Path(__file__).resolve().parent.parent / "state.json"
NOTE_NEW_URL = "https://note.com/notes/new"
NOTE_LOGIN_URL = "https://note.com/login"


def _has_state() -> bool:
    return STATE_FILE.exists()


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


def _fill_editor(page: Page, title: str, body: str) -> None:
    """note のエディタにタイトルと本文を入力する.

    注意: note のエディタDOMは変更されやすい。効かない場合はセレクタを更新すること。
    """
    page.goto(NOTE_NEW_URL)
    page.wait_for_load_state("networkidle")

    # タイトル欄（placeholder「記事タイトル」）
    title_selectors = [
        'textarea[placeholder*="タイトル"]',
        'input[placeholder*="タイトル"]',
        '[contenteditable="true"][data-placeholder*="タイトル"]',
    ]
    for sel in title_selectors:
        try:
            page.wait_for_selector(sel, timeout=4000)
            page.click(sel)
            el = page.query_selector(sel)
            if el and el.evaluate("el => el.tagName") in ("TEXTAREA", "INPUT"):
                page.fill(sel, title)
            else:
                page.keyboard.type(title)
            break
        except PWTimeout:
            continue

    # 本文欄（contenteditable の本文エリア）
    body_selectors = [
        'div[contenteditable="true"][data-placeholder*="本文"]',
        'div[role="textbox"][contenteditable="true"]',
        '.note-common-styles__textnote-body [contenteditable="true"]',
    ]
    for sel in body_selectors:
        try:
            page.wait_for_selector(sel, timeout=4000)
            page.click(sel)
            page.keyboard.type(body)
            break
        except PWTimeout:
            continue

    # 入力内容が保存されるまで少し待つ（自動保存）
    page.wait_for_timeout(2000)


def publish(
    title: str,
    body: str,
    *,
    mode: str = "draft",
    headless: bool = True,
) -> None:
    """記事をエディタに入力し、下書き保存または公開する.

    mode: "draft"（下書き保存のみ・推奨） / "publish"（公開まで行う）
    """
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

        _fill_editor(page, title, body)

        if mode == "publish":
            # 「公開に進む」→「投稿する」の二段階。ボタン文言でクリックする。
            try:
                page.get_by_role("button", name="公開に進む").click(timeout=8000)
                page.wait_for_timeout(1500)
                page.get_by_role("button", name="投稿する").click(timeout=8000)
                page.wait_for_timeout(2000)
                print("記事を公開しました。")
            except PWTimeout:
                print(
                    "公開ボタンが見つかりませんでした。下書きは保存されています。"
                    "note のUI変更の可能性があるため、note上で確認してください。"
                )
        else:
            # note は入力すると自動で下書き保存されるが、明示的に保存も試みる。
            try:
                page.get_by_role("button", name="下書き保存").click(timeout=5000)
            except PWTimeout:
                pass
            print("下書きとして保存しました。note の下書き一覧で確認してください。")

        browser.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "login":
        interactive_login()
    else:
        print("使い方: python -m note_auto.publisher login")
