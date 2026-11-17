"""Per-behavior E2E promotion checklists (ADR-087).

Tier 2 merges reach ``master`` only through a passed E2E checklist. Each
promotion generates checklist items from the merge diff plus the touched
goal docs. An item auto-passes only by linking a prior passing E2E
report for the same behavior on an ancestor commit, with an attached
no-diff proof for that behavior's files — and every such approval is
visibly marked with a warning, never silently green. Unmatched items
become one owner E2E task; submitting it auto-builds the report. A
failed E2E blocks only its own merge's promotion.

Docs/tests/tooling-only areas carry no user-visible behavior, so their
items auto-pass as ``nonbehavioral`` with a stated reason instead of
paging the owner. This keeps ``master`` meaningful without reintroducing
per-merge theater for Tier 1 changes.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WARNING_TEMPLATE = "passed on {commit}, code untouched since — not re-tested"

# Path prefix -> (area id, user-visible behavior, goal doc, regression neighbors).
AREA_TABLE: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "packages/ai_provider/",
        "provider",
        "provider requests and routing execution",
        "docs/goals/provider.md",
        ("orchestrator", "dashboard"),
    ),
    (
        "packages/ai_orchestrator/",
        "orchestrator",
        "routing and orchestration decisions",
        "docs/goals/orchestrator.md",
        ("agent-cli", "dashboard"),
    ),
    (
        "packages/ai_agent/",
        "agent-cli",
        "CLI agent runs and chat",
        "docs/goals/agent-cli.md",
        ("dashboard",),
    ),
    (
        "apps/workbench_dashboard/",
        "dashboard",
        "dashboard views and actions",
        "docs/goals/dashboard.md",
        (),
    ),
    ("apps/ai_council/", "council", "council deliberation", "docs/goals/council.md", ()),
    ("apps/job_search/", "job-search", "job search flows", "docs/goals/job-search.md", ()),
    (
        "company-site/",
        "company-site",
        "company website pages and intake",
        "docs/goals/company-site.md",
        (),
    ),
    ("apps/", "apps", "application behavior", "docs/goals/dashboard.md", ()),
    ("packages/", "packages", "shared package behavior", "docs/goals/provider.md", ()),
    ("scripts/", "tooling", "repo tooling", "docs/goals/meta.md", ()),
    ("tests/", "tests", "test suite", "docs/goals/meta.md", ()),
    ("docs/", "docs", "documentation", "docs/goals/meta.md", ()),
)

# Areas with no user-visible behavior; items auto-pass as nonbehavioral.
NONBEHAVIORAL_AREAS = frozenset({"tooling", "tests", "docs"})

BEHAVIOR_AREA_IDS = frozenset(area for _, area, _, _, _ in AREA_TABLE)

AREA_PREFIXES: dict[str, list[str]] = {}
for _prefix, _area, _, _, _ in AREA_TABLE:
    AREA_PREFIXES.setdefault(_area, []).append(_prefix)

# Area -> (how steps, expected outcome, where to observe). The owner reads
# this instead of guessing what "test the behavior" means for a diff.
TEST_GUIDANCE: dict[str, tuple[list[str], str, str]] = {
    "dashboard": (
        [
            "Open the served dashboard and navigate each affected view.",
            "Exercise the changed controls end to end, including submit and cancel paths.",
            "Watch for error toasts and confirm badge counts update.",
        ],
        "Views render, actions complete, no error toasts.",
        "Dashboard UI plus GET /api/status staying green.",
    ),
    "agent-cli": (
        [
            "Run the affected command with --help first.",
            "Run the documented dry-run form (plan/diagnose, no --execute).",
            "For execute paths, run once against a scratch copy and inspect the diff.",
        ],
        "Exit 0, plan metadata printed, no traceback, no unintended writes.",
        "Terminal output plus the artifacts transcript for the run.",
    ),
    "provider": (
        [
            "Run the scoped pytest for the touched adapter module.",
            "Trigger one real request on a local route and read the route line.",
            "Confirm usage/allowance reporting shows the call.",
        ],
        "Correct route chosen, response complete, usage recorded.",
        "Pytest output and the run's route/cost evidence.",
    ),
    "orchestrator": (
        [
            "Run the scoped pytest for the touched decision module.",
            "Trigger one decision (plan or route) and read the reasoning.",
            "Confirm privacy and cost-policy gates still hold.",
        ],
        "Sensible decision with visible reasoning; no gate bypass.",
        "Pytest output and the decision/route evidence.",
    ),
    "council": (
        [
            "Follow the apps/ai_council README quickstart for one deliberation.",
            "Confirm every model answers and the synthesis preserves disagreement.",
        ],
        "Raw responses plus a faithful synthesis, loopback-only.",
        "Council output and the served transcript.",
    ),
    "job-search": (
        [
            "Run the job-search suite for the touched flow.",
            "Walk the approval preview once (never --send in E2E).",
            "Confirm digest binding rejects a changed attachment.",
        ],
        "Preview correct, guards refuse tampered materials.",
        "Pytest output and the CLI preview text.",
    ),
    "apps": (
        [
            "Follow the app's README quickstart for the touched flow.",
            "Exercise the changed path once with realistic input.",
        ],
        "Flow completes with no errors and sensible output.",
        "App output and logs.",
    ),
    "packages": (
        [
            "Run the scoped pytest for the touched package.",
            "Exercise one consumer-facing entry point directly.",
        ],
        "Tests green and the entry point behaves as documented.",
        "Pytest output.",
    ),
    "company-site": (
        [
            "Open each changed page on the served company site, PL and EN.",
            "For shared assets, spot-check the PL index plus one EN page.",
            "Submit the intake form once when kontakt/contact or form.js changed.",
        ],
        "Pages render per the change; no broken layout, links, or form wiring.",
        "Served company site (keepalive-served from the serve tree).",
    ),
}

REGRESSION_LEAD = (
    "Nothing here changed directly; confirm the behavior still works "
    "end to end after the shared-dependency change."
)

# Area -> dashboard views where a live testing reminder makes sense.
# Areas without a dedicated tab fall back to home (the landing view).
AREA_VIEWS: dict[str, list[str]] = {
    "dashboard": ["home", "inbox"],
    "agent-cli": ["chat", "runs"],
    "provider": ["providers", "fleet"],
    "orchestrator": ["fleet", "runs"],
    "council": ["home"],
    "job-search": ["home"],
    "apps": ["home"],
    "packages": ["home"],
    "company-site": ["home"],
    "tooling": ["home"],
    "tests": ["home"],
    "docs": ["home"],
}


def views_for_area(area: str) -> list[str]:
    """Dashboard views showing live reminders for one area."""
    return list(AREA_VIEWS.get(area, ["home"]))


def area_for_path(path: str) -> tuple[str, str, str, tuple[str, ...]]:
    """Map one repo-relative path to (area, behavior, goal, neighbors)."""
    normalized = path.replace("\\", "/").lstrip("/")
    for prefix, area, behavior, goal, neighbors in AREA_TABLE:
        if normalized.startswith(prefix):
            return area, behavior, goal, neighbors
    if normalized.endswith(".md"):
        return "docs", "documentation", "docs/goals/meta.md", ()
    return "tooling", "repo tooling", "docs/goals/meta.md", ()


def _item_id(kind: str, area: str) -> str:
    return f"{kind}:{area}"


def _guidance_for(area: str, kind: str) -> dict:
    """Actionable test guidance: what to do, what to expect, where to look."""
    how, expected, where = TEST_GUIDANCE.get(area, ([], "", ""))
    if kind == "regression":
        how = [REGRESSION_LEAD, *how]
    return {"how": list(how), "expected": expected, "where": where}


def generate_checklist(
    merge_commit: str,
    files: Sequence[str],
    *,
    title: str | None = None,
    summaries: dict | None = None,
) -> dict:
    """Build one checklist from a merge diff's file list plus goal docs.

    One item per touched area; untouched regression neighbors of touched
    areas become ``regression`` items (the ancestor-matchable scope).
    Empty diffs yield an empty item list, never a silent pass.
    ``summaries`` (from :func:`change_summary`) adds per-item What
    (commit subjects + churn) and How/Expected guidance so the owner
    knows what to test and how. Behavior items also carry checkable
    ``steps`` drafted from diff evidence; steps the generator could
    not ground flag ``needs_pointers`` instead of scheduling a vague
    test.
    """
    from e2e_cases import draft_steps, needs_pointers, regression_steps

    by_file = (summaries or {}).get("by_file", {})
    churn = (summaries or {}).get("numstat", {})
    subjects = (summaries or {}).get("subjects", [])
    evidence = (summaries or {}).get("evidence", {})
    by_area: dict[str, dict] = {}
    for path in files:
        area, behavior, goal, _neighbors = area_for_path(path)
        entry = by_area.setdefault(area, {"behavior": behavior, "goals": set(), "files": []})
        entry["goals"].add(goal)
        entry["files"].append(path.replace("\\", "/"))
    items: list[dict] = []
    for area in sorted(by_area):
        entry = by_area[area]
        kind = "nonbehavioral" if area in NONBEHAVIORAL_AREAS else "behavior"
        item_files = sorted(entry["files"])
        what = sorted({subject for path in item_files for subject in by_file.get(path, [])})
        area_evidence = {path: evidence[path] for path in item_files if path in evidence}
        steps = draft_steps(area, area_evidence, subjects) if kind == "behavior" else []
        items.append(
            {
                "id": _item_id(kind, area),
                "kind": kind,
                "area": area,
                "behavior": entry["behavior"],
                "files": item_files,
                "churn": {path: churn[path] for path in item_files if path in churn},
                "what": what or list(subjects),
                "goals": sorted(entry["goals"]),
                "status": "pending",
                "steps": steps,
                "needs_pointers": needs_pointers(steps) if kind == "behavior" else False,
                **_guidance_for(area, kind),
            }
        )
    neighbors: set[str] = set()
    for area in by_area:
        for _prefix, table_area, _b, _g, table_neighbors in AREA_TABLE:
            if table_area == area:
                neighbors.update(table_neighbors)
    for area in sorted(neighbors - set(by_area)):
        behavior = next(b for _p, a, b, _g, _n in AREA_TABLE if a == area)
        goal = next(g for _p, a, _b, g, _n in AREA_TABLE if a == area)
        area_steps = regression_steps(area)
        if not area_steps:
            continue
        items.append(
            {
                "id": _item_id("regression", area),
                "kind": "regression",
                "area": area,
                "behavior": f"{behavior} (regression scope)",
                "files": [],
                "churn": {},
                "what": list(subjects),
                "goals": [goal],
                "status": "pending",
                "steps": area_steps,
                "needs_pointers": False,
                **_guidance_for(area, "regression"),
            }
        )
    return {
        "merge_commit": merge_commit,
        "title": title or f"E2E promotion for {merge_commit}",
        "items": items,
    }


def run_git(repo_root: str, *args: str) -> bytes:
    """Run one git command; raises RuntimeError on failure."""
    completed = subprocess.run(
        ["git", "-C", repo_root, *args],
        capture_output=True,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def is_ancestor(
    repo_root: str,
    ancestor: str,
    descendant: str,
    runner: Callable[..., bytes] | None = None,
) -> bool:
    """True when ``ancestor`` is an ancestor of ``descendant``."""
    run = runner or run_git
    try:
        run(repo_root, "merge-base", "--is-ancestor", ancestor, descendant)
    except RuntimeError:
        return False
    return True


def verify_no_diff(
    repo_root: str,
    ancestor_commit: str,
    merge_commit: str,
    files: Sequence[str],
    runner: Callable[..., bytes] | None = None,
) -> dict | None:
    """Return a no-diff proof, or None when the behavior's code changed.

    The proof spans the report commit to the merge commit over the
    item's files; an empty diff (zero bytes, hashed) is the evidence.
    """
    run = runner or run_git
    raw = run(repo_root, "diff", f"{ancestor_commit}...{merge_commit}", "--", *files)
    if raw:
        return None
    return {
        "ancestor_commit": ancestor_commit,
        "merge_commit": merge_commit,
        "files": sorted(files),
        "diff_bytes": 0,
        "diff_sha256": hashlib.sha256(raw).hexdigest(),
        "verified_utc": datetime.now(UTC).isoformat(),
    }


def find_ancestor_report(
    item_id: str,
    merge_commit: str,
    reports: Sequence[dict],
    repo_root: str,
    runner: Callable[..., bytes] | None = None,
    area: str = "",
) -> dict | None:
    """Latest passing report for the behavior on an ancestor commit.

    Behavior items match the same entry id; regression items (owner
    decision 4f52d6b2, option B) also match a passing behavior entry
    for the same area, with the no-diff proof then spanning the
    area's path prefixes.
    """
    candidates = [
        report
        for report in reports
        if report.get("overall") == "pass"
        and report.get("commit") != merge_commit
        and any(
            entry.get("verdict") == "pass"
            and (
                entry.get("id") == item_id
                or (area and item_id == f"regression:{area}" and entry.get("area") == area)
            )
            for entry in report.get("items", [])
        )
        and is_ancestor(repo_root, str(report.get("commit")), merge_commit, runner)
    ]
    candidates.sort(key=lambda report: str(report.get("built_utc") or ""))
    return candidates[-1] if candidates else None


def apply_ancestor_matching(
    checklist: dict,
    reports: Sequence[dict],
    repo_root: str,
    runner: Callable[..., bytes] | None = None,
) -> dict:
    """Auto-pass matchable items; every approval carries proof + warning.

    ``nonbehavioral`` items auto-pass with a stated reason.
    ``behavior``/``regression`` items auto-pass only with a linked prior
    passing report on an ancestor commit plus a no-diff proof; the
    warning cites the originally tested commit, never silently green.
    """
    merge_commit = str(checklist.get("merge_commit"))
    matched: list[dict] = []
    for item in checklist.get("items", []):
        entry = dict(item)
        if entry.get("kind") == "nonbehavioral":
            entry["status"] = "auto-pass"
            entry["verdict_by"] = "nonbehavioral"
            entry["reason"] = "docs/tests/tooling carry no user-visible behavior"
            matched.append(entry)
            continue
        report = find_ancestor_report(
            str(entry.get("id")),
            merge_commit,
            reports,
            repo_root,
            runner,
            str(entry.get("area") or ""),
        )
        if report is None:
            matched.append(entry)
            continue
        proof_files = [str(path) for path in entry.get("files", [])]
        if not proof_files:
            proof_files = list(AREA_PREFIXES.get(str(entry.get("area") or ""), []))
        proof = verify_no_diff(
            repo_root,
            str(report.get("commit")),
            merge_commit,
            proof_files,
            runner,
        )
        if proof is None:
            matched.append(entry)
            continue
        tested_on = tested_commit(report, str(entry.get("id")))
        entry["status"] = "auto-pass"
        entry["verdict_by"] = "ancestor"
        entry["ancestor_report"] = report.get("id")
        entry["proof"] = proof
        entry["tested_on"] = tested_on
        entry["warning"] = WARNING_TEMPLATE.format(commit=tested_on)
        matched.append(entry)
    return {**checklist, "items": matched}


def tested_commit(report: dict, item_id: str) -> str:
    """Originally tested commit for a report entry (unwinds chains)."""
    for entry in report.get("items", []):
        if entry.get("id") == item_id:
            return str(entry.get("tested_on") or report.get("commit"))
    return str(report.get("commit"))


def build_report(task: dict, submissions: dict[str, dict], verdict_by: str = "owner") -> dict:
    """Assemble the E2E report from submissions plus auto-passes.

    ``verdict_by`` is "owner" for human verdicts or "agent" for
    machine-verdicted all-agent checklists (brief ff9b255d-A).


    Verdicts are per step: every checkable step needs its own
    ``pass``/``fail``, and the item verdict derives fail-closed (any
    failed step fails the item). Stepless legacy items keep one
    explicit item verdict. Anything else fails closed. Per-step
    results are stored as durable proof. Auto-passed items keep
    their proof, warning, and originally tested commit. A ``bad-test``
    flag (with required notes) records that the steps themselves were
    untestable; it fails the overall report like any non-pass.
    """
    items: list[dict] = []
    for item in task.get("items", []):
        item_id = str(item.get("id"))
        if item.get("status") == "auto-pass":
            items.append(
                {
                    **item,
                    "verdict": "pass",
                    "tested_on": tested_on_for(item),
                }
            )
            continue
        submission = submissions.get(item_id)
        if submission is None:
            raise ValueError(f"Missing verdict for {item_id}")
        if str(submission.get("verdict", "")).strip().lower() == "bad-test":
            if not str(submission.get("notes", "") or "").strip():
                raise ValueError(f"Bad-test flag for {item_id} needs notes describing why")
            verdict = "bad-test"
            step_results = []
        elif item.get("steps"):
            step_results = _step_results_for(item, submission, item_id)
            verdict = (
                "fail" if any(entry["verdict"] == "fail" for entry in step_results) else "pass"
            )
        else:
            verdict = str(submission.get("verdict", "")).strip().lower()
            if verdict not in ("pass", "fail"):
                raise ValueError(f"Verdict for {item_id} must be pass or fail")
            step_results = []
        mismatches = _agent_mismatches(item, step_results)
        items.append(
            {
                **item,
                "status": "tested",
                "verdict": verdict,
                "verdict_by": verdict_by,
                "notes": str(submission.get("notes", "") or ""),
                "tested_on": str(task.get("merge_commit")),
                "step_results": step_results,
                "agent_check_mismatches": mismatches,
            }
        )
    overall = "pass" if items and all(e.get("verdict") == "pass" for e in items) else "fail"
    return {
        "task_id": task.get("id"),
        "commit": task.get("merge_commit"),
        "range_base": task.get("range_base"),
        "title": task.get("title"),
        "items": items,
        "overall": overall,
        "built_utc": datetime.now(UTC).isoformat(),
    }


def _step_results_for(item: dict, submission: dict, item_id: str) -> list[dict]:
    """Per-step proof; every step needs its own pass/fail verdict."""
    steps = item.get("steps") or []
    verdicts = submission.get("steps")
    if not isinstance(verdicts, list) or len(verdicts) != len(steps):
        raise ValueError(f"Verdict for {item_id} needs one verdict per step")
    results = []
    for step, verdict in zip(steps, verdicts, strict=True):
        clean = str(verdict or "").strip().lower()
        if clean not in ("pass", "fail"):
            raise ValueError(f"Verdict for {item_id} needs every step decided")
        results.append(
            {
                "action": step.get("action", ""),
                "expected": step.get("expected", ""),
                "verdict": clean,
            }
        )
    return results


def _agent_mismatches(item: dict, step_results: list[dict]) -> list[str]:
    """Owner-passed steps whose agent evidence reports failure.

    Owner verdicts always stand; a mismatch flags the step for the
    follow-up agent instead of silently trusting either side.
    """
    steps = item.get("steps") or []
    if len(steps) != len(step_results):
        return []
    mismatched: list[str] = []
    for step, result in zip(steps, step_results, strict=True):
        if not isinstance(step, dict) or not isinstance(result, dict):
            continue
        if result.get("verdict") != "pass":
            continue
        code = step.get("evidence_exit")
        if code is None or code == 0:
            continue
        mismatched.append(str(step.get("action", "")))
    return mismatched


def tested_on_for(item: dict) -> str:
    """Tested commit carried into the report for an auto-passed item."""
    if item.get("verdict_by") == "ancestor":
        return str(item.get("tested_on") or "")
    return ""


def merge_diff_files(
    repo_root: str,
    base: str,
    head: str,
    runner: Callable[..., bytes] | None = None,
) -> list[str]:
    """Files changed across ``base...head`` (the merge's own diff)."""
    run = runner or run_git
    out = run(repo_root, "diff", "--name-only", f"{base}...{head}")
    text = out.decode("utf-8", "replace").strip()
    return [line for line in text.splitlines() if line] if text else []


def merges_between(
    repo_root: str,
    base: str,
    head: str,
    runner: Callable[..., bytes] | None = None,
) -> list[str]:
    """Merge commits in ``base..head``, oldest first."""
    run = runner or run_git
    out = run(repo_root, "log", "--merges", "--format=%H", "--reverse", f"{base}..{head}")
    text = out.decode("utf-8", "replace").strip()
    return [line for line in text.splitlines() if line] if text else []


def change_summary(
    repo_root: str,
    base: str,
    head: str,
    files: Sequence[str],
    runner: Callable[..., bytes] | None = None,
) -> dict:
    """Commit subjects + per-file churn for the merge diff (the item's What)."""
    run = runner or run_git
    log = run(repo_root, "log", "--format=SUBJECT:%s", "--name-only", f"{base}..{head}")
    subjects: list[str] = []
    by_file: dict[str, list[str]] = {}
    current: str | None = None
    for line in log.decode("utf-8", "replace").splitlines():
        if line.startswith("SUBJECT:"):
            current = line[len("SUBJECT:") :].strip()
            if current and current not in subjects:
                subjects.append(current)
        elif line.strip() and current:
            by_file.setdefault(line.strip().replace("\\", "/"), []).append(current)
    numstat = run(repo_root, "diff", "--numstat", f"{base}...{head}", "--", *files)
    churn: dict[str, list[int]] = {}
    for line in numstat.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, path = parts
        churn[path.replace("\\", "/")] = [
            int(added) if added.isdigit() else 0,
            int(removed) if removed.isdigit() else 0,
        ]
    return {"subjects": subjects, "numstat": churn, "by_file": by_file}


def covers_range(
    report: dict,
    merge_commit: str,
    repo_root: str,
    runner: Callable[..., bytes] | None = None,
) -> bool:
    """True when a passing range report covers one merge's promotion.

    A range report (catch-up E2E over ``range_base...commit``) covers a
    merge only when the merge sits inside that span on the ancestry
    line. Ordinary per-merge reports cover only their own commit.
    """
    if report.get("overall") != "pass":
        return False
    if report.get("commit") == merge_commit and not report.get("range_base"):
        return True
    range_base = report.get("range_base")
    if not range_base:
        return False
    return is_ancestor(repo_root, str(range_base), merge_commit, runner) and is_ancestor(
        repo_root, merge_commit, str(report.get("commit")), runner
    )


def uncovered_merges(
    merges: Sequence[str],
    reports: Sequence[dict],
    repo_root: str,
    runner: Callable[..., bytes] | None = None,
) -> list[str]:
    """Merges with no passing own or covering range report."""
    return [
        merge
        for merge in merges
        if not any(covers_range(report, merge, repo_root, runner) for report in reports)
    ]


@dataclass(frozen=True)
class GateVerdict:
    """Promotion gate outcome for one merge commit."""

    allowed: bool
    reason: str


def promotion_verdict(merge_commit: str, reports: Sequence[dict]) -> GateVerdict:
    """Decide whether one merge may promote to master.

    Only that merge's own report matters: a failed (or missing) E2E
    blocks its own merge's promotion, never the whole line.
    """
    own = [r for r in reports if r.get("commit") == merge_commit]
    if not own:
        return GateVerdict(False, f"no E2E report for {merge_commit}")
    latest = sorted(own, key=lambda r: str(r.get("built_utc") or ""))[-1]
    if latest.get("overall") == "pass":
        return GateVerdict(True, f"E2E passed for {merge_commit}")
    return GateVerdict(False, f"E2E {latest.get('overall')} for {merge_commit}")


POINTER_RUN_KIND = "e2e-pointers"
POINTER_TERMINAL = frozenset({"completed", "failed", "cancelled"})


def pointer_body(merge: str, unclear: list[dict]) -> str:
    """Clarification text for unclear behaviors (owner or agent prompt tail)."""
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


def pointer_mission(merge: str, task_id: str, unclear: list[dict]) -> str:
    """Read-only pointers mission for the agent run (first, before the owner)."""
    return (
        "Author checkable E2E steps for the draft checklist below. READ-ONLY: "
        "inspect the merge diff and the served dashboard if needed; change no code.\n\n"
        f"Merge: {merge}\nTask: {task_id}\n\n"
        + pointer_body(merge, unclear)
        + "\n\nStep rules (violations fail review):\n"
        "- Steps run on the LIVE served dashboard as-is: no synthetic fixtures, "
        "no test dashboards, no invented setup. Read-only inspection preferred; "
        "mutations must be reversible, with the undo as the final step.\n"
        "- Each step is atomic and independent: verifiable alone in under 2 "
        "minutes. No run IDs, no cross-step choreography ('after X completes'), "
        "no meta-orchestration of runs or drains.\n"
        "- Every runnable step carries its exact backticked command "
        "(`.venv/Scripts/python.exe -m pytest <path> -q`, "
        "`.venv/Scripts/python.exe scripts/run-tests.py <group>`, "
        "`<tool> --help`, `scripts/<name>.py --dry-run`, "
        "`scripts/e2e-http-get.py <path> <status>`). A pytest/command step "
        "without backticks is a defect.\n"
        "- One behavior per step; concrete inputs plus the exact text or "
        "state to observe. Never emit generic standing checks.\n"
        "\nReply BOTH ways so the result survives truncation:\n"
        "1. Write pointers.json at your worktree root: "
        '{"<item-id>": [{"action": "...", "expected": "..."}], ...} '
        'or {"declined": "reason"}.\n'
        "2. Also emit STEPS:{...} (same JSON) or DECLINE:<reason> in output.\n"
        "Every unclear item id needs at least one step. If the change is not "
        "verifiable from any user surface, DECLINE instead of guessing."
    )


def queue_pointer_run(stores, merge: str, task_id: str, unclear: list[dict]) -> dict:
    """Queue a preapproved agent run to author pointers (human escalation last)."""
    run_id = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    run = {
        "id": run_id,
        "title": f"E2E pointers: {merge}",
        "status": "queued",
        "body": pointer_mission(merge, task_id, unclear),
        "origin": POINTER_RUN_KIND,
        "fanout_policy": "restricted",
        "fanout_effective": "restricted",
        "approval_mode": "e2e-followup",
        "inbox_id": None,
        "project_id": None,
        "plan_id": None,
        "created_at_utc": now,
        "updated_at_utc": now,
        "metadata": {
            "kind": POINTER_RUN_KIND,
            "task_id": task_id,
            "merge": merge,
            "unclear": unclear,
        },
    }
    stores.runs.put(run_id, run)
    return run


def file_owner_pointers(stores, merge: str, unclear: list[dict]) -> dict:
    """File the owner pointer request (agent declined, failed, or invalid)."""
    return stores.create_inbox_task(
        title=f"E2E pointers needed: {merge}",
        body=pointer_body(merge, unclear),
        task_type="clarification",
        created_by="supervisor",
        assignee="owner",
        metadata={"merge_commit": merge, "kind": "e2e-pointers"},
    )


POINTER_VERDICT_MAX_BYTES = 65536


def _pointer_steps_from_text(text: str) -> dict | None:
    """Find a STEPS:{...} verdict anywhere; None means no parseable verdict.

    Tries every marker occurrence: agents sometimes emit a broken draft
    before the final verdict.
    """
    decoder = json.JSONDecoder(strict=False)
    start = 0
    while True:
        index = (text or "").find("STEPS:", start)
        if index < 0:
            return None
        try:
            steps, _end = decoder.raw_decode(text, index + len("STEPS:"))
        except ValueError:
            start = index + len("STEPS:")
            continue
        if isinstance(steps, dict):
            return steps
        start = index + len("STEPS:")


def _pointer_steps_from_file(worktree: str) -> dict | None:
    """Read pointers.json from the executor-recorded worktree (truncation-proof).

    The path comes from our own executor receipt, never from agent input;
    only the file *content* is agent-crafted (validated downstream).
    """
    if not worktree:
        return None
    try:
        path = Path(worktree) / "pointers.json"
        if not path.is_file() or path.stat().st_size > POINTER_VERDICT_MAX_BYTES:
            return None
        steps = json.loads(path.read_text(encoding="utf-8"), strict=False)
    except (OSError, ValueError):
        return None
    if not isinstance(steps, dict) or "declined" in steps:
        return None
    return steps


def _pointer_steps(receipt: dict) -> dict | None:
    """Parse the agent's verdict: file channel first, stdout/summary fallback."""
    if not isinstance(receipt, dict):
        return None
    steps = _pointer_steps_from_file(receipt.get("worktree") or "")
    if steps is not None:
        return steps
    for key in ("stdout_tail", "summary"):
        steps = _pointer_steps_from_text(receipt.get(key) or "")
        if steps is not None:
            return steps
    return None


def route_pointer_runs(stores) -> list[dict]:
    """Route terminal pointer runs: finalize on valid steps, else escalate.

    Called after every drain (manual + scheduled). Each run routes once
    (metadata.routed); invalid agent output escalates like a decline —
    the owner path is today's behavior, never a new failure mode.
    """
    outcomes = []
    runs, _total = stores.runs.list(limit=1000)
    for run in runs:
        if not isinstance(run, dict):
            continue
        metadata = run.get("metadata") or {}
        if metadata.get("kind") != POINTER_RUN_KIND:
            continue
        if run.get("status") not in POINTER_TERMINAL or metadata.get("routed"):
            continue
        task_id = metadata.get("task_id")
        merge = metadata.get("merge", "")
        unclear = metadata.get("unclear") or []
        record = stores.e2e_tasks.get(task_id) if task_id else None
        outcome: dict[str, Any] = {"run_id": run["id"], "task_id": task_id}
        if record is None or record.get("status") != "draft" or not isinstance(task_id, str):
            outcome["action"] = "stale"
        else:
            action = "escalated"
            if run.get("status") == "completed":
                receipts = run.get("receipts") or []
                receipt = receipts[-1] if receipts else {}
                steps = _pointer_steps(receipt if isinstance(receipt, dict) else {})
                if steps:
                    try:
                        stores.finalize_e2e_task(task_id, steps)
                        action = "finalized"
                    except Exception:  # noqa: BLE001 - bad steps escalate, never crash drain
                        pass
                if action == "escalated" and steps:
                    if _apply_covered_pointer_steps(stores, task_id, steps):
                        try:
                            stores.open_resolved_draft(task_id)
                            action = "finalized"
                        except Exception:  # noqa: BLE001 - rest still unclear, escalate it
                            outcome["partial"] = True
                            covered = _covered_pointer_ids(stores, task_id)
                            rest = [u for u in unclear if u.get("id") not in covered]
                            file_owner_pointers(stores, merge, rest or unclear)
                    else:
                        file_owner_pointers(stores, merge, unclear)
                elif action == "escalated":
                    file_owner_pointers(stores, merge, unclear)
            else:
                file_owner_pointers(stores, merge, unclear)
            outcome["action"] = action
        metadata["routed"] = outcome["action"]
        run["metadata"] = metadata
        stores.runs.put(run["id"], run)
        outcomes.append(outcome)
    return outcomes


def _covered_pointer_ids(stores, task_id: str) -> set[str]:
    """Item ids whose pointers flag cleared on a draft (partial progress)."""
    record = stores.e2e_tasks.get(task_id)
    if record is None:
        return set()
    return {
        str(item.get("id", ""))
        for item in record.get("items", [])
        if isinstance(item, dict) and not item.get("needs_pointers", True)
    }


def _apply_covered_pointer_steps(stores, task_id: str, steps: dict) -> bool:
    """Apply valid steps for covered items; False when nothing applied."""
    from e2e_cases import validate_steps

    record = stores.e2e_tasks.get(task_id)
    if record is None or record.get("status") != "draft":
        return False
    applied = False
    for item in record.get("items", []):
        if not isinstance(item, dict) or item.get("status") == "auto-pass":
            continue
        item_id = str(item.get("id", ""))
        if item_id not in steps or not item.get("needs_pointers", True):
            continue
        try:
            item["steps"] = validate_steps(steps[item_id])
        except (ValueError, TypeError):
            return False
        item["needs_pointers"] = False
        applied = True
    if applied:
        stores.e2e_tasks.put(task_id, record)
    return applied
