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
| `main.py` | Legacy entry point that sends a configured message to explicit command-line recipients via Gmail/`yagmail` |

`main.py` is an older prototype entry point. Running it can send real email;
it is not an installation check.

Credentials come from `GMAIL_EMAIL` and `GMAIL_PASSWORD` in the process
environment. Applicant details, portfolio/profile links, attachment path and
sent-file path also have environment overrides. Default personal details in
`main.py` are placeholders; inspect `_load_config` before use.

This prototype has its own Poetry metadata and is not a member of the root
`uv` workspace for dependency resolution purposes, though it is listed as a
workspace member for path resolution.

### Tests

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
