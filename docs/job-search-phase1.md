# Job search Phase 1: unify the email sender

Phase 1 scope (structured application record `prepared -> approved -> sent`,
preparation isolated from sending, existing transports unchanged) was
assessed against `apps/job_search/job-email/` on
`feature/loop2b-sender-unify`. Most of the Definition of Done already
existed; this slice adds only the missing pieces.

## What already existed

- `models.py`: `ApplicationPackage` with `application_id`, `vacancy_ref`,
  `contact_email`, `cv_variant_id`, subject/body bound by
  `materials_digest`, `created_at_utc`/`approved_at_utc`, and a
  `SendReceipt` outcome (`success`, `recipient`, `timestamp_utc`,
  `error_message`, `transport_name`). Lifecycle covers
  `PREPARED -> APPROVED -> SENT` plus `FAILED`/`SKIPPED`.
- `preparation.py`: `prepare_application` builds verified packages and never
  touches a transport. `sender.py`: `deliver_application` delivers only
  digest-approved packages via a verified temporary snapshot; the legacy
  `require_approval=False` bypass is refused.
- Send recording: receipt on the returned package, `outreach_cli.py`
  sent-file ledger, and `scripts/loop_notify.py` JSON receipts.

## What this slice changed

- `sender.py`: the `EmailTransport` contract (and both transports) now
  declare `attachments: str | None`, matching the live `loop_notify.py`
  consumer, which sends text-only pings with `attachments=None`.
  Annotation-only: delivery behavior is unchanged. `DryRunEmailTransport`
  with `check_attachment_exists=True` now reports a missing/`None`
  attachment as a failure receipt instead of raising `TypeError`.
- `tests/test_sender_unify.py` (new, `cli` group in `scripts/run-tests.py`):
  unapproved/rejected/bypass deliveries are refused with zero dry-run
  sends; a loop_notify-style consumer flow prepares, approves, delivers,
  and writes a structured JSON application record without modifying the
  sender; preparation/sending isolation is pinned by a source tripwire;
  DryRun and Yagmail failure behavior is pinned. All dry-run, no network.
- (`docs/plans/` is not present in this checkout, so Phase 1 scope was
  taken from the plan prompt: record, separation, recording.)

## Gates

```powershell
C:\Users\Jakub\PycharmProjects\ai-workbench\.venv\Scripts\ruff.exe check --fix tests/test_sender_unify.py apps/job_search/job-email/sender.py scripts/run-tests.py
C:\Users\Jakub\PycharmProjects\ai-workbench\.venv\Scripts\ruff.exe format tests/test_sender_unify.py apps/job_search/job-email/sender.py scripts/run-tests.py
C:\Users\Jakub\PycharmProjects\ai-workbench\.venv\Scripts\python.exe -m pytest tests/test_sender_unify.py tests/test_loop_notify.py
C:\Users\Jakub\PycharmProjects\ai-workbench\.venv\Scripts\python.exe -m pytest apps/job_search/job-email/test_job_search.py apps/job_search/job-email/test_email_cli.py
C:\Users\Jakub\PycharmProjects\ai-workbench\.venv\Scripts\python.exe scripts/run-tests.py --list
```
