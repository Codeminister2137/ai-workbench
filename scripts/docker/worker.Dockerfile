# Mai worker image (ADR-095 phase 2): runnable agent runtime.
# python:3.14-slim matches the repo (requires-python >=3.13,<3.15;
# local venv is 3.14) plus git and a pinned uv. The repo is baked in
# and installed from the lockfile; no credentials, plans, or runtime
# state enter the image (see .dockerignore). The worker runs as
# numeric uid 65532 via the launcher, so no username is baked in.
FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages ./packages
COPY apps ./apps
COPY scripts ./scripts

RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["ai-assistant", "--help"]
