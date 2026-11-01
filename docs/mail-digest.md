# Mail digest (slices 1-2)

Gmail probe/fetch plus optional hosted summary. Slice 1 (--probe, --fetch) is local-only: no hosted calls, no sending. Slice 2 (--summarize) sends subject+snippet lines to Meta Standard (a no-training route) and reports usage plus a USD estimate.

## Usage

```powershell
# Verify the IMAP SSL login; prints PROBE_OK or PROBE_FAIL <reason>
python scripts/mail_digest.py --probe

# Fetch the latest N INBOX mails (newest first) into a JSON file
python scripts/mail_digest.py --fetch 10 --out digest.json

# Summarize a digest via the hosted model (spends grant cents)
python scripts/mail_digest.py --summarize digest.json --out summary.json
```

## Credentials

Reuses `read_gmail_config` from `scripts/loop_notify.py`: process
environment (`GMAIL_EMAIL` / `GMAIL_PASSWORD`), then repo-root `.env`,
then `apps/job_search/job-email/.env`.

`--summarize` needs `META_API_KEY` (process env, else repo-root `.env`)
and refuses digests over 60,000 characters with `digest-too-large`.

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
