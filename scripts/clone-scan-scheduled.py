"""Weekly clone-scan: brief the owner only when NEW duplication appears.

Runs scripts/find-duplication.py over the repo, diffs group signatures
against a JSON baseline, and files one dashboard inbox brief per run when
(and only when) previously unseen groups appear. First run establishes the
baseline silently. Baseline updates only after a successful brief filing
(or when nothing is new), so a failed run retries next time.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("find_duplication", HERE / "find-duplication.py")
assert SPEC is not None and SPEC.loader is not None
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)

SCAN_ROOTS = ("packages", "apps", "scripts")
MIN_NODES = 30
MIN_LINES = 8


def group_keys(groups: list[list[dict]]) -> dict[str, list[str]]:
    """Map each clone group to a stable key with sorted member labels."""
    keyed: dict[str, list[str]] = {}
    for group in groups:
        head = group[0]
        key = f"{head['key']}:{head['nodes']}"
        keyed[key] = sorted(f"{item['path']}:{item['lineno']}: {item['name']}" for item in group)
    return keyed


def find_new(current: dict[str, list[str]], baseline: dict[str, object]) -> dict[str, list[str]]:
    """Return current groups whose keys are absent from the baseline."""
    known = set(baseline.get("groups", {}))
    return {key: members for key, members in current.items() if key not in known}


def build_brief_body(new: dict[str, list[str]], total: int) -> str:
    """Render the owner brief listing each new group with members."""
    lines = [
        f"Weekly clone scan found {len(new)} new group(s) ({total} total).",
        "Triage each: centralize (shared core + variance) or leave intentionally.",
        "",
    ]
    for key, members in sorted(new.items()):
        lines.append(f"--- key={key} ({len(members)} members)")
        lines.extend(f"- {member}" for member in members)
    return "\n".join(lines)


def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def file_brief(dashboard: str, title: str, body: str) -> None:
    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "type": "decision",
            "options": ["Approve centralization", "Leave"],
        }
    ).encode()
    request = urllib.request.Request(
        f"{dashboard.rstrip('/')}/api/inbox",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError(f"Inbox brief rejected: {result!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=HERE.parent)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--dashboard", default="http://127.0.0.1:8766")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    baseline_path = args.baseline or (args.repo_root / "artifacts/clone-scan/baseline.json")
    roots = [args.repo_root / name for name in SCAN_ROOTS if (args.repo_root / name).exists()]
    records = []
    for path in scanner.iter_python_files(roots):
        records.extend(scanner.scan_file(path))
    groups = scanner.find_groups(records, min_nodes=MIN_NODES, min_lines=MIN_LINES)
    current = group_keys(groups)

    stamp = datetime.now(UTC).isoformat()
    baseline = load_baseline(baseline_path)
    if not baseline:
        print(f"first run: establishing baseline with {len(current)} groups")
        if not args.dry_run:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(
                json.dumps(
                    {
                        "groups": {
                            key: {"members": members, "first_seen_utc": stamp}
                            for key, members in current.items()
                        },
                        "updated_utc": stamp,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return 0

    new = find_new(current, baseline)
    print(f"scanned {len(records)} functions, {len(current)} groups, {len(new)} new")
    if not new:
        return 0
    body = build_brief_body(new, len(current))
    if args.dry_run:
        print("dry-run: would file brief:")
        print(body)
        return 0
    try:
        file_brief(args.dashboard, f"Clone scan: {len(new)} new group(s)", body)
    except Exception as exc:  # noqa: BLE001 - scheduled run must report, not crash silently
        print(f"dashboard unreachable, baseline kept for retry: {exc}", file=sys.stderr)
        return 1
    stored = baseline.get("groups", {})
    for key, members in new.items():
        stored[key] = {"members": members, "first_seen_utc": stamp}
    baseline["groups"] = stored
    baseline["updated_utc"] = stamp
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    log_path = baseline_path.parent / "runs.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} functions={len(records)} groups={len(current)} new={len(new)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
