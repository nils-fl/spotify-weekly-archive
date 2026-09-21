# librespot pins Python >=3.10,<3.11, so the base image is not a free choice.
FROM python:3.10-slim AS builder

# librespot is installed from git, so git is needed at build time (but not at
# runtime, which is why this is a separate stage).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# Pin uv for reproducible builds; bump deliberately rather than drifting.
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


FROM python:3.10-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

# A one-shot job: it runs, prints what it did, and exits. Schedule it from the
# host (cron, systemd timer, or a container scheduler) rather than looping here.
# Override the entrypoint to reach the other commands, e.g.
#   docker run ... --entrypoint python IMAGE /app/src/read_playlist.py
ENTRYPOINT ["python", "/app/src/sync.py"]
