"""Owner-self email pings for unattended loop runs.

Reuses the job-search prototype's email transports
(``apps/job_search/job-email/sender.py``): real delivery through
``YagmailEmailTransport`` (Gmail app password) and offline ``DryRunEmailTransport``
otherwise. Every ping writes a JSON receipt under the run directory.

Standing boundary: pings go only to the owner's own Gmail address, for run
events (objective error, run finished, sleep scheduled) carrying run metadata
(counts, statuses, timings) only. Never prompts, credentials, or third parties.
Each ping also carries the host's current public IP (best effort) so the owner
can reach the machine from outside the home network.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOB_EMAIL_DIR = ROOT / "apps/job_search/job-email"

EMAIL_ENV = "GMAIL_EMAIL"
PASSWORD_ENV = "GMAIL_PASSWORD"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        name = name.strip()
        if name in (EMAIL_ENV, PASSWORD_ENV) and name not in values:
            values[name] = value.strip().strip("\"'")
    return values


def read_gmail_config(root: Path = ROOT) -> tuple[str, str] | None:
    """Return ``(address, app password)`` or None when not configured.

    Precedence: process environment, repository-root ``.env``, then the
    job-search prototype's ``.env``. Values are never logged.
    """
    email = os.environ.get(EMAIL_ENV, "").strip()
    password = os.environ.get(PASSWORD_ENV, "").strip()
    if email and password:
        return email, password
    for env_file in (root / ".env", root / "apps/job_search/job-email/.env"):
        found = _read_env_file(env_file)
        email = email or found.get(EMAIL_ENV, "")
        password = password or found.get(PASSWORD_ENV, "")
        if email and password:
            return email, password
    return None


def _load_sender():
    sys.path.insert(0, str(JOB_EMAIL_DIR))
    import sender

    return sender


def public_ip(*, timeout: float = 10) -> str | None:
    """Return the host's public IP, or None when it cannot be determined.

    Best effort only: any transport failure, timeout, or implausible answer
    yields None instead of raising, so notification can never break a run.
    """
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as response:
            answer = response.read(64).decode("ascii", errors="strict").strip()
    except Exception:  # noqa: BLE001 - address lookup must fail soft
        return None
    if not answer or len(answer) > 45 or any(char.isspace() for char in answer):
        return None
    return answer


def send_ping(
    *,
    subject: str,
    body: str,
    run_dir: Path,
    event: str,
    recipient: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Send one owner-self ping and record a JSON receipt.

    Raises ``ValueError`` when the recipient is not the owner's own address
    (fail closed: misdirected mail is refused, never rerouted). Transport
    failures are captured in the receipt, never raised, so a broken notifier
    cannot break a run. Returns the receipt dict.
    """
    sender = _load_sender()
    config = read_gmail_config()
    owner = config[0] if config else ""
    target = (recipient or owner).strip()
    if not target or (owner and target != owner):
        raise ValueError("Loop pings are restricted to the owner's Gmail address")
    address = public_ip()
    if address is not None:
        body = f"{body}\n\nPublic IP: {address}"
    notifications = run_dir / "notifications"
    notifications.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = notifications / f"{event}-{stamp}.json"
    live_config = config if not dry_run else None
    attempts = 0
    try:
        if live_config is not None:
            transport = sender.YagmailEmailTransport(live_config[0], live_config[1])
            transport_name = "yagmail"
            use_live = True
        else:
            transport = sender.DryRunEmailTransport()
            transport_name = "dry_run"
            use_live = False
        # Retry transient send failures (e.g. DNS down right after a
        # sleep/wake cycle): run-11 lost its finished email this way.
        result = None
        for attempt in range(3):
            attempts = attempt + 1
            try:
                result = transport.send(
                    to_email=target, subject=subject, contents=body, attachments=None
                )
            except Exception:
                result = None
                if attempt == 2:
                    raise
                time.sleep(30)
                continue
            if result.success or attempt == 2:
                break
            time.sleep(30)
        assert result is not None
        payload = dataclasses.asdict(result)
        payload["live"] = bool(use_live and result.success)
        payload["transport_name"] = transport_name
        payload["attempts"] = attempts
    except Exception as error:  # noqa: BLE001 - ping must never break a run
        payload = {
            "success": False,
            "recipient": target,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "error_message": f"{type(error).__name__}: {str(error)[:300]}",
            "transport_name": "failed",
            "live": False,
            "attempts": attempts,
        }
    payload.update({"event": event, "subject": subject, "public_ip": address})
    receipt_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--to", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    receipt = send_ping(
        subject=args.subject,
        body=args.body,
        run_dir=args.run_dir.resolve(),
        event=args.event,
        recipient=args.to,
        dry_run=args.dry_run,
    )
    print(
        json.dumps(
            {
                "live": receipt["live"],
                "success": receipt["success"],
                "transport": receipt["transport_name"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
