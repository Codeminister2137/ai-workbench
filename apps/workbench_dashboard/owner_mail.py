"""Owner-only email notifications over stdlib SMTP; silent unless configured.

Adapted from remote-operator ``notify.py``/``settings.py`` mechanics onto
dashboard shapes: SMTP settings come from ``WORKBENCH_*`` environment
variables (never from the config file or request bodies), delivery is
fail-closed to the configured owner address, and every send attempt is
captured in a receipt. Missing SMTP configuration means a silent skip —
never a crash and never dry-run receipt spam.

When ``WORKBENCH_*`` is absent, configuration falls back to the single
``GMAIL_EMAIL``/``GMAIL_PASSWORD`` credential pair (process environment,
then the repository-root ``.env`` file) over Gmail SMTP — the same pair
``scripts/loop_notify.py`` uses, so one credential provisions both paths.
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
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_EMAIL_ENV = "GMAIL_EMAIL"
GMAIL_PASSWORD_ENV = "GMAIL_PASSWORD"
REPO_ROOT = Path(__file__).resolve().parents[2]
SMTP_TIMEOUT_SECONDS = 15
MAX_SUBJECT_CHARS = 300
MAX_BODY_CHARS = 50_000
SUPERVISION_MODES = ("attended", "unattended")

# Owner decision 2026-11-18 (inbox f06b15e4): mail only during unattended
# sessions; attended communication stays in chat, inbox items and documents.
# ``paused`` is never terminal and never mailed.
ATTENDED_NOTIFY_STATUSES = frozenset()
UNATTENDED_NOTIFY_STATUSES = frozenset({"completed", "failed", "cancelled", "waiting_on_owner"})


def _read_env_file(path: Path) -> dict[str, str]:
    """Read ``GMAIL_*`` entries from a dotenv file (values never logged)."""
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
        if name in (GMAIL_EMAIL_ENV, GMAIL_PASSWORD_ENV) and name not in values:
            values[name] = value.strip().strip("\"'")
    return values


def load_smtp_config(
    env: Mapping[str, str] | None = None, *, root: Path | str | None = None
) -> dict:
    """Read SMTP settings from ``env`` (default: process environment).

    ``WORKBENCH_*`` wins when complete; otherwise the ``GMAIL_*`` pair is
    resolved from the same mapping, then from ``root/.env`` (default: the
    repository root) over Gmail SMTP. Anything else raises ``ValueError``.
    """
    source = os.environ if env is None else env
    owner = (source.get("WORKBENCH_OWNER_EMAIL") or "").strip()
    host = (source.get("WORKBENCH_SMTP_HOST") or "").strip()
    if owner and host:
        return _explicit_smtp_config(source, owner, host)
    email = (source.get(GMAIL_EMAIL_ENV) or "").strip()
    password = source.get(GMAIL_PASSWORD_ENV) or ""
    if not (email and password):
        base = Path(root) if root is not None else REPO_ROOT
        found = _read_env_file(base / ".env")
        email = email or found.get(GMAIL_EMAIL_ENV, "")
        password = password or found.get(GMAIL_PASSWORD_ENV, "")
    if email and password:
        return {
            "owner": email,
            "host": GMAIL_SMTP_HOST,
            "port": DEFAULT_SMTP_PORT,
            "username": email,
            "password": password,
            "starttls": True,
        }
    raise ValueError(
        "Set WORKBENCH_OWNER_EMAIL and WORKBENCH_SMTP_HOST "
        "(or GMAIL_EMAIL/GMAIL_PASSWORD) to notify"
    )


def _explicit_smtp_config(source: Mapping[str, str], owner: str, host: str) -> dict:
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


def mail_configured(
    env: Mapping[str, str] | None = None, *, root: Path | str | None = None
) -> bool:
    """Return True when owner-mail SMTP settings are present (no secrets)."""
    try:
        load_smtp_config(env, root=root)
    except (ValueError, OSError):
        return False
    return True


def _send_owner_mail_now(
    *,
    to: str,
    subject: str,
    body: str,
    config: dict,
    dry_run: bool = True,
    receipts_dir: Path,
    dedupe_key: str | None = None,
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
    if dedupe_key:
        receipt["dedupe_key"] = dedupe_key
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


def _mail_text(value: object, limit: int = 300) -> str:
    """Accept bounded single-line text, never serialize arbitrary payloads."""
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _run_label(summary: Mapping[str, object]) -> str:
    return {
        "completed": "Done",
        "failed": "Failed",
        "waiting_on_owner": "Blocked",
        "cancelled": "Cancelled",
    }.get(str(summary.get("status")), "Run update")


def format_run_subject(summary: Mapping[str, object]) -> str:
    title = _mail_text(summary.get("title"), 160) or "Untitled run"
    return f"{_run_label(summary)}: {title}"


def format_run_mail(summary: Mapping[str, object]) -> str:
    """Render allowlisted run facts without prompts, receipts or JSON dumps."""
    status = summary.get("status")
    title = _mail_text(summary.get("title")) or "Untitled run"
    outcomes = {
        "completed": f"Completed: {title}.",
        "failed": f"Could not complete: {title}.",
        "waiting_on_owner": f"Stopped for owner input: {title}.",
        "cancelled": f"Cancelled: {title}.",
    }
    outcome = outcomes.get(str(status), "See the dashboard run report for the outcome.")
    error = _mail_text(summary.get("error"), 500)
    if error:
        outcome += f" Reason: {error}"
    source = _mail_text(summary.get("inbox_id"), 64)
    triage = _mail_text(summary.get("triage_item"), 64)
    shipment = summary.get("shipment")
    shipment = shipment if isinstance(shipment, Mapping) else {}
    review = _mail_text(shipment.get("merge_item"), 64)
    merged = _mail_text(shipment.get("merged_sha"), 64)
    if status == "waiting_on_owner":
        next_step = (
            f"Needs owner input; inbox:{source}."
            if source
            else "Needs owner input; see the dashboard run report."
        )
    elif triage:
        next_step = f"Triage queued; inbox:{triage}."
    elif merged:
        next_step = f"Merged as {merged}."
    elif review:
        next_step = f"Integration review queued; inbox:{review}."
    else:
        next_step = "See the dashboard run report; no queued follow-up recorded."
    refs = list(dict.fromkeys(ref for ref in (source, triage, review) if ref))
    machine = f"Refs: run:{_mail_text(summary.get('run_id'), 8) or '?'}"
    if refs:
        machine += " | " + " ".join(f"inbox:{ref}" for ref in refs)
    return "\n".join(
        [
            _run_label(summary),
            f"Title: {title}",
            f"Outcome: {outcome}",
            f"Next: {next_step}",
            "",
            machine,
        ]
    )


def notify_plan(
    supervision: str,
    receipts_dir: Path,
    env: Mapping[str, str] | None = None,
    *,
    root: Path | str | None = None,
) -> tuple[Callable[[Mapping[str, object]], dict] | None, frozenset[str]]:
    """Return ``(sender, notify_on)`` for terminal run outcomes.

    A missing SMTP configuration yields a ``None`` sender (silent skip);
    otherwise the sender mails summaries whose status is in ``notify_on``.
    Never raises for settings or config problems.
    """
    try:
        config = load_smtp_config(env, root=root)
    except (ValueError, OSError):
        logger.warning("supervision without SMTP settings; not notifying")
        return None, UNATTENDED_NOTIFY_STATUSES
    if supervision == "unattended":
        notify_on = UNATTENDED_NOTIFY_STATUSES
    else:
        notify_on = ATTENDED_NOTIFY_STATUSES

    def _send(summary: Mapping[str, object]) -> dict:
        run_id = str(summary.get("run_id", "?"))
        key = f"{run_id}:{summary.get('status', '?')}"
        if _already_mailed(receipts_dir, key):
            return {"to": config["owner"], "sent": False, "deduped": True, "dedupe_key": key}
        return send_owner_mail(
            to=config["owner"],
            subject=format_run_subject(summary),
            body=format_run_mail(summary),
            config=config,
            dry_run=False,
            receipts_dir=receipts_dir,
            dedupe_key=key,
            supervision=supervision,
            data_dir=receipts_dir.parent,
            blocker=summary.get("status") in {"failed", "waiting_on_owner"},
        )

    return _send, notify_on


def _already_mailed(receipts_dir: Path, dedupe_key: str) -> bool:
    """True when a sent receipt already carries this outcome key."""
    try:
        files = sorted(receipts_dir.glob("notify-*.json"))
    except OSError:
        return False
    for path in files:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            isinstance(receipt, dict)
            and receipt.get("dedupe_key") == dedupe_key
            and receipt.get("sent") is True
        ):
            return True
    return False


def shared_mail_root(root: Path = REPO_ROOT) -> Path:
    """Resolve linked worktrees to the main checkout's notification state."""
    marker = root / ".git"
    if marker.is_file():
        git_dir = Path(marker.read_text(encoding="utf-8").strip().removeprefix("gitdir: "))
        if not git_dir.is_absolute():
            git_dir = root / git_dir
        common_file = git_dir / "commondir"
        if common_file.exists():
            return (git_dir / common_file.read_text(encoding="utf-8").strip()).resolve().parent
    return root


