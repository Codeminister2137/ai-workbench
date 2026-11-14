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
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

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
    ("apps/", "apps", "application behavior", "docs/goals/dashboard.md", ()),
    ("packages/", "packages", "shared package behavior", "docs/goals/provider.md", ()),
    ("scripts/", "tooling", "repo tooling", "docs/goals/meta.md", ()),
    ("tests/", "tests", "test suite", "docs/goals/meta.md", ()),
    ("docs/", "docs", "documentation", "docs/goals/meta.md", ()),
)

# Areas with no user-visible behavior; items auto-pass as nonbehavioral.
NONBEHAVIORAL_AREAS = frozenset({"tooling", "tests", "docs"})

BEHAVIOR_AREA_IDS = frozenset(area for _, area, _, _, _ in AREA_TABLE)

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
}

REGRESSION_LEAD = (
    "Nothing here changed directly; confirm the behavior still works "
    "end to end after the shared-dependency change."
)


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
    knows what to test and how.
    """
    by_file = (summaries or {}).get("by_file", {})
    churn = (summaries or {}).get("numstat", {})
    subjects = (summaries or {}).get("subjects", [])
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
) -> dict | None:
    """Latest passing report for the behavior on an ancestor commit."""
    candidates = [
        report
        for report in reports
        if report.get("overall") == "pass"
        and report.get("commit") != merge_commit
        and any(
            entry.get("id") == item_id and entry.get("verdict") == "pass"
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
            str(entry.get("id")), merge_commit, reports, repo_root, runner
        )
        if report is None:
            matched.append(entry)
            continue
        proof = verify_no_diff(
            repo_root,
            str(report.get("commit")),
            merge_commit,
            [str(path) for path in entry.get("files", [])],
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


def build_report(task: dict, submissions: dict[str, dict]) -> dict:
    """Assemble the E2E report from owner submissions plus auto-passes.

    Every pending item needs a ``pass``/``fail`` verdict; anything else
    (or a missing verdict) fails closed. Auto-passed items keep their
    proof, warning, and originally tested commit.
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
        verdict = str(submission.get("verdict", "")).strip().lower()
        if verdict not in ("pass", "fail"):
            raise ValueError(f"Verdict for {item_id} must be pass or fail")
        items.append(
            {
                **item,
                "status": "tested",
                "verdict": verdict,
                "verdict_by": "owner",
                "notes": str(submission.get("notes", "") or ""),
                "tested_on": str(task.get("merge_commit")),
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
