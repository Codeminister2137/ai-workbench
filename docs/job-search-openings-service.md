# Openings kept service

Installed 2026-11-13 per owner adoption answer `1d8f4fdf` (kept service
with scheduler). Pinned upstream `156dedef` (v0.4.2, MIT) — the same
revision the trial and reuse review validated.

## Layout (all under `apps/job_search/openings-svc/`, gitignored)

- `upstream/` — pinned source checkout carrying ONE maintained patch:
  `integrations/openings/manual-import-mirrors.patch` (manual import with
  a new posting key routes through collector upsert, retaining both
  postings and original provenance; the patch's trailing-newline hunk is
  moot — the checkout already ends with newline). Re-apply after any
  upstream refresh, then reinstall + replay-check (probe kept at
  `$env:TEMP/mirror-check.py` pattern; verified green 2026-11-13).
- `.venv/` — service interpreter (py3.14) with `openings` installed.
- `data/` — `OPENINGS_DATA_DIR`: `config/settings.yaml`, `db/openings.db`,
  `logs/`, `attachments/`. The database is the durable archive.
- `api-token.txt` — random API token (read by the web wrapper at start).
  Secret: never commit, never log.

## Scheduled tasks (both as the owner, no stored password)

- `OpeningsWeb` — at logon: `scripts/openings-web.cmd` serves the
  dashboard/API on **127.0.0.1:8501**. The upstream `openings-web` entry
  point hardcodes `0.0.0.0`, so the wrapper launches uvicorn on loopback
  directly. Restart on failure x3. Token-gated (`token_required: true`).
- `OpeningsCollect` — daily 06:30: `scripts/openings-collect.cmd` runs one
  `openings run` (missed runs start when available).

Register/remove: `scripts/register-openings-service.ps1 [-At HH:mm] [-Unregister]`.

## Install-time decisions (all reversible in `settings.yaml`)

- Embeddings OFF (trial parity; avoids the ~90MB ONNX download).
- Sources: LinkedIn + Indeed/Poland (both probed green 2026-11-13).
- Scoring: example defaults; NOT personalized (owner criteria pending).
- Notifications OFF (no Telegram bot configured).
- Log timezone: Europe/Warsaw.

## Ops

- Smoke: `openings.exe healthcheck` (expect 4/4 OK) with `OPENINGS_DATA_DIR`
  set; web: `GET /api/dashboard/auth` → `{"token_required":true}`.
- Logs: `data/logs/openings.log`. DB: `data/db/openings.db` (SQLite).
- Restart web now: `schtasks /run /tn OpeningsWeb` (or `/end` then `/run`).
- Uninstall: run the register script with `-Unregister`, then delete the
  `openings-svc/` directory (the DB goes with it — back up first if kept).

## Follow-ups (not done at install)

- Personalize `scoring.keywords/weights` + queries once the owner supplies
  criteria; `openings rescore --dry-run` previews the effect.
- Polish-board gap stands (Just Join IT, Pracuj.pl, RocketJobs need adapters).
- MCP surface + our `openings_api.py` bridge + dashboard UI build (npm)
  remain unwired; API verified read-path only.
