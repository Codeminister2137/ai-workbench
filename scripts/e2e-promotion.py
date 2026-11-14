#!/usr/bin/env python3
"""E2E promotion workflow: generate checklists, gate merges, promote to master.

Implements the ADR-087 use-based promotion gate:

* ``generate`` builds a per-behavior checklist from a merge diff plus the
  touched goal docs, applies ancestor matching (no-diff proof +
  warnings), and files one E2E task. Fully auto-passed tasks submit
  themselves; anything pending waits for the owner in the dashboard.
* ``gate`` reports whether one merge may promote (its own passing
  report exists).
* ``promote`` merges ``develop`` to ``master`` only when every merge in
  the span has a passing own or covering range report. A failed E2E
  blocks only its own merge's promotion.

Usage:
    python scripts/e2e-promotion.py generate abc123
    python scripts/e2e-promotion.py generate develop --base master
    python scripts/e2e-promotion.py gate abc123
    python scripts/e2e-promotion.py promote
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[1]
DASHBOARD_DIR = REPO_ROOT / "apps" / "workbench_dashboard"
DEFAULT_DATA_DIR = DASHBOARD_DIR / "data"
DEFAULT_URL = "http://127.0.0.1:8766"

sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(HERE.parent))

from e2e_promotion import (  # noqa: E402
    apply_ancestor_matching,
    generate_checklist,
    merge_diff_files,
    merges_between,
    promotion_verdict,
    run_git,
    uncovered_merges,
)


def load_reports(data_dir: Path) -> list[dict]:
    """Read stored E2E reports; skips unreadable files."""
    reports: list[dict] = []
    reports_dir = data_dir / "e2e_reports"
    if not reports_dir.is_dir():
        return reports
    for path in sorted(reports_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            continue
        if isinstance(payload, dict):
            reports.append(payload)
    return reports


def file_task(url: str, payload: dict, token: str | None, data_dir: Path) -> dict:
    """File the task via the dashboard API, else write the store directly."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/e2e/tasks",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        request.add_header("X-Supervisor-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        from dashboard_stores import DashboardStores

        record = DashboardStores(data_dir).create_e2e_task(
            merge_commit=str(payload["merge_commit"]),
            title=str(payload["title"]),
            items=list(payload["items"]),
            range_base=payload.get("range_base"),
        )
        return {"ok": True, "id": record["id"], "direct": True}


def submit_task(url: str, task_id: str, data_dir: Path) -> dict:
    """Submit (possibly empty) results; direct store fallback included."""
    body = json.dumps({"results": []}).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/e2e/tasks/{task_id}/submit",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError:
        from dashboard_stores import DashboardStores

        outcome = DashboardStores(data_dir).submit_e2e_task(task_id, [])
        return {
            "ok": True,
            "report_id": outcome["report"]["id"],
            "overall": outcome["report"]["overall"],
            "direct": True,
        }


def resolve_base(repo: str, merge: str, base: str | None) -> str:
    """Default base is the merge's first parent (the merge's own diff)."""
    if base:
        return base
    return run_git(repo, "rev-parse", f"{merge}^1").decode("utf-8").strip()


def cmd_generate(args: argparse.Namespace) -> int:
    repo = str(REPO_ROOT)
    data_dir = Path(args.data_dir)
    try:
        base = resolve_base(repo, args.merge, args.base)
        files = merge_diff_files(repo, base, args.merge)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    checklist = generate_checklist(args.merge, files, title=args.title)
    if args.base:
        checklist["range_base"] = base
    reports = load_reports(data_dir)
    try:
        matched = apply_ancestor_matching(checklist, reports, repo)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    if args.dry_run:
        print(json.dumps(matched, indent=2))
        return 0
    payload = {
        "merge_commit": args.merge,
        "title": matched["title"],
        "items": matched["items"],
    }
    if args.base:
        payload["range_base"] = base
    try:
        filed = file_task(args.url, payload, args.token, data_dir)
    except Exception as exc:  # noqa: BLE001 - store refusal or HTTP error body
        print(f"error: could not file E2E task: {exc}")
        return 1
    if not filed.get("ok", True):
        print(f"error: {filed.get('error', 'unknown filing failure')}")
        return 1
    pending = sum(1 for item in matched["items"] if item.get("status") == "pending")
    task_id = filed["id"]
    print(f"task: {task_id} pending={pending} items={len(matched['items'])}")
    if pending == 0:
        submitted = submit_task(args.url, task_id, data_dir)
        print(f"report: {submitted.get('report_id')} overall={submitted.get('overall')}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    reports = load_reports(Path(args.data_dir))
    verdict = promotion_verdict(args.merge, reports)
    print(verdict.reason)
    return 0 if verdict.allowed else 1


def cmd_promote(args: argparse.Namespace) -> int:
    from auto_merge import TARGET as DEVELOP
    from auto_merge import push_with_retries

    repo = str(REPO_ROOT)
    target = args.target
    try:
        merges = merges_between(repo, target, DEVELOP)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    if not merges:
        print(f"nothing to promote: {target} already contains {DEVELOP}")
        return 0
    reports = load_reports(Path(args.data_dir))
    try:
        missing = uncovered_merges(merges, reports, repo)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    if missing:
        print(f"refused: {len(missing)} merge(s) lack a passing E2E report:")
        for commit in missing[:20]:
            print(f"  {commit}")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
        return 3
    try:
        run_git(repo, "switch", target)
        run_git(repo, "merge", "--no-ff", DEVELOP, "-m", f"Promote {DEVELOP} (E2E passed)")
        remote = push_with_retries(target)
    except RuntimeError as exc:
        print(f"FAILED: {exc}")
        return 5
    head = run_git(repo, "rev-parse", "--short", target).decode("utf-8").strip()
    print(f"promoted: {DEVELOP} -> {target}@{head}")
    print(f"remote: {remote}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="E2E promotion workflow (ADR-087).")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Build a checklist and file one E2E task.")
    gen.add_argument("merge", help="Merge commit (or tip) to promote.")
    gen.add_argument("--base", default=None, help="Range base (default: first parent).")
    gen.add_argument("--title", default=None)
    gen.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    gen.add_argument("--url", default=DEFAULT_URL)
    gen.add_argument("--token", default=None)
    gen.add_argument("--dry-run", action="store_true")
    gen.set_defaults(func=cmd_generate)
    gate = sub.add_parser("gate", help="Check one merge's promotion verdict.")
    gate.add_argument("merge")
    gate.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    gate.set_defaults(func=cmd_gate)
    promo = sub.add_parser("promote", help="Merge develop to master when E2E-green.")
    promo.add_argument("--target", default="master")
    promo.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    promo.set_defaults(func=cmd_promote)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
