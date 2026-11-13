"""Dashboard redeploy supervisor (scheduled-task entry, stdlib only).

Serves a supervisor-owned detached worktree tracking origin/<serve_branch>,
so the dev checkout is never touched: dirty trees and feature branches do
not block redeploys. Each tick: ensure the worktree, fast-forward it to
origin (refusing when unexpectedly dirty), restart the dashboard onto it
with shared config/data/state from the main checkout, health-check the new
commit, and clear the maintenance banner. Failures keep the banner up with
the reason and mail the owner on incident transition only (first failure
or changed reason; repeats stay silent until recovery).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MAINTENANCE_FILENAME = "maintenance.json"
PID_FILENAME = "dashboard.pid"
SERVE_VERSION_FILENAME = "serve-version.json"
MAIL_STATE_FILENAME = "supervise-mail-state.json"
HEALTH_TIMEOUT_SECONDS = 60.0
PORT_FREE_TIMEOUT_SECONDS = 15.0


@dataclass(slots=True)
class SuperviseConfig:
    """Resolved supervisor inputs (all paths absolute)."""

    main_root: Path
    worktree: Path
    data_dir: Path
    config_path: Path
    port: int
    serve_branch: str
    python_exe: str


def _same_commit(left: str, right: str) -> bool:
    """Compare full/short SHAs by prefix in either direction."""
    return left == right or left.startswith(right) or right.startswith(left)


def decide(*, running_commit: str | None, origin_commit: str | None) -> tuple[str, str]:
    """Return (action, reason); unknown origin fails closed (skip)."""
    if not origin_commit:
        return "skip-unknown", "origin commit unknown"
    if running_commit and _same_commit(running_commit, origin_commit):
        return "up-to-date", f"serving {running_commit}"
    return "redeploy", f"{running_commit or '?'} -> {origin_commit}"


def _git(workdir: Path, *args: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def read_origin_commit(main_root: Path, branch: str) -> str | None:
    """Best-effort origin branch head (None when unreachable)."""
    try:
        proc = _git(main_root, "ls-remote", "origin", branch, timeout=30.0)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    parts = proc.stdout.strip().split()
    return parts[0] if parts else None


def read_served_commit(port: int, timeout: float = 10.0) -> str | None:
    """Best-effort served commit from live /api/version (None when down)."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/version", timeout=timeout
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - any failure means not servable
        return None
    if not isinstance(payload, dict):
        return None
    commit = payload.get("commit")
    return commit if isinstance(commit, str) and commit and commit != "unknown" else None


