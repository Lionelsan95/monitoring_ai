# syntax=docker/dockerfile:1
# ── Stage 1: builder ──────────────────────────────────────────────────────────
# uv image ships Python 3.12 + uv; used only to resolve and install deps.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Compile bytecode for faster cold starts; copy mode avoids hard-link issues
# between build and runtime stages.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Layer 1: install third-party deps only (cached until lockfile changes)
# --no-install-project skips building the local package — src/ not needed yet.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
        --extra openai \
        --extra anthropic \
        --extra ollama \
        --extra bedrock \
        --extra ui

# Layer 2: application source (cache-busted only when code changes)
COPY src/     ./src/
COPY prompts/ ./prompts/
COPY config.yaml ./
COPY config/  ./config/

# Layer 3: install the local package itself (fast — deps are already cached)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
        --extra openai \
        --extra anthropic \
        --extra ollama \
        --extra bedrock \
        --extra ui


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
# Plain python:3.12-slim — no uv, no build tools, minimal attack surface.
# Python binary lives at /usr/local/bin/python3.12 in both images, so the
# venv symlinks resolve correctly after the COPY.
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=builder /app/.venv    /app/.venv
COPY --from=builder /app/src      /app/src
COPY --from=builder /app/prompts  /app/prompts
COPY --from=builder /app/config.yaml /app/config.yaml
COPY --from=builder /app/config   /app/config

# Persistent data directory (mount a volume here for durable SQLite)
RUN mkdir -p /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

EXPOSE 8000

# Default: API server. Override CMD in compose for the UI service.
CMD ["uvicorn", "entrypoints.api:app", "--host", "0.0.0.0", "--port", "8000"]
