<p align="center">
  <img src="assets/logo.svg" width="80" height="80" alt="">
</p>

<h1 align="center">spotify-weekly-archive</h1>

<p align="center">
  Keep every Discover Weekly.
</p>

---

Copies tracks from one Spotify playlist into another on a schedule. Built for
Discover Weekly, which Spotify replaces every Monday.

Deduplicates on track URI, so it is safe to run repeatedly.

## Why librespot

The Web API can no longer read Spotify-owned playlists:

- Nov 2024: apps without existing extended quota lost access to algorithmic and
  editorial playlists.
- Feb/Mar 2026 (Developer Mode): playlist contents are only returned for
  playlists you own or collaborate on. For anything else the `items` field is
  absent. See the [migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide).
- Extended Quota Mode is exempt, but has been organizations-only since May 2025
  (registered business, 250k MAU).

No app configuration gets around this. So the source playlist is read through a
librespot session, using the same spclient endpoint the official clients use,
and the archive is read and written through the Web API, since you own it.

This reads playlist metadata only. It never calls librespot's `content_feeder`,
`audio_key` or `cdn`, and contacts no CDN. The only hosts it talks to are
`api.spotify.com`, `accounts.spotify.com` and spclient.

The spclient endpoint is undocumented and can change. When it does, the job
exits non-zero rather than reporting an empty week, so you find out.

## Setup

Needs Python 3.10, since librespot pins `>=3.10,<3.11`.
[uv](https://docs.astral.sh/uv/) handles that on hosts with a newer Python.

```bash
git clone https://github.com/nils-fl/spotify-weekly-archive
cd spotify-weekly-archive
uv sync
cp .env.example .env
```

Fill in `.env`, then run the two logins. Both need a browser, so do them on a
desktop machine and copy the credential files to wherever the job runs.

```bash
PYTHONPATH=src .venv/bin/python src/login.py   # librespot session, reads
PYTHONPATH=src .venv/bin/python src/auth.py    # Web API token, writes
```

`login.py` needs no app registration: librespot uses Spotify's own desktop
client id and a callback on `127.0.0.1:5588`. If you already have a credentials
file from another librespot tool, point `LIBRESPOT_CREDENTIALS` at it and skip
this step. The file is only ever read.

`auth.py` needs a [dashboard app](https://developer.spotify.com/dashboard)
with:

- redirect URI registered as exactly `http://127.0.0.1:8888/callback`, not
  `localhost`
- your account under User Management, since Development Mode allows five
- active Premium on the app owner's account, or Development Mode apps stop
  working

Then check it and run it:

```bash
PYTHONPATH=src .venv/bin/python src/sync.py --dry-run
PYTHONPATH=src .venv/bin/python src/sync.py
```

## Scheduling

A one-shot job, so schedule it however you like.

```bash
pm2 start ecosystem.config.cjs
pm2 save
```

Mondays 09:00 local time. `ecosystem.config.cjs` derives its paths from its own
location and needs no editing. If pm2 came from nvm it will not be on the
non-interactive SSH PATH, so use absolute paths in scripts.

With cron instead:

```cron
0 9 * * 1 cd /path/to/repo && PYTHONPATH=src .venv/bin/python src/sync.py
```

## Docker

```bash
docker build -t spotify-weekly-archive .

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/.env:/app/.env:ro" \
  -v "$PWD/credentials.json:/app/credentials.json:ro" \
  -v "$PWD/api-credentials.json:/app/api-credentials.json" \
  -v "$PWD/logs:/app/logs" \
  spotify-weekly-archive
```

Alpine, 72MB, runs as `nobody`. Do the logins on the host first.

`api-credentials.json` has to be writable, because tokens expire hourly and the
refreshed one is written back. `credentials.json` can stay read-only.

Environment variables override `.env`, which is how you point at container
paths: `-e LIBRESPOT_CREDENTIALS=/app/credentials.json`.

Building on Apple Silicon for an x86 host needs `--platform linux/amd64`.

## Logs

`logs/runs.jsonl`, one object per run: timestamp, counts, and each track added.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `source playlist returned no tracks` | Session revoked, or the spclient endpoint changed. Delete the credentials file and re-run `login.py`. |
| `already exists` from `login.py` | It will not overwrite a session file. Delete it first. |
| `session could not be established` | AP handshake failing. Check outbound access to `ap-gew4.spotify.com`. |
| `token refresh failed (400)` | Refresh token revoked. Re-run `auth.py`. |
| 403 on everything | Premium lapsed, or your account fell off the app's allowlist. |
| 403 on track lookups only | Expected. Batch track lookup is gone in Developer Mode, so it falls back to the bare URI. |
| `Permission denied` under Docker | Pass `--user "$(id -u):$(id -g)"`. |
| `exec format error` | Wrong architecture. Rebuild with `--platform linux/amd64`. |

## Caveats

Run it from one machine only. A token refresh can rotate the refresh token, and
whichever machine refreshed last holds the valid one.

Deduplication is by track URI, so a re-release carrying a different URI can slip
through as a near-duplicate.

## License

MIT
