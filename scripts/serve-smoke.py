"""Spot-check the served dashboard: reachability, key shapes, serve drift.

Read-only and fast: plain HTTP GETs plus one ls-remote. Exit 0 when every
check passes, 1 otherwise. Agent mode being off is reported as info, not
failure (disabling it is a legitimate owner choice).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

APPROVALS = ("scoped", "ask-always", "yolo")


def _get(url: str, timeout: float = 15.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_status(base_url: str) -> tuple[bool, str]:
    try:
        payload = _get(f"{base_url}/api/status")
    except Exception as exc:
        return False, f"status unreachable: {exc}"
    if payload.get("ok") is True:
        return True, "status ok"
    return False, f"status not ok: {payload!r}"[:160]


def check_agent_config(base_url: str) -> tuple[bool, str]:
    try:
        payload = _get(f"{base_url}/api/chat/agent-config")
    except Exception as exc:
        return False, f"agent-config unreachable: {exc}"
    enabled = payload.get("enabled")
    approval = payload.get("approval")
    if not isinstance(enabled, bool):
        return False, f"agent-config enabled not a bool: {enabled!r}"
    if approval not in APPROVALS:
        return False, f"agent-config approval invalid: {approval!r}"
    state = "on" if enabled else "off"
    return True, f"agent mode {state} (policy {approval})"


def check_e2e_open(base_url: str) -> tuple[bool, str]:
    try:
        payload = _get(f"{base_url}/api/e2e/tasks?status=open")
    except Exception as exc:
        return False, f"e2e tasks unreachable: {exc}"
    items = payload.get("items")
    if payload.get("ok") is not True or not isinstance(items, list):
        return False, f"e2e open shape invalid: {payload!r}"[:160]
    return True, f"e2e open lists {len(items)} task(s)"


def _origin_head(repo_root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "ls-remote", "origin", "develop"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    return completed.stdout.split()[0]


def check_serve_drift(repo_root: Path) -> tuple[bool, str]:
    version_file = repo_root / "apps" / "workbench_dashboard" / "data" / "serve-version.json"
    try:
        served = str(json.loads(version_file.read_text(encoding="utf-8")).get("commit", "") or "")
    except (OSError, ValueError):
        return True, "serve version unknown (no local marker); skipped"
    origin = _origin_head(repo_root)
    if origin is None:
        return True, "origin unreachable; drift unknown"
    if served == origin or origin.startswith(served) or served.startswith(origin):
        return True, f"serve matches origin ({served[:12]})"
    return False, f"serve {served[:12]} lags origin {origin[:12]}"


def run_all(base_url: str, repo_root: Path) -> list[tuple[str, bool, str]]:
    drift_ok, drift_msg = check_serve_drift(repo_root)
    return [
        ("status",) + check_status(base_url),
        ("agent-config",) + check_agent_config(base_url),
        ("e2e-open",) + check_e2e_open(base_url),
        ("serve-drift", drift_ok, drift_msg),
    ]


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    parser.add_argument("--repo", type=Path, default=here.parent)
    args = parser.parse_args(argv)
    failed = False
    for name, ok, message in run_all(args.url.rstrip("/"), args.repo):
        print(f"{'OK  ' if ok else 'FAIL'} {name}: {message}")
        failed = failed or not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