def ensure_worktree(main_root: Path, worktree: Path, branch: str) -> tuple[bool, str]:
    """Create (detached) or verify the supervisor-owned serve worktree."""
    gitdir = worktree / ".git"
    if not gitdir.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        try:
            fetch = _git(main_root, "fetch", "origin", branch)
            if fetch.returncode != 0:
                return False, f"fetch failed: {fetch.stderr.strip()[:200]}"
            proc = _git(
                main_root,
                "worktree",
                "add",
                "--detach",
                str(worktree),
                f"origin/{branch}",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"worktree add failed: {exc}"
        if proc.returncode != 0:
            return False, f"worktree add failed: {proc.stderr.strip()[:200]}"
        return True, "worktree created"
    try:
        proc = _git(worktree, "rev-parse", "--git-common-dir")
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"worktree check failed: {exc}"
    if proc.returncode != 0:
        return False, "path is not a worktree of this repo"
    return True, "worktree verified"


def sync_worktree(worktree: Path, branch: str) -> tuple[str | None, str]:
    """Fast-forward the worktree to origin; refuse when unexpectedly dirty."""
    try:
        status = _git(worktree, "status", "--porcelain")
        if status.returncode != 0:
            return None, "worktree status failed"
        if status.stdout.strip():
            return None, "serve worktree dirty (unexpected local state); refusing to reset"
        fetch = _git(worktree, "fetch", "origin", branch)
        if fetch.returncode != 0:
            return None, f"fetch failed: {fetch.stderr.strip()[:200]}"
        reset = _git(worktree, "reset", "--hard", f"origin/{branch}")
        if reset.returncode != 0:
            return None, f"reset failed: {reset.stderr.strip()[:200]}"
        rev = _git(worktree, "rev-parse", "HEAD")
        if rev.returncode != 0:
            return None, "rev-parse failed after reset"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git error: {exc}"
    return rev.stdout.strip(), "synced"


def target_supports_worktree(main_root: Path, commit: str) -> bool:
    """True when the target tree has the --repo-root serving flag."""
    try:
        proc = _git(
            main_root,
            "show",
            f"{commit}:apps/workbench_dashboard/dashboard_web_app.py",
            timeout=30.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and "--repo-root" in proc.stdout


def write_serve_version(data_dir: Path, *, branch: str, commit: str) -> None:
    """Record the synced commit for /api/version (atomic)."""
    import datetime

    path = Path(data_dir) / SERVE_VERSION_FILENAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {
                "branch": branch,
                "commit": commit,
                "updated_utc": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


def write_maintenance(data_dir: Path, *, active: bool, message: str = "") -> None:
    """Atomically raise/update/clear the dashboard maintenance banner."""
    import datetime

    payload = {
        "active": active,
        "message": message,
        "since_utc": datetime.datetime.now(datetime.UTC).isoformat() if active else None,
    }
    path = Path(data_dir) / MAINTENANCE_FILENAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def _read_pidfile(data_dir: Path) -> dict | None:
    try:
        payload = json.loads((Path(data_dir) / PID_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _port_busy(port: int) -> bool:
    probe = socket.socket()
    probe.settimeout(2.0)
    try:
        probe.connect(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def _pid_start_time(pid: int) -> float | None:
    """Process creation time (epoch seconds) or None when unknown/dead."""
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            creation = ctypes.c_ulonglong()
            dummy = ctypes.c_ulonglong()
            ok = kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(dummy),
                ctypes.byref(dummy),
                ctypes.byref(dummy),
            )
            if not ok:
                return None
            return creation.value / 10_000_000 - 11_644_473_600
        finally:
            kernel32.CloseHandle(handle)
    if sys.platform == "linux":
        try:
            return os.stat(f"/proc/{pid}").st_ctime
        except OSError:
            return None
    return None


def _pidfile_matches_process(record: dict, pid: int) -> bool:
    """True when the pidfile record plausibly identifies the live pid.

    Guards escalation against PID reuse: only a tracked server whose
    recorded start time matches may receive stronger signals.
    """
    try:
        stamped = str(record.get("started_utc"))
        expected = datetime.fromisoformat(stamped.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return False
    actual = _pid_start_time(pid)
    return actual is not None and abs(actual - expected) <= 60


def _stop_tracked_server(pid: int, port: int) -> None:
    """Stop a verified-ours server: graceful SIGINT, then forceful SIGTERM."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            os.kill(pid, sig)
        except (OSError, ProcessLookupError):
            return
        deadline = time.monotonic() + PORT_FREE_TIMEOUT_SECONDS
        while time.monotonic() < deadline and _port_busy(port):
            time.sleep(0.5)
        if not _port_busy(port):
            return


def _serve_env(worktree: Path) -> dict[str, str]:
    """Environment shadowing installed editables with worktree packages."""
    env = dict(os.environ)
    roots = sorted(str(path) for path in (worktree / "packages").glob("*/src") if path.is_dir())
    if roots:
        prior = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join([*roots, prior] if prior else roots)
    return env


def restart_dashboard(config: SuperviseConfig) -> tuple[bool, str]:
    """Restart the dashboard onto the synced worktree; (ok, detail)."""
    record = _read_pidfile(config.data_dir)
    pid = record.get("pid") if isinstance(record, dict) else None
    if (
        isinstance(record, dict)
        and isinstance(pid, int)
        and pid > 0
        and _pidfile_matches_process(record, pid)
    ):
        _stop_tracked_server(pid, config.port)
    if _port_busy(config.port):
        return False, "port still busy after stop; unknown owner, refusing to kill strangers"
    app_dir = config.worktree / "apps" / "workbench_dashboard"
    try:
        subprocess.Popen(
            [
                config.python_exe,
                "dashboard_web_app.py",
                "--host",
                "127.0.0.1",
                "--port",
                str(config.port),
                "--config",
                str(config.config_path),
                "--data-dir",
                str(config.data_dir),
                "--repo-root",
                str(config.main_root),
            ],
            cwd=app_dir,
            env=_serve_env(config.worktree),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return False, f"respawn failed: {exc}"
    return True, "respawned"


def wait_healthy(config: SuperviseConfig, want_commit: str) -> bool:
    """Wait until /api/version serves want_commit (prefix match allowed)."""
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        served = read_served_commit(config.port)
        if served and (
            served == want_commit
            or want_commit.startswith(served)
            or served.startswith(want_commit)
        ):
            return True
        time.sleep(2.0)
    return False


def _mail_state_path(data_dir: Path) -> Path:
    return Path(data_dir) / MAIL_STATE_FILENAME


def _read_last_mailed_key(data_dir: Path) -> str | None:
    """Last-mailed incident key, or None when never mailed/unreadable."""
    try:
        payload = json.loads(_mail_state_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    key = payload.get("key")
    return key if isinstance(key, str) and key else None


def _write_last_mailed_key(data_dir: Path, key: str) -> None:
    """Record the mailed incident key (atomic, best-effort)."""
    import datetime

    try:
        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        path = _mail_state_path(data_dir)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {
                    "key": key,
                    "mailed_utc": datetime.datetime.now(datetime.UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError:
        pass


def _clear_last_mailed_key(data_dir: Path) -> None:
    """Forget the mailed incident after recovery (no-op when no state)."""
    try:
        _mail_state_path(data_dir).unlink(missing_ok=True)
    except OSError:
        pass


def _maybe_mail_failure(config: SuperviseConfig, reason: str) -> bool:
    """Mail on incident transition only; True when a send was attempted.

    Repeated identical failures (same incident key) do not re-mail; a
    changed reason or a failure after recovery mails again.
    """
    key = f"failed:{reason}"
    if _read_last_mailed_key(config.data_dir) == key:
        return False
    _mail_failure(config, reason)
    _write_last_mailed_key(config.data_dir, key)
    return True


def _mail_failure(config: SuperviseConfig, reason: str) -> None:
    try:
        from owner_mail import load_smtp_config, send_owner_mail

        mail_config = load_smtp_config(root=config.main_root)
        send_owner_mail(
            to=mail_config["owner"],
            subject="Dashboard redeploy failed",
            body=f"Supervised redeploy to origin/{config.serve_branch} failed: {reason}\nThe maintenance banner stays up; the dashboard keeps serving its previous commit.",
            config=mail_config,
            dry_run=False,
            receipts_dir=config.data_dir / "mail-receipts",
        )
    except Exception:  # noqa: BLE001 - mail is best-effort; banner is the record
        pass


def supervise_tick(config: SuperviseConfig, *, dry_run: bool = False, force: bool = False) -> dict:
    """One supervisor pass; returns a JSON-able outcome (never raises)."""
    outcome: dict = {"action": "error", "reason": "", "dry_run": dry_run}
    try:
        origin = read_origin_commit(config.main_root, config.serve_branch)
        running = read_served_commit(config.port)
        action, reason = decide(running_commit=running, origin_commit=origin)
        if force and action == "up-to-date":
            action, reason = "redeploy", "forced redeploy"
        outcome.update(action=action, reason=reason, running=running, origin=origin)
        if action != "redeploy":
            if action == "up-to-date" and not dry_run:
                _clear_last_mailed_key(config.data_dir)
            return outcome
        if dry_run:
            return outcome
        assert origin is not None
        if not target_supports_worktree(config.main_root, origin):
            detail = "target predates worktree serving (--repo-root); held"
            write_maintenance(config.data_dir, active=True, message=f"Update held: {detail}")
            outcome.update(action="held", reason=detail)
            return outcome
        write_maintenance(
            config.data_dir,
            active=True,
            message=f"Updating to {origin[:12]} — restarts in seconds.",
        )
        ok, detail = ensure_worktree(config.main_root, config.worktree, config.serve_branch)
        if not ok:
            write_maintenance(config.data_dir, active=True, message=f"Update held: {detail}")
            outcome.update(action="held", reason=detail)
            return outcome
        commit, detail = sync_worktree(config.worktree, config.serve_branch)
        if commit is None:
            write_maintenance(config.data_dir, active=True, message=f"Update held: {detail}")
            outcome.update(action="held", reason=detail)
            return outcome
        write_serve_version(config.data_dir, branch=config.serve_branch, commit=commit[:12])
        ok, detail = restart_dashboard(config)
        if not ok:
            write_maintenance(config.data_dir, active=True, message=f"Restart failed: {detail}")
            _maybe_mail_failure(config, detail)
            outcome.update(action="failed", reason=detail)
            return outcome
        if not wait_healthy(config, commit):
            write_maintenance(
                config.data_dir, active=True, message="New dashboard failed its health check."
            )
            _maybe_mail_failure(config, "health check timeout")
            outcome.update(action="failed", reason="health check timeout")
            return outcome
        write_maintenance(config.data_dir, active=False)
        _clear_last_mailed_key(config.data_dir)
        outcome.update(action="redeployed", reason=f"now serving {commit[:12]}")
        return outcome
    except Exception as exc:  # noqa: BLE001 - supervisor ticks never raise
        outcome.update(action="error", reason=f"{type(exc).__name__}: {exc}"[:300])
        return outcome


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dashboard redeploy supervisor (one tick).")
    parser.add_argument("--main-root", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--serve-branch", default="develop")
    parser.add_argument("--python-exe", default=sys.executable)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="Redeploy even when up to date (testing)."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one tick; print the JSON outcome; exit 0 unless redeploy failed."""
    args = build_parser().parse_args(argv)
    main_root = args.main_root.resolve()
    worktree = args.worktree or (main_root.parent / "ai-workbench-serve")
    data_dir = args.data_dir or (main_root / "apps" / "workbench_dashboard" / "data")
    config = SuperviseConfig(
        main_root=main_root,
        worktree=worktree,
        data_dir=data_dir,
        config_path=args.config or (main_root / "apps" / "workbench_dashboard" / "dashboard.json"),
        port=args.port,
        serve_branch=args.serve_branch,
        python_exe=args.python_exe,
    )
    outcome = supervise_tick(config, dry_run=args.dry_run, force=args.force)
    print(json.dumps(outcome))
    if args.dry_run:
        return 0
    return 0 if outcome["action"] in {"up-to-date", "redeployed", "skip-unknown", "held"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
