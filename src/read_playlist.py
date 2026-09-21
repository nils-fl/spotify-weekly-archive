"""Read a playlist's contents via librespot's spclient endpoint.

This is the piece the official Web API can no longer do. Since the Feb/Mar 2026
"Developer Mode" changes, GET /v1/playlists/{id}/items returns contents only for
playlists the user owns or collaborates on; for Spotify-owned playlists such as
Discover Weekly the `items` field is simply absent. The spclient endpoint used
here is the one the Spotify clients themselves use, authenticated by the
librespot session rather than by a Web API token, so the restriction does not
apply.

The response is protobuf (SelectedListContent from playlist4_external.proto),
which librespot ships generated bindings for -- so it is parsed properly rather
than scraped out of bytes.
"""
import sys

from librespot.core import Session
from librespot.proto import Playlist4External_pb2

from config import SPCLIENT_PLAYLIST_SUFFIX

TRACK_PREFIX = "spotify:track:"


def read_playlist_uris(session: Session, playlist_id: str) -> list[str]:
    """Return the playlist's track URIs in playlist order."""
    response = session.api().send("GET", SPCLIENT_PLAYLIST_SUFFIX.format(playlist_id), None, None)

    if response.status_code != 200:
        raise RuntimeError(
            f"spclient returned {response.status_code} for playlist {playlist_id}: "
            f"{response.text[:300]}"
        )

    content = Playlist4External_pb2.SelectedListContent()
    content.ParseFromString(response.content)

    if content.contents.truncated:
        # Not expected for a 30-track Discover Weekly, but worth knowing about
        # rather than silently archiving a partial playlist.
        print(
            "[read] WARNING: spclient reports the item list is truncated; "
            "only the first page was returned",
            file=sys.stderr,
            flush=True,
        )

    uris = []
    skipped = 0
    for item in content.contents.items:
        if item.uri.startswith(TRACK_PREFIX):
            uris.append(item.uri)
        else:
            # Local files and podcast episodes cannot be added to a playlist by URI.
            skipped += 1

    if skipped:
        print(f"[read] skipped {skipped} non-track item(s)", file=sys.stderr, flush=True)

    return uris


if __name__ == "__main__":
    from config import load_env, require
    from session import create_session

    load_env()
    playlist_id = sys.argv[1] if len(sys.argv) > 1 else require("SOURCE_PLAYLIST_ID")
    s = create_session()
    found = read_playlist_uris(s, playlist_id)
    print(f"{len(found)} tracks in {playlist_id}")
    for i, uri in enumerate(found, 1):
        print(f"{i:3d}. {uri}")
