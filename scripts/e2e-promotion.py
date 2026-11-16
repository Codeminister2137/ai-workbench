#!/usr/bin/env python3
"""E2E promotion workflow: generate checklists, gate merges, promote to master.

Implements the ADR-087 use-based promotion gate:

* ``generate`` builds a per-behavior checklist from a merge diff plus the
  touched goal docs, applies ancestor matching (no-diff proof +
  warnings), and files one E2E task. Fully auto-passed tasks submit
  themselves; anything pending waits for the owner in the dashboard.
  Items whose steps cannot ground in diff evidence file the task as a
  draft plus one pointer clarification instead of a vague checklist.
* ``finalize`` opens a draft with authored steps after pointers land.
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

from e2e_cases import extract_diff_evidence  # noqa: E402
from e2e_promotion import (  # noqa: E402
    apply_ancestor_matching,
    change_summary,
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
            draft=bool(payload.get("draft", False)),
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


def pointer_body(merge: str, unclear: list[dict]) -> str:
    """Owner-readable pointer request for behaviors the generator could not ground."""
    lines = [
        f"The E2E generator could not determine concrete checks for {merge}.",
        "Reply with what to verify for each behavior (what to click, what to expect);",
        "the draft checklist finalizes once pointers land. Evidence the generator saw:",
        "",
    ]
    for item in unclear:
        lines.append(f"- {item.get('behavior')} ({item.get('id')})")
        for subject in item.get("what", [])[:4]:
            lines.append(f"  what: {subject}")
        for path in item.get("files", [])[:8]:
            lines.append(f"  file: {path}")
    return "\n".join(lines)


def file_pointers(
    url: str, token: str | None, data_dir: Path, merge: str, unclear: list[dict]
) -> str:
    """File one clarification asking the owner how to test unclear behaviors."""
    payload = {
        "title": f"E2E pointers needed: {merge}",
        "body": pointer_body(merge, unclear),
        "type": "clarification",
        "created_by": "supervisor",
        "assignee": "owner",
        "metadata": {"merge_commit": merge, "kind": "e2e-pointers"},
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/inbox",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        request.add_header("X-Supervisor-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return str(json.loads(response.read().decode("utf-8"))["id"])
    except OSError:
        from dashboard_stores import DashboardStores

        record = DashboardStores(data_dir).create_inbox_task(
            title=str(payload["title"]),
            body=str(payload["body"]),
            task_type="clarification",
            created_by="supervisor",
            assignee="owner",
            metadata=dict(payload["metadata"]),
        )
        return str(record["id"])


def cmd_generate(args: argparse.Namespace) -> int:
    repo = str(REPO_ROOT)
    data_dir = Path(args.data_dir)
    try:
        base = resolve_base(repo, args.merge, args.base)
        files = merge_diff_files(repo, base, args.merge)
        summaries = change_summary(repo, base, args.merge, files)
        summaries["evidence"] = extract_diff_evidence(repo, base, args.merge, files)
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 2
    checklist = generate_checklist(args.merge, files, title=args.title, summaries=summaries)
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
    unclear = [
        item
        for item in matched["items"]
        if item.get("status") == "pending" and item.get("needs_pointers")
    ]
    payload = {
        "merge_commit": args.merge,
        "title": matched["title"],
        "items": matched["items"],
        "draft": bool(unclear),
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
    if unclear:
        try:
            inbox_id = file_pointers(args.url, args.token, data_dir, args.merge, unclear)
        except Exception as exc:  # noqa: BLE001 - pointer filing must not lose the draft
            print(f"error: could not file pointer request: {exc}")
            return 1
        print(f"pointers: {inbox_id} unclear={len(unclear)} (task stays draft)")
        return 0
    if pending == 0:
        submitted = submit_task(args.url, task_id, data_dir)
        print(f"report: {submitted.get('report_id')} overall={submitted.get('overall')}")
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    """Finalize a draft with authored steps after pointers land."""
    try:
        steps = json.loads(Path(args.steps_json).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"error: cannot read steps file: {exc}")
        return 2
    if not isinstance(steps, dict):
        print("error: steps file must map item ids to step lists")
        return 2
    body = json.dumps({"steps": steps}).encode("utf-8")
    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/api/e2e/tasks/{args.task_id}/finalize",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if args.token:
        request.add_header("X-Supervisor-Token", args.token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            outcome = json.loads(response.read().decode("utf-8"))
    except OSError:
        from dashboard_stores import DashboardStores

        try:
            record = DashboardStores(Path(args.data_dir)).finalize_e2e_task(args.task_id, steps)
        except Exception as exc:  # noqa: BLE001 - store refusal surfaces as error
            print(f"error: could not finalize: {exc}")
            return 1
        print(f"finalized: {record['id']} status={record['status']} (direct)")
        return 0
    if not outcome.get("ok", True):
        print(f"error: {outcome.get('error', 'unknown finalize failure')}")
        return 1
    print(f"finalized: {outcome['id']} status={outcome['status']}")
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
    fin = sub.add_parser("finalize", help="Open a draft with authored steps.")
    fin.add_argument("task_id", help="Draft E2E task id.")
    fin.add_argument("steps_json", help="JSON file mapping item ids to step lists.")
    fin.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    fin.add_argument("--url", default=DEFAULT_URL)
    fin.add_argument("--token", default=None)
    fin.set_defaults(func=cmd_finalize)
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
