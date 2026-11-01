# Mail digest (slice 1)

Local-only Gmail probe and fetch. No hosted calls, no sending.

## Usage

```powershell
# Verify the IMAP SSL login; prints PROBE_OK or PROBE_FAIL <reason>
python scripts/mail_digest.py --probe

# Fetch the latest N INBOX mails (newest first) into a JSON file
python scripts/mail_digest.py --fetch 10 --out digest.json
```

## Credentials

Reuses `read_gmail_config` from `scripts/loop_notify.py`: process
environment (`GMAIL_EMAIL` / `GMAIL_PASSWORD`), then repo-root `.env`,
then `apps/job_search/job-email/.env`.

## Output schema

`--fetch` writes a JSON list, newest first, one object per mail:

```json
[
  {
    "from": "Alice <alice@example.com>",
    "date": "Sat, 1 Nov 2026 10:00:00 +0100",
    "subject": "Plain hello",
    "message-id": "<plain-1@example.com>",
    "snippet": "Hi there, ...",
    "urls": ["https://example.com/a"]
  }
]
```

`snippet` is the first 200 characters of collapsed plain text
(`text/plain` parts preferred, HTML tags stripped as fallback).
`urls` are deduplicated `http(s)` links from the body (max 20).

## Status and privacy

- `--probe` prints `PROBE_OK`, or `PROBE_FAIL <reason>` with exit code 1.
- `--fetch` prints `FETCH_OK <count>`, or `FETCH_FAIL <reason>` with exit
  code 1 (no file written).
- `<reason>` is coarse only: `missing-credentials`, `auth`, `network`,
  `mailbox`, or `error`. Status output never contains addresses,
  passwords, subjects, or server detail.

## Tests

`tests/test_mail_digest.py` covers probe ok/fail paths, multipart fetch
parsing, and the missing-credential path with a fake `IMAP4` class
monkeypatched over `imaplib`; no network is used.
