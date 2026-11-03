# Operator serve rehearsal (patch candidate for remote-ai-operator)

`rehearse.py` drives the served task lifecycle over HTTP exactly the way the
phone UI does: create → run → review → approve → completed, plus a
reject-path task and event coverage. Stdlib-only, no dependencies.

## Run (from ai-workbench, $0 against scripted serve)

```powershell
.venv/Scripts/python.exe patches/operator-rehearsal/rehearse.py --env-file .\.env
```

- `--env-file` must define `OPERATOR_ACCESS_TOKEN` (the serve's Bearer token).
  The token is read at runtime and never printed; nonces in output are
  redacted to their last 4 characters.
- `--base` defaults to `http://127.0.0.1:8765`.

## Verified

2026-11-02 ~11:55Z against owner-started scripted serve (PID 17700):
`REHEARSAL OK` — 11/11 checks, approve path completed with 15 events,
reject path terminal `rejected`.

## Intended home

`remote-ai-operator/scripts/rehearse.py` (or `tests/` smoke). Apply by copy;
no base-commit coupling (standalone file, stdlib-only).
