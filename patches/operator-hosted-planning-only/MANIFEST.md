# H1 hosted planning-only patch — manifest

## Base

- Repository: `remote-ai-operator`
- Base commit: `cc3577e`
- Slice: fix (b) — hosted planning-only enforcement; fix (a) design only

## Contents (mirror paths under the sibling checkout)

| Patch path | Target path | Kind |
| --- | --- | --- |
| `src/remote_operator/web.py` | `src/remote_operator/web.py` | modified (full file) |
| `tests/test_hosted_planning_only.py` | `tests/test_hosted_planning_only.py` | new tests |
| `DESIGN.md` | — (review doc, not applied) | doc |
| `MANIFEST.md` | — (this file, not applied) | doc |

Change summary in `web.py`: new `HOSTED_PLANNING_ONLY_MESSAGE` constant plus a
hosted gate in `_supervisor_routes.approve_plan` — hosted `execute=true`
returns 409 with that message, hosted `execute=false` records a planning-only
approval, owner behavior unchanged. No other file is modified. No wiring, no
activation, no secrets.

## Apply order

1. Copy `src/remote_operator/web.py` to `src/remote_operator/web.py`.
2. Copy `tests/test_hosted_planning_only.py` to
   `tests/test_hosted_planning_only.py`.
3. Run validation below. There is no step 3: do not implement the fix-(a)
   hosted drain from `DESIGN.md` without separate review (it changes
   multi-subject execution semantics).

## Validation steps

From the `remote-ai-operator` checkout:

1. `ruff check src/remote_operator/web.py tests/test_hosted_planning_only.py`
   (check only, never `--fix`).
2. `python -m pytest tests/test_hosted_planning_only.py -q` — local only, no
   inference, no network; uses synthetic fixtures and temp dirs.
3. `python -m pytest tests/test_hosted.py tests/test_supervisor.py
   tests/test_owner_settings.py tests/test_web.py -q` — regression: existing
   hosted/supervisor/owner behavior unchanged.

## Files written (this patch dir)

- `src/remote_operator/web.py`
- `tests/test_hosted_planning_only.py`
- `DESIGN.md`
- `MANIFEST.md`
