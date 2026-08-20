# Multi-stage build for loom-ai server and CLI.
#
# Build:  docker build -t loom-ai .
# Run:    docker run -e LOOM_HOST=0.0.0.0 -e LOOM_API_KEY=secret -p 5000:5000 loom-ai
#
# Targets:
#   server  (default) -- FastAPI server with all optional backends
#   client            -- CLI-only image, no server dependencies

# ── builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY loom_ai/ loom_ai/

RUN pip install --no-cache-dir --prefix=/install \
    ".[server,postgresql]"

# ── server (default) ────────────────────────────────────────────────
FROM python:3.12-slim AS server

RUN groupadd -r loom && useradd -r -g loom -s /sbin/nologin loom

COPY --from=builder /install /usr/local

WORKDIR /app
COPY loom_ai/ loom_ai/

USER loom

ENV LOOM_HOST=0.0.0.0 \
    LOOM_PORT=5000

EXPOSE 5000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

ENTRYPOINT ["python", "-m", "loom_ai"]

# ── client ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS client

RUN groupadd -r loom && useradd -r -g loom -s /sbin/nologin loom

WORKDIR /build
COPY pyproject.toml README.md ./
COPY loom_ai/ loom_ai/

RUN pip install --no-cache-dir "." && rm -rf /build

USER loom
WORKDIR /home/loom

ENTRYPOINT ["loom"]
