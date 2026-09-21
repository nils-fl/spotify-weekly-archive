"""Official Spotify Web API client for the write side.

Only the archive playlist is touched here, and Nils owns it, so none of the
Developer Mode playlist restrictions apply. Reading Discover Weekly is handled
by read_playlist.py instead.

Two things this deliberately guards against:

* Spotify's token refresh answers 200 with a fresh access_token but sometimes
  omits refresh_token entirely. Reading it unconditionally raises KeyError and
  kills the job weeks after it was set up. Per OAuth2 the stored refresh token
  stays valid when none is reissued, so it is carried over. (Same bug worked
  around in ../zotify/zotify_run.py:69-87.)
* The Feb 2026 API changes renamed /playlists/{id}/tracks to
  /playlists/{id}/items. The old path still answers for some apps, so both are
  tried rather than guessing which migration state this app is in.
"""
import base64
import json
import time
from pathlib import Path

import requests

from config import TOKEN_URL, WEB_API

_TIMEOUT = 30
_ADD_CHUNK = 100  # Spotify's hard cap per add request
_PAGE = 50


class WebAPI:
    def __init__(self, client_id: str, client_secret: str, creds_path: Path):
        self.client_id = client_id
        self.client_secret = client_secret
        self.creds_path = creds_path
        self._creds = self._load()
        self._token = None

    # ---- credentials -------------------------------------------------------
    def _load(self) -> dict:
        if not self.creds_path.exists():
            raise SystemExit(
                f"Web API credentials not found at {self.creds_path}\n"
                "Run: python src/auth.py   (on a machine with a browser)"
            )
        return json.loads(self.creds_path.read_text())

    def _save(self) -> None:
        self.creds_path.write_text(json.dumps(self._creds, indent=2))
        self.creds_path.chmod(0o600)

    def _basic_auth(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def token(self) -> str:
        """Return a valid access token, refreshing it when it is close to expiry."""
        if self._token and self._creds.get("expires_at", 0) > time.time() + 60:
            return self._token

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._creds["refresh_token"],
            },
            headers={"Authorization": self._basic_auth()},
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"token refresh failed ({response.status_code}): {response.text[:300]}")

        payload = response.json()
        self._creds["access_token"] = payload["access_token"]
        self._creds["expires_at"] = time.time() + payload.get("expires_in", 3600)
        # Carry the old refresh token over when Spotify does not reissue one.
        if payload.get("refresh_token"):
            self._creds["refresh_token"] = payload["refresh_token"]
        self._save()

        self._token = self._creds["access_token"]
        return self._token

    # ---- requests ----------------------------------------------------------
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(3):
            response = requests.request(
                method,
                url,
                headers={"Authorization": f"Bearer {self.token()}"},
                timeout=_TIMEOUT,
                **kwargs,
            )
            if response.status_code == 429:
                wait = int(response.headers.get("Retry-After", "2")) + 1
                time.sleep(wait)
                continue
            return response
        return response

    def _playlist_paths(self, playlist_id: str) -> list[str]:
        """The post-Feb-2026 path first, then the legacy one."""
        return [
            f"{WEB_API}/playlists/{playlist_id}/items",
            f"{WEB_API}/playlists/{playlist_id}/tracks",
        ]

    # ---- playlist ----------------------------------------------------------
    def get_playlist_uris(self, playlist_id: str) -> list[str]:
        """Every track URI currently in the playlist. Requires ownership."""
        last_error = None
        for base in self._playlist_paths(playlist_id):
            url = f"{base}?limit={_PAGE}"
            uris: list[str] = []
            ok = True
            while url:
                response = self._request("GET", url)
                if response.status_code == 404:
                    last_error = f"404 at {base}"
                    ok = False
                    break
                if response.status_code != 200:
                    raise RuntimeError(
                        f"reading playlist {playlist_id} failed "
                        f"({response.status_code}): {response.text[:300]}"
                    )
                payload = response.json()
                for entry in payload.get("items") or []:
                    # The /items endpoint and the legacy /tracks endpoint differ
                    # in how the object is nested.
                    track = entry.get("track") or entry.get("item") or {}
                    uri = track.get("uri")
                    if uri:
                        uris.append(uri)
                url = payload.get("next")
            if ok:
                return uris
        raise RuntimeError(f"could not read playlist {playlist_id} ({last_error})")

    def add_uris(self, playlist_id: str, uris: list[str]) -> int:
        """Append URIs to the playlist. Returns how many were sent."""
        if not uris:
            return 0
        for base in self._playlist_paths(playlist_id):
            sent = 0
            ok = True
            for start in range(0, len(uris), _ADD_CHUNK):
                chunk = uris[start:start + _ADD_CHUNK]
                response = self._request("POST", base, json={"uris": chunk})
                if response.status_code == 404 and sent == 0:
                    ok = False
                    break
                if response.status_code not in (200, 201):
                    raise RuntimeError(
                        f"adding to playlist {playlist_id} failed "
                        f"({response.status_code}): {response.text[:300]}"
                    )
                sent += len(chunk)
            if ok:
                return sent
        raise RuntimeError(f"could not add items to playlist {playlist_id}")

    def track_label(self, uri: str) -> str:
        """'Artist - Title' for the run log. Best-effort: never fails the run.

        The batch form GET /v1/tracks?ids= was removed for Development Mode apps
        (it answers 403), so this is one request per track. At ~30 tracks a week
        that is not worth optimising.
        """
        track_id = uri.rsplit(":", 1)[-1]
        try:
            response = self._request("GET", f"{WEB_API}/tracks/{track_id}")
            if response.status_code != 200:
                return uri
            payload = response.json()
            artists = ", ".join(a["name"] for a in payload.get("artists", []))
            return f"{artists} - {payload.get('name', '?')}".strip(" -")
        except Exception:
            return uri
