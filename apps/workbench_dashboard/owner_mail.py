"""Owner-only email notifications over stdlib SMTP; silent unless configured.

Adapted from remote-operator ``notify.py``/``settings.py`` mechanics onto
dashboard shapes: SMTP settings come from ``WORKBENCH_*`` environment
variables (never from the config file or request bodies), delivery is
fail-closed to the configured owner address, and every send attempt is
captured in a receipt. Missing SMTP configuration means a silent skip —
never a crash and never dry-run receipt spam.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import smtplib
import ssl
import time
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 15
MAX_SUBJECT_CHARS = 300
MAX_BODY_CHARS = 50_000
SUPERVISION_MODES = ("attended", "unattended")

# Attended mails only the run events that need the owner; unattended mails
# every terminal outcome. ``paused`` is never terminal and never mailed.
ATTENDED_NOTIFY_STATUSES = frozenset({"failed", "waiting_on_owner"})
UNATTENDED_NOTIFY_STATUSES = frozenset({"completed", "failed", "cancelled", "waiting_on_owner"})


def load_smtp_config(env: Mapping[str, str] | None = None) -> dict:
    """Read SMTP settings from ``env`` (default: process environment)."""
    source = os.environ if env is None else env
    owner = (source.get("WORKBENCH_OWNER_EMAIL") or "").strip()
    host = (source.get("WORKBENCH_SMTP_HOST") or "").strip()
    if not owner or not host:
        raise ValueError("Set WORKBENCH_OWNER_EMAIL and WORKBENCH_SMTP_HOST to notify")
    try:
        port = int(source.get("WORKBENCH_SMTP_PORT", str(DEFAULT_SMTP_PORT)))
    except ValueError:
        raise ValueError("WORKBENCH_SMTP_PORT must be an integer") from None
    if not 1 <= port <= 65535:
        raise ValueError("WORKBENCH_SMTP_PORT must be between 1 and 65535")
    return {
        "owner": owner,
        "host": host,
        "port": port,
        "username": (source.get("WORKBENCH_SMTP_USER") or "").strip(),
        "password": source.get("WORKBENCH_SMTP_PASS") or "",
        "starttls": (source.get("WORKBENCH_SMTP_STARTTLS") or "1") != "0",
    }


def mail_configured(env: Mapping[str, str] | None = None) -> bool:
    """Return True when owner-mail SMTP settings are present (no secrets)."""
    try:
        load_smtp_config(env)
    except (ValueError, OSError):
        return False
    return True


def send_owner_mail(
    *,
    to: str,
    subject: str,
    body: str,
    config: dict,
    dry_run: bool = True,
    receipts_dir: Path,
) -> dict:
    """Send one owner notification; returns the persisted receipt."""
    if to != config["owner"]:
        raise ValueError("Refusing to send a notification off the owner address")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > MAX_SUBJECT_CHARS:
        raise ValueError("Notification subject requires 1-300 characters")
    if not isinstance(body, str) or len(body) > MAX_BODY_CHARS:
        raise ValueError("Notification body must be text up to 50000 characters")
    receipt = {
        "to": to,
        "subject": subject,
        "dry_run": bool(dry_run),
        "sent": False,
        "error": None,
        "finished": time.time(),
    }
    if not dry_run:
        try:
            _deliver(config, to, subject, body)
        except (OSError, TimeoutError, ssl.SSLError, smtplib.SMTPException) as exc:
            receipt["error"] = f"{type(exc).__name__}: {exc}"[:500]
        else:
            receipt["sent"] = True
    receipts_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(receipt["finished"]))
    target = receipts_dir / f"notify-{stamp}-{secrets.token_hex(4)}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt), encoding="utf-8")
    tmp.replace(target)
    receipt["receipt"] = target.name
    return receipt


def _deliver(config: dict, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = config["username"] or config["owner"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    if config["port"] == 465:
        smtp = smtplib.SMTP_SSL(
            config["host"],
            config["port"],
            timeout=SMTP_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        )
    else:
        smtp = smtplib.SMTP(config["host"], config["port"], timeout=SMTP_TIMEOUT_SECONDS)
    with smtp:
        smtp.ehlo()
        if config["port"] != 465 and config["starttls"]:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if config["username"]:
            smtp.login(config["username"], config["password"])
        smtp.send_message(message)


def format_run_mail(summary: Mapping[str, object]) -> str:
    """Render a short plain-text body for a terminal run summary."""
    lines = [
        f"Run {summary.get('run_id', '?')} finished: {summary.get('status', '?')}.",
        f"Title: {summary.get('title') or '(untitled)'}",
    ]
    error = summary.get("error")
    if error:
        lines += ["", f"Error: {error}"]
    lines += ["", "Details:", json.dumps(dict(summary), indent=2, default=str)]
    return "\n".join(lines)


def notify_plan(
    supervision: str,
    receipts_dir: Path,
    env: Mapping[str, str] | None = None,
) -> tuple[Callable[[Mapping[str, object]], dict] | None, frozenset[str]]:
    """Return ``(sender, notify_on)`` for terminal run outcomes.

    A missing SMTP configuration yields a ``None`` sender (silent skip);
    otherwise the sender mails summaries whose status is in ``notify_on``.
    Never raises for settings or config problems.
    """
    try:
        config = load_smtp_config(env)
    except (ValueError, OSError):
        logger.warning("supervision without SMTP settings; not notifying")
        return None, UNATTENDED_NOTIFY_STATUSES
    if supervision == "unattended":
        notify_on = UNATTENDED_NOTIFY_STATUSES
    else:
        notify_on = ATTENDED_NOTIFY_STATUSES

    def _send(summary: Mapping[str, object]) -> dict:
        run_id = str(summary.get("run_id", "?"))
        return send_owner_mail(
            to=config["owner"],
            subject=f"[workbench] run {summary.get('status', '?')}: {run_id[:8]}",
            body=format_run_mail(summary),
            config=config,
            dry_run=False,
            receipts_dir=receipts_dir,
        )

    return _send, notify_on
