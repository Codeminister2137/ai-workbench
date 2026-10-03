# Job-search prototypes

This directory contains early application experiments. It is not a production
job-search service and does not provide autonomous application approval,
recipient discovery or campaign management.

## Email prototype

`job-email/main.py` sends a configured application message and attachment to
explicit command-line recipients through Gmail, using `yagmail`. It records
successful recipients locally to avoid duplicate sends on later invocations.
Running the entry point can send real email; it is not an installation check.

Credentials come from `GMAIL_EMAIL` and `GMAIL_PASSWORD` in the process environment.
Applicant details, portfolio/profile links, attachment path and sent-file path
also have environment overrides. Inspect `_load_config` before use; default
personal details are placeholders. This prototype has its own Poetry metadata
and is not a member of the root `uv` workspace.

## Privacy and limitations

Keep credentials, CV attachments, recipient lists and sent-email state local.
PDF attachments and `sent_emails.txt` are ignored; the ignore rules do not sanitize
message content or protect stdout, which includes recipient information.
Gmail receives the submitted message, attachment and recipient addresses.

The broader planned job-search automation remains unimplemented. Do not treat
provider availability or a successful email send as consent to automate applications.
See the repository's [privacy guide](../../docs/publication.md) and
[architecture](../../docs/architecture.md).
