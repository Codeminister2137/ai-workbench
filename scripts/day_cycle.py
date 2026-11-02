"""Day-cycle helper: safe end-of-day closeout and next-day startup.

``close`` snapshots git state plus the exact command lines of running
services, and reports whether the tree is safe to power off. ``open``
replays the snapshot: it checks every expected service and starts the
missing ones, then reports what runs and what still needs a human.

Snapshots live under ``artifacts/day-cycle/`` (gitignored, local only).
Service command lines may contain hostnames; they never leave the disk.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_provider.secrets import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATOR_ROOT = REPO_ROOT.parent / "remote-ai-operator"
SNAPSHOT_DIR = REPO_ROOT / "artifacts" / "day-cycle"

OPERATOR_PORT = 8765
DASHBOARD_PORT = 8766
OLLAMA_PORT = 11434


@dataclass(frozen=True, slots=True)
class GitState:
    """Porcelain git state for one checkout; no network involved."""

    root: str
    branch: str
    clean: bool
    ahead: int
    behind: int
    head: str
    untracked: tuple[str, ...] = ()


def run_command(argv: list[str], *, cwd: Path | None = None, timeout: int = 60) -> tuple[int, str]:
    """Run one command; return (exit code, combined tail output)."""
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"runner error: {exc}"
    return completed.returncode, (completed.stdout + completed.stderr)[-2000:]


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check one TCP port without sending application bytes."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def git_state(root: Path) -> GitState:
    """Collect branch, cleanliness, and ahead/behind for one checkout."""
    code, branch = run_command(["git", "branch", "--show-current"], cwd=root)
    code_s, status = run_command(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root)
    _code_u, untracked_raw = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root
    )
    code_h, head = run_command(["git", "rev-parse", "--short", "HEAD"], cwd=root)
    code_a, ahead = run_command(["git", "rev-list", "--count", "@{upstream}..HEAD"], cwd=root)
    code_b, behind = run_command(["git", "rev-list", "--count", "HEAD..@{upstream}"], cwd=root)
    if code or code_s or code_h:
        return GitState(str(root), "?", False, 0, 0, "?")
    try:
        ahead_n = int(without_warnings(ahead).strip().split()[0]) if not code_a else 0
        behind_n = int(without_warnings(behind).strip().split()[0]) if not code_b else 0
    except (ValueError, IndexError):
        ahead_n, behind_n = 0, 0
    cleaned = without_warnings(untracked_raw)
    untracked = tuple(sorted(line for line in cleaned.splitlines() if line.strip()))
    return GitState(
        root=str(root),
        branch=without_warnings(branch).strip(),
        clean=not without_warnings(status).strip(),
        ahead=ahead_n,
        behind=behind_n,
        head=without_warnings(head).strip(),
        untracked=untracked,
    )


def close_verdict(states: list[GitState]) -> tuple[bool, list[str]]:
    """Decide whether power-off is safe; blockers are explicit strings."""
    blockers: list[str] = []
    for state in states:
        label = Path(state.root).name
        if state.head == "?":
            blockers.append(f"{label}: git state unreadable")
            continue
        if not state.clean:
            blockers.append(f"{label}: uncommitted tracked changes on {state.branch}")
        if state.ahead:
            blockers.append(f"{label}: {state.ahead} unpushed commit(s) on {state.branch}")
        if state.behind:
            blockers.append(f"{label}: {state.behind} commit(s) behind origin (fetch first)")
    return (not blockers, blockers)


def service_command_lines() -> dict[str, str]:
    """Map listener ports to owning python command lines (Windows)."""
    code, conns = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-NetTCPConnection -State Listen | Select-Object LocalPort,OwningProcess",
        ],
        timeout=30,
    )
    if code:
        return {}
    port_pids: dict[str, str] = {}
    for line in conns.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            port_pids[parts[0]] = parts[1]
    found: dict[str, str] = {}
    for port in (str(OPERATOR_PORT), str(DASHBOARD_PORT), str(OLLAMA_PORT)):
        pid = port_pids.get(port)
        if not pid:
            continue
        code_p, info = run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
            ],
            timeout=30,
        )
        if not code_p and info.strip():
            found[port] = " ".join(info.split())
    return found


def docker_state() -> dict[str, object]:
    """Check the Docker daemon without starting anything."""
    code, output = run_command(["docker", "version", "--format", "{{.Server.Version}}"], timeout=30)
    return {"available": code == 0, "server_version": output.strip() if code == 0 else None}


def without_warnings(text: str) -> str:
    """Drop stderr `warning: ` lines from combined command output."""
    kept = [line for line in text.splitlines(keepends=True) if not line.startswith("warning: ")]
    return "".join(kept)


def docker_desktop_candidates() -> list[Path]:
    """Well-known Docker Desktop install paths (Windows)."""
    roots: list[Path] = []
    for env in ("ProgramFiles", "ProgramW6432"):
        value = os.environ.get(env)
        if value:
            roots.append(Path(value))
    if not roots:
        roots.append(Path("C:/Program Files"))
    return [root / "Docker" / "Docker" / "Docker Desktop.exe" for root in roots]


def parse_process_count(output: str) -> int:
    """Parse the @(Get-Process ...).Count output; 0 when unreadable."""
    try:
        return max(0, int(output.strip().split()[0]))
    except (ValueError, IndexError):
        return 0


def docker_desktop_running() -> bool:
    """Check whether Docker Desktop runs (without starting anything)."""
    code, output = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "@(Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue).Count",
        ],
        timeout=30,
    )
    return code == 0 and parse_process_count(output) > 0


def ensure_docker(
    *,
    wait_seconds: float = 180,
    poll_seconds: float = 5,
    state_fn: Callable[[], dict[str, object]] = docker_state,
    running_fn: Callable[[], bool] = docker_desktop_running,
    launch_fn: Callable[[Path], bool] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    candidates_fn: Callable[[], list[Path]] = docker_desktop_candidates,
) -> tuple[bool, str]:
    """Start Docker Desktop when the daemon is down; report the outcome."""
    if state_fn()["available"]:
        return True, "docker: daemon up"
    if not running_fn():
        exe = next((path for path in candidates_fn() if path.exists()), None)
        if exe is None:
            return (
                False,
                "docker: daemon down, Desktop not found at known paths "
                "(start Docker Desktop manually)",
            )
        if launch_fn is None:
            started = start_detached("docker-desktop", [str(exe)], REPO_ROOT)
        else:
            started = launch_fn(exe)
        if not started:
            return (
                False,
                "docker: daemon down, Desktop launch FAILED (start Docker Desktop manually)",
            )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        sleep_fn(poll_seconds)
        if state_fn()["available"]:
            return True, "docker: daemon up (Desktop started it)"
    return (
        False,
        f"docker: daemon still down after {wait_seconds:.0f}s (start Docker Desktop manually)",
    )


def write_snapshot(payload: dict) -> Path:
    """Write one timestamped close snapshot; return its path."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = SNAPSHOT_DIR / f"close-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def latest_snapshot() -> dict | None:
    """Read the newest close snapshot, or None when absent/unreadable."""
    try:
        files = sorted(SNAPSHOT_DIR.glob("close-*.json"))
    except OSError:
        return None
    if not files:
        return None
    try:
        payload = json.loads(files[-1].read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def command_close() -> int:
    """Snapshot the evening state and print the power-off verdict."""
    states = [git_state(REPO_ROOT)]
    states.append(
        git_state(OPERATOR_ROOT)
        if OPERATOR_ROOT.exists()
        else GitState(str(OPERATOR_ROOT), "?", False, 0, 0, "?")
    )
    listeners = service_command_lines()
    payload = {
        "closed_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "git": [dataclasses.asdict(state) for state in states],
        "listeners": listeners,
        "docker": docker_state(),
    }
    path = write_snapshot(payload)
    ok, blockers = close_verdict(states)
    print(f"snapshot: {path}")
    for state in states:
        print(
            f"{Path(state.root).name}: {state.branch}@{state.head} "
            f"clean={state.clean} ahead={state.ahead} behind={state.behind}"
        )
    print(f"listeners: {sorted(listeners)} docker={payload['docker']['available']}")
    for state in states:
        if state.untracked:
            shown = ", ".join(state.untracked[:8])
            more = f" (+{len(state.untracked) - 8} more)" if len(state.untracked) > 8 else ""
            print(
                f"untracked (left in place, not blocking): {Path(state.root).name}: {shown}{more}"
            )
    if ok:
        print("READY FOR POWER OFF: trees clean and pushed.")
        return 0
    print("NOT READY FOR POWER OFF:")
    for blocker in blockers:
        print(f"  - {blocker}")
    return 1


SERVICE_ENV_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "operator-serve": ("OPERATOR_ACCESS_TOKEN",),
}
"""Secret-store names each replayed service may receive (values never logged)."""


