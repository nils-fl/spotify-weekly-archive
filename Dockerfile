# syntax=docker/dockerfile:1

# librespot pins Python >=3.10,<3.11, so the base image is not a free choice.
#
# Alpine rather than slim: musl wheels exist for every C extension in the tree
# (Cryptodome, protobuf, zeroconf), so nothing is compiled from source and the
# runtime image is less than half the size. Only pure-Python sdists are built.
FROM python:3.10-alpine AS builder

# git is needed because librespot is installed from a git ref. No compilers:
# everything else resolves to a prebuilt musl wheel.
RUN apk add --no-cache git

# Pin uv so builds are reproducible; bump deliberately rather than drifting.
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

# copy: the cache mount is a different filesystem, so hardlinking would warn.
ENV UV_LINK_MODE=copy

WORKDIR /app

# Dependencies resolve from the lockfile alone, so this layer is cached until
# pyproject.toml or uv.lock actually changes -- editing src/ does not rebuild it.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.10-alpine

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp

# Nothing here needs root. Pass --user "$(id -u):$(id -g)" when running so that
# mounted logs and the refreshed token stay owned by you rather than by nobody.
USER nobody

# A one-shot job: it runs, prints what it did, and exits. Schedule it from the
# host (cron, systemd timer, or a container scheduler) rather than looping here.
# Override the entrypoint to reach the other commands, e.g.
#   docker run ... --entrypoint python IMAGE /app/src/read_playlist.py
ENTRYPOINT ["python", "/app/src/sync.py"]
