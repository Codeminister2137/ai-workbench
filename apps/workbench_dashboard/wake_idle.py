"""Task-only idle sleep and its shared admission/commit interlock.

Option A is implemented; owner item 4b7c31d0 remains pending retro-confirmation.
Only commit_sleep owns the suspend handoff, so that policy can be revisited.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

GRACE = timedelta(minutes=30)
_LOCK = threading.RLock()


@contextmanager
def interlock(data_dir: Path):
    """Serialize admission and sleep commitment across dashboard processes."""
    data_dir.mkdir(parents=True, exist_ok=True)
    with _LOCK, (data_dir / "wake-idle.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            # Windows locks may extend beyond EOF. Initialize only while locked:
            # reading the locked byte before acquisition fails under contention.
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def cancel_pending(data_dir: Path) -> None:
    """Invalidate only the idle controller's pending handoff."""
    (data_dir / "wake-idle.cancel").touch()


def blockers(data_dir: Path, config_path: Path, now: datetime) -> list[str]:
    from dashboard_config import load_config

    reasons = []
    if load_config(config_path).supervision != "unattended":
        reasons.append("attended")
    for directory in ("inbox", "runs"):
        folder = data_dir / directory
        for path in folder.glob("*.json*"):
            if path.name.endswith(".tmp"):
                continue
            if path.name.endswith(".claim"):
                reasons.append("claimed_run")
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            if directory == "inbox":
                if record.get("status") == "open" and record.get("assignee") == "agent":
                    reasons.append("open_agent_task")
            else:
                if record.get("status") in {"queued", "running", "claimed"}:
                    reasons.append("active_run")
                stamp = record.get("finished_at_utc")
                if stamp:
                    finished = datetime.fromisoformat(stamp)
                    if finished.tzinfo is None:
                        finished = finished.replace(tzinfo=UTC)
                    if now - finished <= GRACE:
                        reasons.append("recent_run")
    return sorted(set(reasons))


def sleep_clock() -> float:
    """Cumulative suspended time; Windows unbiased time excludes sleep."""
    if os.name != "nt":
        raise OSError("wake-idle suspend is Windows-only")
    unbiased = ctypes.c_ulonglong()
    if not ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(unbiased)):
        raise OSError("QueryUnbiasedInterruptTime failed")
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    return ctypes.windll.kernel32.GetTickCount64() / 1000 - unbiased.value / 10_000_000


def commit_sleep(repo_root: Path, data_dir: Path, config_path: Path) -> None:
    """Prepare sleep unlocked; the helper owns the final locked recheck.

    Admission before commitment cancels sleep. After commitment Windows owns
    suspend; the lock is released when its API returns (normally after wake).
    The existing helper retains update and owner-cancellation protections.
    """
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(repo_root / "scripts" / "workstation-sleep.ps1"),
            "-Sleep",
            "-DelaySeconds",
            "0",
            "-ReceiptPath",
            str(data_dir / "wake-idle-helper.json"),
            "-CancelPath",
            str(data_dir / "wake-idle.cancel"),
            "-IdlePython",
            sys.executable,
            "-IdleDataDirectory",
            str(data_dir.resolve()),
            "-IdleConfigPath",
            str(config_path.resolve()),
        ],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class WakeIdle:
    """One controller per supervision loop; startup and resume get full grace."""

    def __init__(self, data_dir: Path, config_path: Path, repo_root: Path, *, clock=sleep_clock):
        self.data_dir = data_dir
        self.config_path = config_path
        self.repo_root = repo_root
        self.clock = clock
        self.last_sleep = None
        self.idle_since = None

    def check(self, now: datetime) -> list[str]:
        reasons = blockers(self.data_dir, self.config_path, now)
        if self.idle_since is None or now - self.idle_since < GRACE:
            reasons.append("grace")
        return reasons

    def tick(self, *, now=None, dry_run=False, handoff=commit_sleep, before_commit=None) -> dict:
        now = now or datetime.now(UTC)
        with interlock(self.data_dir):
            try:
                suspended = self.clock()
                if self.last_sleep is None or suspended - self.last_sleep > 1:
                    self.idle_since = now
                self.last_sleep = suspended
                reasons = self.check(now)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                reasons = [f"state_unavailable:{type(exc).__name__}"]
            if reasons:
                cancel_pending(self.data_dir)
                result = {"status": "sleep_cancelled", "blockers": reasons}
            else:
                (self.data_dir / "wake-idle.cancel").unlink(missing_ok=True)
                result = {"status": "sleep_pending", "blockers": []}
            self._receipt(result, now, dry_run)
        if reasons:
            return result
        if before_commit:
            before_commit()
        with interlock(self.data_dir):
            try:
                reasons = self.check(datetime.now(UTC) if not dry_run else now)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                reasons = [f"state_unavailable:{type(exc).__name__}"]
            if (self.data_dir / "wake-idle.cancel").exists():
                reasons.append("interlock_cancelled")
            if reasons:
                cancel_pending(self.data_dir)
                result = {"status": "sleep_cancelled", "blockers": reasons}
            elif dry_run:
                result = {"status": "sleep_dry_run", "blockers": []}
            else:
                result = {"status": "sleep_handoff", "blockers": []}
            self._receipt(result, now, dry_run)
        if result["status"] == "sleep_handoff":
            handoff(self.repo_root, self.data_dir, self.config_path)
            self.idle_since = datetime.now(UTC)
            result = {"status": "sleep_helper_returned", "blockers": []}
            with interlock(self.data_dir):
                self._receipt(result, datetime.now(UTC), False)
        return result

    def _receipt(self, result: dict, now: datetime, dry_run: bool) -> None:
        path = self.data_dir / "wake-idle.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({**result, "checked_at_utc": now.isoformat(), "dry_run": dry_run}),
            encoding="utf-8",
        )
        tmp.replace(path)


def final_check(data_dir: Path, config_path: Path) -> int:
    """Called with the shared file lock held by the PowerShell suspend caller."""
    try:
        reasons = blockers(data_dir, config_path, datetime.now(UTC))
        if (data_dir / "wake-idle.cancel").exists():
            reasons.append("interlock_cancelled")
    except (OSError, ValueError, TypeError, AttributeError):
        reasons = ["state_unavailable"]
    if reasons:
        cancel_pending(data_dir)
        return 2
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check-final", action="store_true", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(final_check(args.data_dir, args.config))
