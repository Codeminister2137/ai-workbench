"""Owner self-service PC sleep scheduling (dashboard Sleep button).

The owner schedules sleep remotely through the dashboard instead of
asking the agent. One owner timer at a time: scheduling while a live
owner timer exists is refused until it is cancelled or fires. Timers
run through the shared workstation-sleep helper; cancelling touches
only the owner timer's own cancel file, never agent timers.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

RECEIPT_DIRNAME = "owner-sleep"
RECEIPT_NAME = "sleep-owner.json"
CANCEL_NAME = "sleep-owner.cancel"
MIN_DELAY_MINUTES = 1
MAX_DELAY_MINUTES = 24 * 60
# Helper -DelaySeconds caps at 600; longer delays use absolute -SleepAtUtc.
HELPER_DELAY_CAP_SECONDS = 600
RECEIPT_WAIT_SECONDS = 10.0
# A "scheduled" receipt this far past due is stale (helper gone or PC asleep
# at fire time). Liveness is receipt-based on purpose: signalling foreign
# pids (os.kill) from sandboxed processes gets the caller killed.
TIMER_STALE_GRACE = timedelta(minutes=15)


def receipt_paths(repo_root: Path) -> tuple[Path, Path]:
    """(receipt, cancel) paths for the single owner timer slot."""
    directory = Path(repo_root) / ".tmp" / RECEIPT_DIRNAME
    return directory / RECEIPT_NAME, directory / CANCEL_NAME


def helper_script(repo_root: Path) -> Path:
    return Path(repo_root) / "scripts" / "workstation-sleep.ps1"


def validate_delay_minutes(delay_minutes: int) -> int:
    """Range-check an owner delay; input errors surface before state checks."""
    if isinstance(delay_minutes, bool) or not isinstance(delay_minutes, int):
        raise ValueError("delay must be an integer number of minutes")
    if not MIN_DELAY_MINUTES <= delay_minutes <= MAX_DELAY_MINUTES:
        raise ValueError(f"delay must be {MIN_DELAY_MINUTES}-{MAX_DELAY_MINUTES} minutes")
    return delay_minutes


def launch_argv(repo_root: Path, *, delay_minutes: int, receipt: Path, cancel: Path) -> list[str]:
    """Build the hidden-helper command for an owner timer."""
    validate_delay_minutes(delay_minutes)
    base = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(helper_script(repo_root)),
        "-Sleep",
        "-ReceiptPath",
        str(receipt),
        "-CancelPath",
        str(cancel),
    ]
    total_seconds = delay_minutes * 60
    if total_seconds <= HELPER_DELAY_CAP_SECONDS:
        return [*base, "-DelaySeconds", str(total_seconds)]
    due = datetime.now(UTC) + timedelta(seconds=total_seconds)
    return [*base, "-SleepAtUtc", due.strftime("%Y-%m-%dT%H:%M:%SZ")]


def spawn_hidden(argv: list[str]) -> None:
    """Launch a detached hidden helper (stubbed in tests)."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(argv, creationflags=creationflags)


def read_receipt(receipt: Path) -> dict | None:
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def receipt_due_utc(payload: dict) -> datetime | None:
    """Due time from a helper receipt, or None when absent/unparseable."""
    raw = payload.get("planned_sleep_utc")
    if not isinstance(raw, str):
        return None
    try:
        due = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    return due


def timer_state(repo_root: Path) -> dict:
    """Current owner-timer state; live only while scheduled and not stale.

    The helper pid stays informational: liveness never signals foreign
    processes (see TIMER_STALE_GRACE).
    """
    receipt, _ = receipt_paths(repo_root)
    payload = read_receipt(receipt)
    if payload is None:
        return {"active": False, "status": "none"}
    status = payload.get("status")
    due = receipt_due_utc(payload)
    stale = bool(due is not None and datetime.now(UTC) >= due + TIMER_STALE_GRACE)
    live = status == "sleep_scheduled" and not stale
    return {
        "active": live,
        "status": status,
        "stale": stale,
        "due_utc": payload.get("planned_sleep_utc"),
        "due_warsaw": payload.get("planned_sleep_warsaw"),
        "pid": payload.get("process_id"),
    }


def schedule_owner_sleep(repo_root: Path, delay_minutes: int, *, launcher=None) -> dict:
    """Schedule owner sleep; refuses while a live owner timer exists."""
    validate_delay_minutes(delay_minutes)
    spawn = launcher or spawn_hidden
    state = timer_state(repo_root)
    if state["active"]:
        raise ValueError(f"owner sleep already scheduled (due {state['due_warsaw']})")
    receipt, cancel = receipt_paths(repo_root)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if cancel.exists():
        cancel.unlink()
    if receipt.exists():
        receipt.unlink()
    spawn(launch_argv(repo_root, delay_minutes=delay_minutes, receipt=receipt, cancel=cancel))
    deadline = time.monotonic() + RECEIPT_WAIT_SECONDS
    while time.monotonic() < deadline:
        payload = read_receipt(receipt)
        if payload is not None and payload.get("status") == "sleep_scheduled":
            return {
                "ok": True,
                "due_utc": payload.get("planned_sleep_utc"),
                "due_warsaw": payload.get("planned_sleep_warsaw"),
                "pid": payload.get("process_id"),
            }
        time.sleep(0.2)
    raise ValueError("sleep helper did not acknowledge scheduling")


def cancel_owner_sleep(repo_root: Path) -> dict:
    """Cancel the owner timer via its own cancel file (agent timers untouched)."""
    receipt, cancel = receipt_paths(repo_root)
    payload = read_receipt(receipt)
    if payload is None or payload.get("status") != "sleep_scheduled":
        return {"cancelled": False, "status": (payload or {}).get("status", "none")}
    # The cancel file is honored even by a stale-but-unfired helper on wake,
    # so it is always written for a scheduled receipt.
    due = receipt_due_utc(payload)
    stale = bool(due is not None and datetime.now(UTC) >= due + TIMER_STALE_GRACE)
    cancel.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
    deadline = time.monotonic() + RECEIPT_WAIT_SECONDS
    while time.monotonic() < deadline:
        current = read_receipt(receipt)
        if current is not None and current.get("status") == "sleep_cancelled":
            return {"cancelled": True, "status": "sleep_cancelled"}
        time.sleep(0.2)
    if stale:
        return {"cancelled": False, "status": "stale (no acknowledgement; timer presumed gone)"}
    return {"cancelled": False, "status": "cancel sent, no acknowledgement yet"}