def service_env(label: str, *, store: Path | None = None) -> dict[str, str]:
    """Allowlisted secret-store values for one replayed service."""
    load_dotenv(store)
    return {
        name: os.environ[name]
        for name in SERVICE_ENV_ALLOWLIST.get(label, ())
        if os.environ.get(name)
    }


def start_detached(
    label: str, argv: list[str] | str, cwd: Path, env: dict[str, str] | None = None
) -> bool:
    """Start one service detached with logs; never raises."""
    logs = SNAPSHOT_DIR / "service-logs"
    try:
        logs.mkdir(parents=True, exist_ok=True)
        out = (logs / f"{label}.out.log").open("ab")
        err = (logs / f"{label}.err.log").open("ab")
    except OSError:
        return False
    try:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=out,
            stderr=err,
            stdin=subprocess.DEVNULL,
            env={**os.environ, **(env or {})},
            creationflags=creation,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


def command_open() -> int:
    """Check every expected service and start the missing ones."""
    snapshot = latest_snapshot()
    stored = (snapshot or {}).get("listeners", {})
    if not isinstance(stored, dict):
        stored = {}
    report: list[str] = []
    failed = False

    checks = [
        ("operator-serve", OPERATOR_PORT, OPERATOR_ROOT),
        ("dashboard", DASHBOARD_PORT, REPO_ROOT / "apps" / "workbench_dashboard"),
        ("ollama", OLLAMA_PORT, REPO_ROOT),
    ]
    for label, port, cwd in checks:
        if port_open("127.0.0.1", port):
            report.append(f"{label}: already listening on {port}")
            continue
        env: dict[str, str] = {}
        if label == "ollama":
            ok = start_detached(label, ["ollama", "serve"], REPO_ROOT)
        else:
            cmdline = stored.get(str(port), "")
            if not cmdline:
                report.append(f"{label}: missing and no snapshot command to replay")
                failed = True
                continue
            env = service_env(label)
            ok = start_detached(label, cmdline, cwd, env=env)
        secret = ""
        if label in SERVICE_ENV_ALLOWLIST:
            secret = " (token from secret store)" if env else " (NO TOKEN in secret store)"
        report.append(f"{label}: {'start requested' if ok else 'START FAILED'} on {port}{secret}")
        failed = failed or not ok
    _docker_ok, docker_line = ensure_docker()
    report.append(docker_line)
    time.sleep(3)
    for label, port, _cwd in checks:
        report.append(
            f"{label}: listening" if port_open("127.0.0.1", port) else f"{label}: NOT listening"
        )
        if not port_open("127.0.0.1", port):
            failed = True
    code, _output = run_command(
        [sys.executable, "-c", "import ai_provider, ai_agent, ai_orchestrator"],
        cwd=REPO_ROOT,
        timeout=60,
    )
    report.append("workspace imports: ok" if code == 0 else "workspace imports: FAILED")
    failed = failed or code != 0
    for line in report:
        print(line)
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    """CLI with close/open subcommands."""
    parser = argparse.ArgumentParser(description="End-of-day closeout and next-day startup.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("close", help="Snapshot state and print the power-off verdict.")
    sub.add_parser("open", help="Check services and start the missing ones.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch close/open; return the process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "close":
        return command_close()
    return command_open()


if __name__ == "__main__":
    raise SystemExit(main())
