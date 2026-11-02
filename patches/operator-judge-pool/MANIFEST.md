# Judge pool patch — manifest

## Base

- Repository: `remote-ai-operator`
- Base commit: `cc3577e`
- Slice: inert finite judge-pool (config + admission + shared ledger + tests)

## Contents (mirror paths under the sibling checkout)

| Patch path | Target path | Kind |
| --- | --- | --- |
| `src/remote_operator/judge_pool.py` | `src/remote_operator/judge_pool.py` | new module |
| `tests/test_judge_pool.py` | `tests/test_judge_pool.py` | new tests |
| `DESIGN.md` | — (review doc, not applied) | doc |
| `MANIFEST.md` | — (this file, not applied) | doc |

No existing file is modified. No wiring, no activation, no secrets.

## Apply order

1. Copy `src/remote_operator/judge_pool.py` to
   `src/remote_operator/judge_pool.py`.
2. Copy `tests/test_judge_pool.py` to `tests/test_judge_pool.py`.
3. Run validation below. There is no step 3: do not wire the pool into
   `web.py` / `deployment.py` / `modal_app.py` without owner approval of
   the amount and activation (see `DESIGN.md`).

## Validation steps

From the `remote-ai-operator` checkout (read-only checks first):

1. `ruff check src/remote_operator/judge_pool.py tests/test_judge_pool.py`
   (check only, never `--fix`).
2. `python -m pytest tests/test_judge_pool.py -q` — local only, no
   inference, no network; uses synthetic fixtures and temp dirs.
3. `python -m pytest tests/test_judges.py tests/test_hosted.py
   tests/test_sessions.py -q` — regression: existing admission behavior
   unchanged (this patch adds files only, so these must pass untouched).

## Files written (this patch dir)

- `src/remote_operator/judge_pool.py`
- `tests/test_judge_pool.py`
- `DESIGN.md`
- `MANIFEST.md`
