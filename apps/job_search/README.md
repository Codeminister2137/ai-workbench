# Job-search prototypes

This directory contains early application experiments. It is not a production
job-search service and does not provide autonomous application approval,
recipient discovery or campaign management.

## Email prototype

`job-email/` contains a structured job application email prototype with a
domain model layer and a delivery scaffold.

### Domain model

| Module | Purpose |
| --- | --- |
| `models.py` | Normalized `JobVacancy`, `CandidateProfile`, `SkillEvidence`, `CVVariant`, `ApplicationPackage`, and `SendReceipt` data classes |
| `evidence.py` | Evidence verification — applications never invent or upgrade qualifications; unbacked claims raise `ProhibitedClaimError` |
| `deduplication.py` | Deterministic entity name/title normalization and duplicate key generation to prevent duplicate applications |
| `preparation.py` | Assembles verified application packages, tailors messages, and selects appropriate CV variants |
| `approval.py` | Enforces explicit human approval workflow; mutating an approved package revokes approval, requiring fresh review |
| `sender.py` | Delivery abstractions: `DryRunEmailTransport` and `YagmailEmailTransport`; raises `UnapprovedApplicationError` if an unapproved package is delivered |
| `outreach_cli.py` | Terminal preview/review and reusable `run_outreach`; sends explicit recipients through guarded delivery |
| `main.py` | Thin compatibility entry point for the guarded outreach workflow |

`main.py` previews by default, without SMTP or credentials. It uses the shared
application preparation formatter and displays recipient, subject, body,
attachment path and a digest of the exact materials. Open the attachment locally
to review its contents. To send, supply `--send` and type `send <recipient>` at
each package's prompt. Empty/other answers skip; EOF or interruption stops the
batch. Attachment changes during review require a new preview.

```powershell
# Preview only
python apps/job_search/job-email/main.py recruiter@example.com
# Request per-package review and delivery
python apps/job_search/job-email/main.py --send recruiter@example.com
```

SMTP setup occurs only after approval. Successful delivery appends the recipient
to the existing sent-file history; failed delivery does not. Contacts already
in history and repeated command-line recipients are skipped. If SMTP succeeds
but history recording fails, the batch stops and asks for manual reconciliation;
the sent-file is not a transactional or concurrent delivery ledger.

Credentials come from `GMAIL_EMAIL` and `GMAIL_PASSWORD` in the process
environment. Applicant details, portfolio/profile links, attachment path and
sent-file path also have environment overrides. Default personal details in
`outreach_cli.py` are placeholders; inspect `_load_config` before use.

This prototype has its own Poetry metadata and is not a member of the root
`uv` workspace for dependency resolution purposes, though it is listed as a
workspace member for path resolution.

### Tests

`approve_package` requires a readable attachment and records a digest binding
the recipient, subject, body, attachment path/variant and exact attachment bytes.
Changing any reviewed materials invalidates approval. `deliver_application`
always enforces approval, including when the legacy `require_approval=False`
argument is supplied, and sends a temporary copy of verified attachment bytes.
The transport must read that copy synchronously; it is deleted after the call.
Keep the returned SENT/FAILED package rather than reusing an old approved object.
Persistent/concurrent delivery deduplication is not implemented.

The full workspace test runner includes domain and terminal-review regression
tests in the isolated `job-search` group. Tests use synthetic transport receipts
and temporary attachments; no SMTP calls are made.

```powershell
python -m uv run pytest apps/job_search/job-email/test_job_search.py
```

## Privacy and limitations

Keep credentials, CV attachments, recipient lists and sent-email state local.
PDF attachments and `sent_emails.txt` are ignored; the ignore rules do not
sanitize message content or protect stdout, which includes recipient
information. Gmail receives the submitted message, attachment and recipient
addresses.

The broader planned job-search automation remains unimplemented. Do not treat
provider availability or a successful email send as consent to automate
applications. See the repository's [privacy guide](../../docs/publication.md)
and [architecture](../../docs/architecture.md).
