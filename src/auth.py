"""One-time OAuth bootstrap. Run this on a machine with a browser.

Produces api-credentials.json containing the refresh token, which is what lets
the sync run unattended on the server afterwards. Copy that file across.

    python src/auth.py

The redirect URI must be registered on the Spotify app exactly as
http://127.0.0.1:8888/callback -- Spotify rejects the hostname "localhost", it
has to be the loopback IP.
"""
import base64
import json
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from config import (
    AUTHORIZE_URL,
    REDIRECT_URI,
    SCOPES,
    TOKEN_URL,
    load_env,
    path_setting,
    require,
)

_received = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _received.update({k: v[0] for k, v in params.items()})

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if "code" in _received:
            body = "<h2>Authorised.</h2><p>You can close this tab and return to the terminal.</p>"
        else:
            body = f"<h2>Authorisation failed.</h2><pre>{_received}</pre>"
        self.write_body(body)

    def write_body(self, body: str):
        self.wfile.write(f"<html><body style='font-family:sans-serif'>{body}</body></html>".encode())

    def log_message(self, *args):
        pass  # keep the terminal clean


def main() -> None:
    load_env()
    client_id = require("SPOTIFY_CLIENT_ID")
    client_secret = require("SPOTIFY_CLIENT_SECRET")
    creds_path = path_setting("API_CREDENTIALS", "api-credentials.json")

    state = secrets.token_urlsafe(16)
    authorize = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    })

    print("Opening the Spotify consent page. If it does not open, visit:\n")
    print(authorize + "\n")
    webbrowser.open(authorize)

    server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
    server.timeout = 300
    while "code" not in _received and "error" not in _received:
        server.handle_request()

    if "error" in _received:
        raise SystemExit(f"authorisation failed: {_received['error']}")
    if _received.get("state") != state:
        raise SystemExit("state mismatch - aborting")

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": _received["code"],
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Authorization": f"Basic {basic}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise SystemExit(f"token exchange failed ({response.status_code}): {response.text[:300]}")

    payload = response.json()
    if not payload.get("refresh_token"):
        raise SystemExit("no refresh_token in the response - cannot run unattended")

    creds = {
        "client_id": client_id,
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": time.time() + payload.get("expires_in", 3600),
        "scope": payload.get("scope", ""),
    }
    creds_path.write_text(json.dumps(creds, indent=2))
    creds_path.chmod(0o600)

    print(f"\nWrote {creds_path}")
    print(f"Granted scopes: {creds['scope']}")
    print("\nCopy this file to the server, then run sync.py --dry-run there.")


if __name__ == "__main__":
    sys.exit(main())
