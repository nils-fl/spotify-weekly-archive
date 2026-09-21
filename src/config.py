"""Project paths and .env loading.

Deliberately dependency-free: a .env here is a handful of KEY=value lines, and a
12-line parser is one less thing that can break on a machine we only touch when
something has already gone wrong.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

SPCLIENT_PLAYLIST_SUFFIX = "/playlist/v2/playlist/{}"
WEB_API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"

# Must match the app's registered redirect URI byte for byte.
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-read-private playlist-modify-private playlist-modify-public"


def load_env() -> None:
    """Read .env into os.environ without clobbering real environment variables."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is not set (see .env.example)")
    return value


def path_setting(name: str, default: str) -> Path:
    """Resolve a credential path, treating relative values as project-relative."""
    raw = os.environ.get(name, "").strip() or default
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p
