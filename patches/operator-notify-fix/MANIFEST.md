# Owner-notification gap fix — manifest

## Base

- Repository: `remote-ai-operator`
- Base commit: `cc3577e`
- Slice: run-event mail in every supervision mode + pollable agent inbox

## Contents (mirror paths under the sibling checkout)

| Patch path | Target path | Kind |
| --- | --- | --- |
| `src/remote_operator/supervisor_runner.py` | `src/remote_operator/supervisor_runner.py` | full-file mirror (modified) |
| `src/remote_operator/supervisor_inbox.py` | `src/remote_operator/supervisor_inbox.py` | new module |
| `src/remote_operator/web.py` | `src/remote_operator/web.py` | full-file mirror (modified: inbox route) |
| `src/remote_operator/settings.py` | `src/remote_operator/settings.py` | full-file mirror (modified: docstring) |
| `tests/test_notify_fix.py` | `tests/test_notify_fix.py` | new tests |
| `DESIGN.md` | — (review doc, not applied) | doc |
| `MANIFEST.md` | — (this file, not applied) | doc |

No secrets, no live inference, no real mail sends (tests stub the transport).

## Apply order

1. Copy `src/remote_operator/supervisor_runner.py` to
   `src/remote_operator/supervisor_runner.py`.
2. Copy `src/remote_operator/supervisor_inbox.py` to
   `src/remote_operator/supervisor_inbox.py`.
3. Copy `src/remote_operator/web.py` to `src/remote_operator/web.py`.
4. Copy `src/remote_operator/settings.py` to `src/remote_operator/settings.py`.
5. Copy `tests/test_notify_fix.py` to `tests/test_notify_fix.py`.
6. Run validation below.

## Validation steps

From the `remote-ai-operator` checkout (read-only checks first):

1. `python -m ruff check src/remote_operator/supervisor_runner.py
   src/remote_operator/supervisor_inbox.py src/remote_operator/web.py
   src/remote_operator/settings.py tests/test_notify_fix.py`
   (check only, never `--fix`).
2. `python -m pytest tests/test_notify_fix.py -q` — new regression cover:
   attended mail fired, inbox cursor semantics, missing-config silence.
   Local only; transport stubbed, temp dirs.
3. `python -m pytest tests/test_owner_settings.py
   tests/test_supervisor_runner.py tests/test_run_mail.py
   tests/test_supervisor.py tests/test_owner_questions.py
   tests/test_supervisor_drain_worker.py tests/test_drain_supervision.py
   tests/test_notify.py -q` — regression: existing notify/drain/supervisor
   behavior unchanged (including `test_attended_never_notifies`, which drains
   to `awaiting_approval` and stays silent in attended mode).

## Files written (this patch dir)

- `src/remote_operator/supervisor_runner.py`
- `src/remote_operator/supervisor_inbox.py`
- `src/remote_operator/web.py`
- `src/remote_operator/settings.py`
- `tests/test_notify_fix.py`
- `DESIGN.md`
- `MANIFEST.md`
