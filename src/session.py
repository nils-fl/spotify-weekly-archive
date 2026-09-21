"""librespot session for reading Spotify-owned playlists.

Three workarounds carried over from ../zotify/zotify_run.py rather than
rediscovered the hard way:

1. librespot's access point is refused on :4070 and stalls on :80 on the Mac, so
   the AP pool is filtered to :443. Port 4070 is in fact open from the home
   server, but pinning costs nothing and keeps this script portable.
2. The AP handshake is intermittent on this network even on :443, so the connect
   is retried rather than failing on the first reset.
3. store_credentials is disabled so librespot never rewrites the credentials
   file. zotify reads the same file on the Mac and must not be disturbed by us.
"""
import sys
import time

from librespot.core import ApResolver, Session

from config import load_env, path_setting

_CONNECT_ATTEMPTS = 8
_RETRY_SLEEP = 3

_orig_request = ApResolver.request


def _prefer_443(service_type: str) -> str:
    urls = _orig_request(service_type).get(service_type) or []
    if not urls:
        raise RuntimeError("No ApResolve url available")
    return ([u for u in urls if u.endswith(":443")] or urls)[0]


ApResolver.get_random_of = staticmethod(_prefer_443)


def create_session() -> Session:
    load_env()
    creds = path_setting("LIBRESPOT_CREDENTIALS", "credentials.json")
    if not creds.exists():
        raise SystemExit(
            f"librespot credentials not found at {creds}\n"
            "Copy credentials.json from the zotify project (chmod 600)."
        )

    last = None
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            builder = Session.Builder()
            builder.conf.store_credentials = False
            session = builder.stored_file(str(creds)).create()
            print(f"[session] connected on attempt {attempt}", file=sys.stderr, flush=True)
            return session
        except Exception as e:
            last = e
            print(
                f"[session] attempt {attempt} failed: {type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )
            if attempt < _CONNECT_ATTEMPTS:
                time.sleep(_RETRY_SLEEP)

    raise RuntimeError(f"session could not be established after {_CONNECT_ATTEMPTS} attempts: {last}")


if __name__ == "__main__":
    s = create_session()
    print(f"ok: authenticated as {s.username()}")