def send_owner_mail(
    *,
    to: str,
    subject: str,
    body: str,
    config: dict,
    dry_run: bool = True,
    receipts_dir: Path,
    dedupe_key: str | None = None,
    supervision: str | None = None,
    blocker: bool = False,
    all_work_blocked: bool = False,
    data_dir: Path | None = None,
) -> dict:
    """Persist live notifications for the hourly unattended digest.

    Only an explicitly confirmed blocker of all work bypasses cadence.
    Dry runs retain the transport validation/receipt contract without queuing.
    """
    if dry_run:
        return _send_owner_mail_now(
            to=to,
            subject=subject,
            body=body,
            config=config,
            dry_run=True,
            receipts_dir=receipts_dir,
            dedupe_key=dedupe_key,
        )
    if to != config["owner"]:
        raise ValueError("Refusing to send a notification off the owner address")
    if not subject.strip() or len(subject) > MAX_SUBJECT_CHARS or len(body) > MAX_BODY_CHARS:
        raise ValueError("Invalid notification subject or body length")
    from owner_digest import queue_notification

    root = shared_mail_root()
    if supervision is None:
        from dashboard_config import load_config

        supervision = load_config(root / "apps/workbench_dashboard/dashboard.json").supervision
    return queue_notification(
        data_dir=data_dir or root / "apps/workbench_dashboard/data",
        supervision=supervision,
        subject=subject,
        body=body,
        config=config,
        dedupe_key=dedupe_key,
        blocker=blocker,
        all_work_blocked=all_work_blocked,
    )
