# -*- coding: utf-8 -*-
"""
「鍵2」（YouTubeアナリティクス用のリフレッシュトークン）を手に入れるための道具。
自分のパソコンで1回だけ動かします。

使い方:
  python3 get_refresh_token.py あなたのCLIENT_ID あなたのCLIENT_SECRET

  → ブラウザが開くので、チャンネルのGoogleアカウントでログインして「許可」
  → 画面に YT_REFRESH_TOKEN=... が出るので、それを GitHub の Secrets に登録
"""

import sys
import json
import webbrowser
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765
REDIRECT = f"http://localhost:{PORT}"
SCOPES = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/yt-analytics.readonly"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    client_id, client_secret = sys.argv[1], sys.argv[2]
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent",
    })
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got["code"] = q.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("OK！この画面は閉じてターミナルに戻ってください。".encode("utf-8"))

        def log_message(self, *a):
            pass

    print("ブラウザでログインして「許可」を押してください。開かない場合はこのURLを開いてください:\n" + url)
    webbrowser.open(url)
    HTTPServer(("localhost", PORT), Handler).handle_request()
    if not got.get("code"):
        sys.exit("許可コードが受け取れませんでした。もう一度やり直してください。")

    data = urllib.parse.urlencode({
        "code": got["code"], "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=data)) as res:
        tok = json.loads(res.read().decode())
    if "refresh_token" not in tok:
        sys.exit(f"リフレッシュトークンが入っていませんでした: {tok}")
    print("\n✅ これを GitHub の Secrets に登録してください:\n")
    print(f"YT_REFRESH_TOKEN={tok['refresh_token']}")


if __name__ == "__main__":
    main()
