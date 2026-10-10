# Openings manual-import mirror fix

Owner-approved integration boundary: external REST API with a reviewed upstream
fix, rather than depending on Openings' internal collector interface.

`manual-import-mirrors.patch` targets Openings commit
`156dedef348747652a72c961edde3eb103452c6d` (0.4.2). Upstream code is MIT;
its copyright and licence are retained in `LICENSE`.

The manual job endpoint previously updated a matching canonical vacancy without
adding the second source posting. The patch uses the existing collector upsert
when a new posting key matches an existing vacancy. This retains canonical
provenance, mirrors and application status, keeps distinct requisitions from
the same source separate, and refuses blacklisted mirrors.

In a separately reviewed checkout of that exact upstream revision, check the
patch before applying it:

```text
git apply --check /absolute/path/to/manual-import-mirrors.patch
git apply /absolute/path/to/manual-import-mirrors.patch
```

This repository has not installed, deployed or submitted the fix upstream.
The isolated SQLite probe uses real upstream persistence and selected service
methods, with scoring and embeddings stubbed. It verifies mirror/status/replay
semantics, not the complete FastAPI application or deployment. Full upstream
tests and a synthetic API trial remain required before real posting intake.

The local bridge in `apps/job_search/job-email/openings_api.py` refuses writes
unless its operator sets `mirror_fix_verified=True`. This is an explicit
operator assertion, not server attestation: do not set it for an unpatched or
unvalidated deployment. Reads use the existing JSON export adapter.

Future deployment must explicitly bind the server to loopback, configure its
API token, and resolve its persistence/embedding configuration. The bare web
entrypoint binds all interfaces; embeddings may download assets by default.
No deployment settings, credentials or downloads are supplied by this patch.
