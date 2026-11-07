"""Owner-self email pings for unattended loop runs.

Delivers through the dashboard's stdlib SMTP mailer
(``apps/workbench_dashboard/owner_mail.py``) over Gmail SMTP; offline pings
record dry-run receipts instead. Every ping writes a JSON receipt under the
run directory.

Standing boundary: pings go only to the owner's own Gmail address, for run
events (objective error, run finished, sleep scheduled) carrying run metadata
(counts, statuses, timings) only. Never prompts, credentials, or third parties.
Each ping also carries the host's current public IP (best effort) so the owner
can reach the machine from outside the home network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "apps" / "workbench_dashboard"

EMAIL_ENV = "GMAIL_EMAIL"
PASSWORD_ENV = "GMAIL_PASSWORD"


def _read_env_file(path: Path) -> dict[str, str]:
    from ai_provider.secrets import read_dotenv_values

    return read_dotenv_values(path, {EMAIL_ENV, PASSWORD_ENV})


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


def _load_owner_mail():
    """Import the dashboard stdlib mailer without installing it."""
    sys.path.insert(0, str(DASHBOARD_DIR))
    import owner_mail  # noqa: PLC0415 - local app module, not installed

    return owner_mail


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


def previous_public_ip(notifications: Path) -> str | None:
    """Latest public_ip from earlier ping receipts, or None. Fail-soft."""
    try:
        candidates = sorted(notifications.glob("*.json"), key=lambda item: item.stat().st_mtime)
    except OSError:
        return None
    for path in reversed(candidates):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue
        address = payload.get("public_ip")
        if isinstance(address, str) and address:
            return address
    return None


LAST_IP_FILENAME = "last-public-ip.txt"


def stable_ip_path(root: Path = ROOT) -> Path:
    """Repo-local last-known-IP file (gitignored scratch, cross-window)."""
    return root / ".tmp" / LAST_IP_FILENAME


def read_last_ip(path: Path) -> str | None:
    """Read the last-known public IP, or None. Fail-soft."""
    try:
        address = path.read_text(encoding="utf-8").strip()
    except (ValueError, UnicodeError, OSError):
        return None
    return address or None


def write_last_ip(path: Path, address: str) -> None:
    """Record the last-known public IP. Fail-soft; never breaks a ping."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(address + "\n", encoding="utf-8")
    except (ValueError, UnicodeError, OSError):
        return


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
    owner_mail = _load_owner_mail()
    config = read_gmail_config()
    owner = config[0] if config else ""
    target = (recipient or owner).strip()
    if not target or (owner and target != owner):
        raise ValueError("Loop pings are restricted to the owner's Gmail address")
    address = public_ip()
    notifications = run_dir / "notifications"
    notifications.mkdir(parents=True, exist_ok=True)
    previous = previous_public_ip(notifications) if address is not None else None
    if previous is None:
        previous = read_last_ip(stable_ip_path())
    if address is not None:
        body = f"{body}\n\nPublic IP: {address}"
        if previous is not None and previous != address:
            body += (
                f"\nNOTE: public IP changed since last ping: "
                f"{previous} -> {address} (update the phone WoL app)"
            )
        write_last_ip(stable_ip_path(), address)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    receipt_path = notifications / f"{event}-{stamp}.json"
    live_config = config if not dry_run else None
    attempts = 0
    try:
        if live_config is not None:
            mail_config = {
                "owner": live_config[0],
                "host": "smtp.gmail.com",
                "port": 587,
                "username": live_config[0],
                "password": live_config[1],
                "starttls": True,
            }
            transport_name = "owner_mail"
            use_live = True
        else:
            mail_config = {
                "owner": target,
                "host": "",
                "port": 587,
                "username": "",
                "password": "",
                "starttls": True,
            }
            transport_name = "dry_run"
            use_live = False
        # Retry transient send failures (e.g. DNS down right after a
        # sleep/wake cycle): run-11 lost its finished email this way.
        # send_owner_mail captures transport errors in its receipt instead
        # of raising; ValueError (bad subject/body/recipient) fails fast.
        sent: bool | None = None
        finished = datetime.now(UTC).isoformat()
        error_message: str | None = None
        for attempt in range(3):
            attempts = attempt + 1
            try:
                mail_receipt = owner_mail.send_owner_mail(
                    to=target,
                    subject=subject,
                    body=body,
                    config=mail_config,
                    dry_run=not use_live,
                    receipts_dir=notifications,
                )
            except ValueError:
                raise
            except Exception:
                mail_receipt = None
                if attempt == 2:
                    raise
                time.sleep(30)
                continue
            sent = mail_receipt["sent"] if use_live else True
            finished = mail_receipt["finished"]
            error_message = mail_receipt["error"]
            if sent or attempt == 2:
                break
            time.sleep(30)
        assert sent is not None
        payload = {
            "success": sent,
            "recipient": target,
            "timestamp_utc": finished,
            "error_message": error_message,
        }
        payload["live"] = bool(use_live and sent)
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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body", default=None)
    group.add_argument("--body-file", type=Path, default=None)
    parser.add_argument("--to", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    body = args.body
    if args.body_file is not None:
        body = args.body_file.read_text(encoding="utf-8-sig")
    receipt = send_ping(
        subject=args.subject,
        body=body,
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
