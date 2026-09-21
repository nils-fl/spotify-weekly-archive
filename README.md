<p align="center">
  <img src="assets/logo.svg" width="80" height="80" alt="">
</p>

<h1 align="center">spotify-weekly-archive</h1>

<p align="center">
  Keep every Discover Weekly, forever.
</p>

---

Copies the tracks from a Spotify playlist into a permanent archive playlist on a
schedule. Built for Discover Weekly, which is replaced every Monday — this keeps
a running archive of everything it ever recommended.

Runs unattended under pm2 (or any scheduler), deduplicates on track URI, and is
safe to run repeatedly.

## Why it needs librespot

The Spotify Web API cannot return the contents of Spotify-owned playlists such
as Discover Weekly:

- **Nov 27, 2024** — apps without pre-existing extended quota lost access to
  algorithmic and Spotify-owned editorial playlists.
- **Feb 11 / Mar 9, 2026 ("Developer Mode")** — per the
  [migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide):
  *"Playlist contents (`items`) are only returned for playlists the user owns or
  collaborates on. For other playlists, only metadata is returned and the
  `items` field will be absent from the response."*
- **Extended Quota Mode**, which is exempt, has been restricted to organizations
  since May 2025 (registered business, live product, 250k MAU).

There is therefore no Web API configuration that can read Discover Weekly. The
work is split across two mechanisms:

| Side | Mechanism |
|---|---|
| Read the source playlist | librespot session → spclient `/playlist/v2/playlist/{id}`, the same endpoint the official Spotify clients use |
| Read and write the archive | Official Web API `/v1/playlists/{id}/items` |

The spclient response is protobuf (`SelectedListContent`), parsed with the
bindings librespot ships. No audio is fetched or downloaded — this reads
playlist contents only.

Because the read side depends on an endpoint Spotify does not document, it can
change without notice. The job therefore **fails loudly on an empty source**
rather than reporting "nothing new this week", so a breakage can't quietly cost
you months of recommendations.

## Scope

This tool moves track identifiers between playlists. It does not touch audio.

**What it does**

- Reads the track URIs of a source playlist
- Reads the archive playlist, and appends the URIs that aren't already in it
- Resolves track titles for the run log
- Writes `logs/runs.jsonl`

**What it does not do**

- Fetch, decrypt, store or convert audio in any form
- Call librespot's `content_feeder()`, `audio_key()` or `cdn()` — the APIs
  through which audio would be obtained
- Contact any Spotify CDN or audio endpoint. The only hosts used are
  `api.spotify.com`, `accounts.spotify.com`, and the spclient host that serves
  the playlist metadata
- Read, modify or delete anything outside the two configured playlists
- Bundle, transmit or phone home with credentials of any kind

The entire librespot surface in use is three imports — `ApResolver`, `Session`
and the `Playlist4External` protobuf. `librespot` is a full Spotify client
library and can do considerably more than this project asks of it; that
capability belongs to the library, and nothing here exposes or wraps it.

## Requirements

