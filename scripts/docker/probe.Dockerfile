# Minimal toolchain image for the ADR-095 Docker worker containment probe.
# Owner-approved provisioning option A (2026-11-19): python:3.12-slim plus git.
# The worker runs as numeric uid 65532, so no username is baked in.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

CMD ["python3", "--version"]
