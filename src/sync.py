"""Weekly job: copy the source playlist's tracks into the archive playlist.

Reads Discover Weekly through librespot (the Web API cannot), writes to the
archive through the official Web API (which it can, because that playlist is
owned by the user). Deduplicates on track URI, so running it twice in a week
adds nothing the second time.

    python src/sync.py [--dry-run]
"""
import json
import sys
import time
from datetime import datetime, timezone

from config import ROOT, load_env, path_setting, require
from read_playlist import read_playlist_uris
from session import create_session
from webapi import WebAPI

LOG_FILE = ROOT / "logs" / "runs.jsonl"


def log_run(entry: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    load_env()

    source_id = require("SOURCE_PLAYLIST_ID")
    archive_id = require("ARCHIVE_PLAYLIST_ID")
    started = time.time()

    # ---- read the source via librespot ------------------------------------
    session = create_session()
    source_uris = read_playlist_uris(session, source_id)

    # An empty source is never treated as "nothing new this week". A revoked
    # session or a changed spclient endpoint would look exactly like a quiet
    # week, and this job would then fail silently for months.
    if not source_uris:
        print(
            f"ERROR: source playlist {source_id} returned no tracks.\n"
            "This is an error, not an empty week -- the librespot session or the\n"
            "spclient endpoint has most likely stopped working.",
            file=sys.stderr,
        )
        log_run({
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "reason": "empty_source",
            "source_playlist": source_id,
        })
        return 1

    # ---- read the archive via the official Web API -------------------------
    api = WebAPI(
        client_id=require("SPOTIFY_CLIENT_ID"),
        client_secret=require("SPOTIFY_CLIENT_SECRET"),
        creds_path=path_setting("API_CREDENTIALS", "api-credentials.json"),
    )
    archive_uris = api.get_playlist_uris(archive_id)
    known = set(archive_uris)

    # ---- diff, preserving source order -------------------------------------
    new_uris = []
    for uri in source_uris:
        if uri not in known:
            new_uris.append(uri)
            known.add(uri)

    print(f"source  : {len(source_uris)} tracks ({source_id})")
    print(f"archive : {len(archive_uris)} tracks ({archive_id})")
    print(f"new     : {len(new_uris)}")

    if not new_uris:
        print("nothing to add")
        log_run({
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "source_count": len(source_uris),
            "archive_before": len(archive_uris),
            "added_count": 0,
            "added": [],
            "dry_run": dry_run,
            "seconds": round(time.time() - started, 1),
        })
        return 0

    labels = [api.track_label(uri) for uri in new_uris]
    for label in labels:
        print(f"  + {label}")

    if dry_run:
        print("\n--dry-run: nothing was written")
        return 0

    added = api.add_uris(archive_id, new_uris)
    print(f"added {added} track(s) to the archive")

    log_run({
        "ts": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "source_playlist": source_id,
        "archive_playlist": archive_id,
        "source_count": len(source_uris),
        "archive_before": len(archive_uris),
        "added_count": added,
        "added": [{"uri": u, "label": l} for u, l in zip(new_uris, labels)],
        "dry_run": False,
        "seconds": round(time.time() - started, 1),
    })
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Non-zero exit so pm2 marks the run as errored rather than succeeded.
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        log_run({
            "ts": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "reason": f"{type(exc).__name__}: {exc}",
        })
        sys.exit(1)