- Python 3.10 (librespot pins `>=3.10,<3.11`); [uv](https://docs.astral.sh/uv/)
  makes this painless on hosts with a newer system Python
- A librespot session credentials file
- A Spotify Developer app for the write side

## Credentials

Two separate logins, for the two halves of the job. They are not
interchangeable, and you need both.

**1. librespot session** — reads the source playlist. Created by:

```bash
PYTHONPATH=src .venv/bin/python src/login.py
```

This opens Spotify's consent page and writes the file `LIBRESPOT_CREDENTIALS`
points at. There is **no app to register** — it uses Spotify's own desktop
client id and a fixed callback on `127.0.0.1:5588`, so the only requirements are
a browser and that port being free while it runs.

The session is not tied to the machine that created it, so log in on your
desktop and copy the file to wherever the sync actually runs. The resulting
file looks like:

```json
{ "username": "...", "credentials": "...", "type": "..." }
```

If you already have one from another librespot-based tool, point
`LIBRESPOT_CREDENTIALS` at it instead and skip `login.py`. This project never
writes to that file (`store_credentials` is disabled), so sharing it is safe.

**2. Web API OAuth** — writes to the archive playlist. Created once by
`src/auth.py`. Unlike the above, this one *does* need a
[dashboard app](https://developer.spotify.com/dashboard) with:

- Redirect URI registered as exactly `http://127.0.0.1:8888/callback`
  (Spotify rejects the hostname `localhost`; it must be the loopback IP)
- Your account added under **User Management** (Development Mode caps at 5 users)
- **Active Spotify Premium on the app owner's account** — Development Mode apps
  stop working without it, which is an easy failure to misdiagnose

Scopes requested: `playlist-read-private playlist-modify-private playlist-modify-public`

## Setup

```bash
git clone <this-repo> spotify-helpers && cd spotify-helpers
uv sync

cp .env.example .env
# fill in SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
# SOURCE_PLAYLIST_ID, ARCHIVE_PLAYLIST_ID

# two one-time logins; both need a browser, so run these on a desktop machine
PYTHONPATH=src .venv/bin/python src/login.py   # librespot session -> reads
PYTHONPATH=src .venv/bin/python src/auth.py    # Web API token     -> writes

# sanity checks
PYTHONPATH=src .venv/bin/python src/read_playlist.py   # lists source track URIs
PYTHONPATH=src .venv/bin/python src/sync.py --dry-run  # reads everything, writes nothing
```

Then run it for real:

```bash
PYTHONPATH=src .venv/bin/python src/sync.py
```

## Deploying to a server

`auth.py` needs a browser, so authorise on a desktop machine and copy the
resulting `api-credentials.json` to the server along with your librespot
credentials file. Both should be `chmod 600`.

```bash
uv python install 3.10
uv sync
PYTHONPATH=src .venv/bin/python src/sync.py --dry-run
```

Schedule it with pm2 — `ecosystem.config.cjs` derives every path from its own
location, so it needs no editing:

```bash
pm2 start ecosystem.config.cjs
pm2 save     # without this the job is lost on reboot
```

Default schedule is Mondays 09:00 in the server's local timezone, after
Discover Weekly refreshes. Change `cron_restart` to taste.

If node/pm2 were installed via nvm, they are typically **not** on the
non-interactive SSH PATH — use absolute paths in any remote or scripted
invocation.

Force a run and inspect it:

```bash
pm2 restart spotify-weekly-archive
pm2 logs spotify-weekly-archive --lines 50
```

## Running with Docker

```bash
docker build -t spotify-weekly-archive .
```

Alpine-based, ~72MB, runs as `nobody`. Dependencies are a separate layer from
the source, so editing `src/` rebuilds in about a second.

If you are building on Apple Silicon for an x86 server, cross-build explicitly —
otherwise you get an arm64 image that will not start there:

```bash
docker build --platform linux/amd64 -t spotify-weekly-archive .
```

Do the two logins on a desktop machine first (see **Credentials**) — both need a
browser, so neither runs usefully inside the container. Then mount the results:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/.env:/app/.env:ro" \
  -v "$PWD/credentials.json:/app/credentials.json:ro" \
  -v "$PWD/api-credentials.json:/app/api-credentials.json" \
  -v "$PWD/logs:/app/logs" \
  spotify-weekly-archive
```

Three details that matter:

- `api-credentials.json` is mounted **writable**, not `:ro`. Access tokens
  expire hourly and the refreshed token is written back; mounting it read-only
  makes the job fail as soon as the first token expires.
- `credentials.json` is safe read-only — the librespot session file is never
  written to.
- `--user` matches the container's uid to yours. The image defaults to `nobody`,
  which cannot write to files your host user owns, so omitting this gives
  `Permission denied` on `logs/` or the token file.

Environment variables take precedence over `.env`, which is how you point at
container paths without editing the file:

```bash
-e LIBRESPOT_CREDENTIALS=/app/credentials.json
```

Add `--dry-run` at the end of the command to read everything and write nothing.
To run one of the other entry points:

```bash
docker run ... --entrypoint python spotify-weekly-archive /app/src/read_playlist.py
```

The container is a **one-shot job**: it runs, reports, and exits. Schedule it
from the host rather than looping inside the container — a crontab line, a
systemd timer, or a container scheduler such as Ofelia:

```cron
0 9 * * 1  cd /path/to/spotify-weekly-archive && docker run --rm ... spotify-weekly-archive
```

## Logs

`logs/runs.jsonl` — one JSON object per run: timestamp, counts, and each added
track with an `Artist - Title` label. pm2's own output goes to
`logs/pm2-out.log` and `logs/pm2-err.log`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `source playlist returned no tracks` | The librespot session was revoked, or the spclient endpoint changed. Delete the credentials file and re-run `src/login.py`. |
| `... already exists` from `login.py` | Intentional. It refuses to overwrite a session file, because librespot would otherwise silently reuse the old one and report success. Delete it first. |
| `session could not be established after 8 attempts` | AP handshake failing. The client already pins `:443` and retries; check outbound access to `ap-gew4.spotify.com`. |
| `token refresh failed (400)` | Refresh token revoked. Re-run `src/auth.py` and copy `api-credentials.json` across. |
| Web API returns 403 everywhere | Premium lapsed on the app owner's account, or your account fell off the app's 5-user allowlist. |
| `403` on track lookups only | Expected. The batch form `GET /v1/tracks?ids=` was removed for Development Mode apps; `track_label()` falls back to the bare URI. |
| Job never runs after a reboot | `pm2 save` was not run, or pm2's startup service is not enabled. |
| `Permission denied` writing logs or the token, in Docker | The image runs as `nobody`. Pass `--user "$(id -u):$(id -g)"`. |
| `exec format error` in Docker | arm64 image on an x86 host. Rebuild with `--platform linux/amd64`. |

## Notes

- **Run the sync from one machine only.** A token refresh can rotate the refresh
  token, and whichever machine refreshes last holds the valid one. Let the
  scheduled host own `api-credentials.json`.
- Deduplication is on track URI. Spotify re-releases can carry a different URI
  for the same recording, so an occasional near-duplicate is possible.
- Playlists cap at 10,000 tracks; at ~30/week that is years of headroom.

## License

MIT — see [LICENSE](LICENSE).
