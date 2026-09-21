"""Create the librespot session credentials file.

Run this once, on a machine with a browser:

    python src/login.py

It opens Spotify's consent page, and on approval writes the file that
LIBRESPOT_CREDENTIALS points at. Copy that file to wherever the sync actually
runs; the session is not tied to the machine that created it.

This is a separate login from `src/auth.py`. The two are not interchangeable:

    login.py  -> librespot session, reads the source playlist
    auth.py   -> Web API token,    writes the archive playlist

The librespot login uses Spotify's own desktop client id and a fixed callback
on 127.0.0.1:5588, so there is no app to register and nothing to configure --
but that port must be free while this runs.
"""
import sys
import webbrowser

from librespot.core import Session

from config import load_env, path_setting


def main() -> int:
    load_env()
    creds = path_setting("LIBRESPOT_CREDENTIALS", "credentials.json")

    # Builder.oauth() silently reuses an existing file instead of logging in,
    # which would look like success while changing nothing. Refuse instead.
    if creds.exists():
        print(
            f"{creds} already exists.\n"
            "Delete it first if you want to log in as a different account, or "
            "point LIBRESPOT_CREDENTIALS somewhere else.",
            file=sys.stderr,
        )
        return 1

    creds.parent.mkdir(parents=True, exist_ok=True)

    conf = (
        Session.Configuration.Builder()
        .set_store_credentials(True)
        .set_stored_credential_file(str(creds))
        .build()
    )

    def open_browser(url: str) -> str:
        print("Opening Spotify's consent page. If it does not open, visit:\n")
        print(url + "\n")
        webbrowser.open(url)
        return url

    builder = Session.Builder(conf)
    session = builder.oauth(open_browser).create()

    if not creds.exists():
        print("login completed but no credentials file was written", file=sys.stderr)
        return 1

    creds.chmod(0o600)
    print(f"\nWrote {creds} (authenticated as {session.username()})")
    print("Copy this file to the machine that runs the sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
