#!/usr/bin/env python3
"""Weekly forgotten-items sweep: find neglected work, queue it, remember it.

One shot: scan dashboard stores (runs/inbox/E2E), git branches/worktrees,
docs plans/goals linkage, and stale E2E draft files for items that failed,
stalled, or were answered but never closed — then optionally file one
inbox task per finding group so nothing rots silently.

Findings below their age gate are reported as ``watching`` (visible in the
receipt, never filed). Findings at/above the gate are filed once: a finding
key already filed by the previous receipt is not re-filed, so the weekly
task cannot spam the inbox; aggregate groups re-file only when their
membership changes.

A JSON receipt lands under ``.tmp/forgotten-sweep/`` on every run.

Exit codes: 0 clean (findings are data, not failure), 1 failed (store
unreadable, git failed, or a ``--file`` POST failed).
``--dry-run`` prints what ``--file`` would file without POSTing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

TERMINAL_RUN = frozenset({"completed", "failed", "cancelled", "canceled", "merged"})
IDLE_RUN = frozenset({"queued", "running", "paused"})

# Filing gates (hours). Below gate -> watching, at/above -> file once.
GATE_H = {
    "R1": 48,  # failed run, no follow-up
    "R2": 48,  # idle queued/running/paused run
    "R3": 48,  # branch-ready run awaiting merge
    "R4": 12,  # live run stuck
    "R5": 0,  # stale run records with closed approvals
    "R6": 24,  # terminal run, source item open, no outcome note
    "I1": 24,  # answered-never-closed inbox
    "I2": 48,  # open agent inbox rotting
    "I3": 168,  # open owner inbox backlog (7d)
    "I4": 24,  # agent item idle after its run finished
    "I5": 0,  # standing owner gate with no open item
    "E1": 24,  # fail E2E report, no follow-up action
    "E2": 24,  # fail E2E report, follow-up itself failed
    "E3": 48,  # open E2E task (owner testing backlog)
    "G1": 0,  # merged local branches (housekeeping; always actionable)
    "G2": 0,  # merged remote branches
    "G3": 0,  # prunable run worktrees (7d+ terminal, via prune script)
    "G4": 0,  # serve tree lags origin (redeploy verification)
    "P1": 0,  # plans without registry project header
    "P2": 0,  # registry projects off on-track
    "P3": 0,  # registry goal docs missing
    "P4": 0,  # stale credential-blocker claims (key already configured)
    "D1": 0,  # stale TEMP E2E drafts (7d+)
}

SHORT_RE = re.compile(r"[0-9a-f]{7,40}")
FOLLOWUP_RE = re.compile(r"E2E follow-up:\s*([0-9a-f]{7,40})", re.IGNORECASE)
STILL_OPEN_RE = re.compile(r"stays open|still open|not resolved|unresolved|reopen", re.IGNORECASE)
TRACKER_RE = re.compile(r"\b[0-9a-f]{8,40}\b")
STOPWORDS = frozenset(
    {
        "with",
        "from",
        "that",
        "this",
        "have",
        "will",
        "task",
        "tasks",
        "failed",
        "failure",
        "error",
        "follow",
        "followup",
        "promotion",
        "agent",
        "owner",
        "workbench",
        "dashboard",
    }
)
OLD_RUN_H = 168  # runs older than this were likely done another way: verify first


def _title_words(title: str) -> set[str]:
    words = {w for w in re.split(r"[^a-z0-9]+", title.casefold()) if len(w) >= 4}
    return words - STOPWORDS


def _strong_word_overlap(left: set[str], right: set[str]) -> bool:
    shared = left & right
    return any(len(w) >= 5 for w in shared) or len(shared) >= 2


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _age_h(value: Any, now: datetime) -> float | None:
    dt = _parse_ts(value)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def _load_store(data_dir: Path, name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    store = data_dir / name
    if not store.is_dir():
        return out
    for entry in sorted(store.iterdir()):
        if entry.suffix != ".json" or not entry.is_file():
            continue
        try:
            record = json.loads(entry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict):
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
                record.setdefault("_file_mtime", mtime.isoformat())
            except OSError:
                pass
            out.append(record)
    return out


def _record_ts(record: dict[str, Any]) -> Any:
    """First available timestamp: explicit fields, then file mtime fallback."""
    return (
        record.get("created_at_utc")
        or record.get("created_at")
        or record.get("built_utc")
        or record.get("_file_mtime")
    )


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _worktree_branches(repo: Path) -> set[str]:
    try:
        raw = _git(repo, "worktree", "list", "--porcelain")
    except RuntimeError:
        return set()
    branches = set()
    for line in raw.splitlines():
        if line.startswith("branch refs/heads/"):
            branches.add(line.split("refs/heads/", 1)[1])
    return branches


def _finding(
    key: str,
    category: str,
    title: str,
    assignee: str,
    action: str,
    members: list[dict[str, Any]],
    max_age_h: float | None,
    link: str = "",
) -> dict[str, Any]:
    gate = GATE_H[category]
    return {
        "key": key,
        "category": category,
        "title": title,
        "assignee": assignee,
        "action": action,
        "members": members,
        "max_age_h": round(max_age_h, 1) if max_age_h is not None else None,
        "gate_h": gate,
        "fileable": max_age_h is not None and max_age_h >= gate,
        "link": link,
    }


def _dash_link(*parts: str) -> str:
    return "http://127.0.0.1:8766/#/" + "/".join(parts)


def _member(record_id: str, title: str, age_h: float | None, extra: str = "") -> dict[str, Any]:
    return {
        "id": record_id,
        "title": title[:100],
        "age_h": round(age_h, 1) if age_h is not None else None,
        "extra": extra[:140],
    }


def _done_elsewhere_evidence(
    title: str,
    own_inbox_id: str,
    inbox: list[dict[str, Any]],
    merged_branches: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Gather possibly-resolved evidence: closed inbox + merged branches."""
    evidence: list[dict[str, Any]] = []
    words = _title_words(title)
    if not words:
        return evidence
    for item in inbox:
        if str(item.get("status", "")) != "closed":
            continue
        if str(item.get("id", "")) == own_inbox_id:
            continue
        if _strong_word_overlap(words, _title_words(str(item.get("title", "")))):
            evidence.append(
                _member(
                    f"inbox:{str(item.get('id', '?'))[:8]}",
                    str(item.get("title", "")),
                    None,
                    f"closed: {str(item.get('resolution', ''))[:100]}",
                )
            )
            if len(evidence) >= 3:
                return evidence
    for branch in merged_branches:
        tokens = set(re.split(r"[^a-z0-9]+", branch.casefold())) - STOPWORDS
        if _strong_word_overlap(words, tokens):
            evidence.append(_member(f"branch:{branch}", branch, None, "merged to develop"))
            if len(evidence) >= 5:
                return evidence
    return evidence


def _prior_sweep_resolution(inbox: list[dict[str, Any]], rid: str) -> str | None:
    """Closed sweep item already adjudicating this run id, if any.

    Runs without an inbox link (inbox_id None) never match _closed_loop;
    a prior closed sweep finding that names the run id is the same
    closed loop. Tracked-still-open resolutions don't count.
    """
    needles = {rid.lower(), rid[:8].lower()}
    for item in inbox:
        if str(item.get("status", "")) != "closed":
            continue
        if "[sweep]" not in str(item.get("title", "")):
            continue
        blob = (
            f"{item.get('title', '')} {item.get('body', '')} "
            f"{item.get('resolution', '')} {item.get('note', '')}".lower()
        )
        if not any(needle and needle in blob for needle in needles):
            continue
        resolution = f"{item.get('resolution', '')} {item.get('answer', '')}"
        if STILL_OPEN_RE.search(resolution):
            for ref in TRACKER_RE.findall(resolution):
                tracker = next(
                    (entry for entry in inbox if str(entry.get("id", "")).startswith(ref[:12])),
                    None,
                )
                if tracker is not None and str(tracker.get("status", "")) != "closed":
                    return None  # tracked elsewhere and still open
        return str(item.get("id", ""))[:8]
    return None


def _staged_refs_resolve(repo: Path | None, run: dict[str, Any]) -> bool:
    """True when a branch-ready run's staged branch/commit still resolves.

    Skipped (True) without a repo: unit tests without git keep the old
    finding. A run naming neither ref keeps the old finding too — there
    is nothing verifiable to check.
    """
    branch = str(run.get("branch") or "").strip()
    commit = str(run.get("commit") or "").strip()
    if repo is None or (not branch and not commit):
        return True
    for ref in [r for r in (branch, f"refs/heads/{branch}" if branch else "", commit) if r]:
        try:
            _git(repo, "rev-parse", "--verify", "--quiet", ref)
            return True
        except RuntimeError:
            continue
    return False


def collect_runs(
    runs: list[dict[str, Any]],
    inbox: list[dict[str, Any]],
    now: datetime,
    merged_branches: tuple[str, ...] = (),
    repo: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect run findings; resolved-first: a closed loop never files.

    Returns (findings, resolved_skipped). A failed/idle run whose linked
    approval is closed is resolved (or a stale record, see R5), never
    forgotten work. Old runs without hard resolution file only with a
    verify-first action plus done-elsewhere evidence.
    """
    findings: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    stale_records: list[dict[str, Any]] = []
    by_inbox: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        if run.get("inbox_id"):
            by_inbox.setdefault(str(run["inbox_id"]), []).append(run)
    inbox_by_id = {str(item.get("id", "")): item for item in inbox}
    open_refs: list[str] = []
    for item in inbox:
        if item.get("status") in ("open", "answered"):
            open_refs.append(
                f"{item.get('title', '')} {item.get('body', '')} "
                f"{item.get('resolution', '')} {item.get('note', '')}".lower()
            )

    def _closed_loop(run: dict[str, Any]) -> dict[str, Any] | None:
        """Return the closed linked approval, if the run's loop is closed."""
        linked = inbox_by_id.get(str(run.get("inbox_id") or ""))
        if linked is None or str(linked.get("status", "")) != "closed":
            return None
        resolution = f"{linked.get('resolution', '')} {linked.get('answer', '')}"
        if STILL_OPEN_RE.search(resolution):
            for ref in TRACKER_RE.findall(resolution):
                tracker = next(
                    (item for item in inbox if str(item.get("id", "")).startswith(ref[:12])),
                    None,
                )
                if tracker is not None and str(tracker.get("status", "")) != "closed":
                    return None  # tracked elsewhere and still open: not resolved
        return linked

    def _verify_first_action(base: str, age: float | None) -> str:
        if age is not None and age >= OLD_RUN_H:
            return (
                "VERIFY FIRST — old run, likely done another way: check the "
                "evidence below and the run report; stamp superseded_by when "
                "confirmed, else: " + base[0].lower() + base[1:]
            )
        return base

    for run in runs:
        rid = str(run.get("id", "?"))
        title = str(run.get("title", ""))
        status = str(run.get("status", ""))
        created = _record_ts(run)
        age = _age_h(created, now)
        if age is None:
            continue
        if status in ("failed", "needs-attention"):
            if run.get("superseded_by"):
                resolved.append({"key": f"R1:{rid}", "reason": "superseded_by stamp"})
                continue
            linked = _closed_loop(run)
            if linked is not None:
                resolved.append(
                    {
                        "key": f"R1:{rid}",
                        "reason": f"linked approval closed: {str(linked.get('resolution', ''))[:120]}",
                    }
                )
                continue
            prior = _prior_sweep_resolution(inbox, rid)
            if prior is not None:
                resolved.append({"key": f"R1:{rid}", "reason": f"prior sweep resolution: {prior}"})
                continue
            siblings = [r for r in by_inbox.get(str(run.get("inbox_id") or ""), []) if r is not run]
            newer_ok = any(
                (_parse_ts(_record_ts(r)) or now) > (_parse_ts(created) or now)
                and str(r.get("status")) != "failed"
                for r in siblings
            )
            newer_failed = any(
                (_parse_ts(_record_ts(r)) or now) > (_parse_ts(created) or now) for r in siblings
            )
            mentioned = any(rid[:8].lower() in ref for ref in open_refs)
            if newer_ok or newer_failed or mentioned:
                resolved.append({"key": f"R1:{rid}", "reason": "superseded or queued"})
                continue
            members = [_member(rid, title, age, str(run.get("error", "")))]
            members += _done_elsewhere_evidence(
                title, str(run.get("inbox_id") or ""), inbox, merged_branches
            )
            label = (
                "Failed run with no follow-up"
                if status == "failed"
                else "Run finished without a deliverable report"
            )
            findings.append(
                _finding(
                    f"R1:{rid}",
                    "R1",
                    f"{label}: {title[:70]}",
                    "agent",
                    _verify_first_action(
                        "Investigate the error; queue a fix run, or stamp the run "
                        "record with superseded_by=<run-id> when fixed elsewhere.",
                        age,
                    ),
                    members,
                    age,
                )
            )
        elif status in IDLE_RUN:
            linked = _closed_loop(run)
            if linked is not None:
                if run.get("cancel_requested"):
                    resolved.append({"key": f"R2:{rid}", "reason": "cancellation in flight"})
                    continue
                stale_records.append(
                    _member(
                        rid,
                        title,
                        age,
                        f"approval {str(linked.get('id', ''))[:8]} closed: "
                        f"{str(linked.get('resolution', ''))[:100]}",
                    )
                )
                resolved.append({"key": f"R2:{rid}", "reason": "loop closed; stale record"})
                continue
            members = [_member(rid, title, age)]
            members += _done_elsewhere_evidence(
                title, str(run.get("inbox_id") or ""), inbox, merged_branches
            )
            findings.append(
                _finding(
                    f"R2:{rid}",
                    "R2",
                    f"Idle {status} run: {title[:70]}",
                    "agent",
                    _verify_first_action("Drain it, requeue it, or cancel with a note.", age),
                    members,
                    age,
                )
            )
        elif status == "branch-ready":
            if _staged_refs_resolve(repo, run):
                findings.append(
                    _finding(
                        f"R3:{rid}",
                        "R3",
                        f"Branch-ready run awaiting merge: {title[:70]}",
                        "agent",
                        "Review the staged branch and merge or close the run.",
                        [_member(rid, title, age)],
                        age,
                    )
                )
            else:
                findings.append(
                    _finding(
                        f"R3:{rid}",
                        "R3",
                        f"Branch-ready run with lost staged branch: {title[:70]}",
                        "agent",
                        _verify_first_action(
                            "Staged branch/commit resolve nowhere; verify the work "
                            "landed elsewhere, then close the run record.",
                            age,
                        ),
                        [_member(rid, title, age, str(run.get("branch") or ""))],
                        age,
                    )
                )
        elif status == "live":
            findings.append(
                _finding(
                    f"R4:{rid}",
                    "R4",
                    f"Live run stuck: {title[:70]}",
                    "agent",
                    "Verify it is still streaming; finish or cancel it.",
                    [_member(rid, title, age)],
                    age,
                )
            )
    if stale_records:
        oldest = max(m["age_h"] for m in stale_records if m["age_h"] is not None)
        findings.append(
            _finding(
                _aggregate_key("R5", stale_records),
                "R5",
                f"Stale run records with closed approvals ({len(stale_records)})",
                "agent",
                "Cancel the stale records (work already decided/done); loops are closed.",
                stale_records,
                oldest,
            )
        )
    orphans: list[dict[str, Any]] = []
    for run in runs:
        if str(run.get("status", "")) not in TERMINAL_RUN:
            continue
        source_id = str(run.get("bridged_from") or run.get("inbox_id") or "")
        if not source_id:
            continue
        source = inbox_by_id.get(source_id)
        if source is None or str(source.get("status", "")) != "open":
            continue
        if str(run.get("id", "?")) in str(source.get("note") or ""):
            continue
        age = _age_h(run.get("finished_at_utc"), now)
        orphans.append(_member(str(run.get("id", "?")), str(run.get("title", "")), age))
    if orphans:
        ages = [m["age_h"] for m in orphans if m["age_h"] is not None]
        findings.append(
            _finding(
                _aggregate_key("R6", orphans),
                "R6",
                f"Terminal runs never reported back ({len(orphans)})",
                "agent",
                "Post each run's outcome to its source item (report-back gap or regression).",
                orphans,
                max(ages) if ages else 0.0,
            )
        )
    return findings, resolved


def collect_inbox(
    inbox: list[dict[str, Any]],
    now: datetime,
    runs: list[dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for gate in gates or []:
        if not isinstance(gate, dict) or not gate.get("id"):
            continue
        # Any status covers: a closed gate item carries its resolution, so
        # re-filing on close would nag forever. I5 fires only when the
        # gate has no item at all (deleted or never filed).
        covered = any(
            isinstance(item, dict)
            and str((item.get("metadata") or {}).get("owner_gate", "")) == gate["id"]
            for item in inbox
        )
        if not covered:
            finding = _finding(
                f"I5:{gate['id']}",
                "I5",
                str(gate.get("title") or gate["id"]),
                "owner",
                "Standing owner gate lost its dashboard item; re-filed from the registry.",
                [],
                0.0,
            )
            finding["gate_id"] = gate["id"]
            finding["gate_body"] = str(gate.get("body") or "")
            finding["gate_type"] = str(gate.get("type") or "decision")
            finding["gate_options"] = list(gate.get("options") or [])
            findings.append(finding)
    for item in inbox:
        iid = str(item.get("id", "?"))
        title = str(item.get("title", ""))
        status = str(item.get("status", ""))
        assignee = str(item.get("assignee", "owner"))
        created = _record_ts(item)
        age = _age_h(created, now)
        if age is None:
            continue
        if status == "answered":
            findings.append(
                _finding(
                    f"I1:{iid}",
                    "I1",
                    f"Answered but never closed: {title[:70]}",
                    "agent",
                    "Apply the owner's answer, then close with a resolution note.",
                    [_member(iid, title, age, str(item.get("answer", "")))],
                    age,
                )
            )
        elif status == "open" and assignee == "agent":
            findings.append(
                _finding(
                    f"I2:{iid}",
                    "I2",
                    f"Open agent item: {title[:70]}",
                    "agent",
                    "Work it FIFO or reassign with a note.",
                    [_member(iid, title, age)],
                    age,
                )
            )
        elif status == "open":
            findings.append(
                _finding(
                    f"I3:{iid}",
                    "I3",
                    f"Open owner item: {title[:70]}",
                    "owner",
                    "Owner decision/action pending.",
                    [_member(iid, title, age)],
                    age,
                )
            )
    if runs is not None:
        by_id = {str(run.get("id", "")): run for run in runs if isinstance(run, dict)}
        for item in inbox:
            if str(item.get("status", "")) != "open":
                continue
            if str(item.get("assignee", "owner")) != "agent":
                continue
            metadata = item.get("metadata")
            rid = str((metadata or {}).get("bridge_run_id", "") or "")
            run = by_id.get(rid)
            if run is None:
                continue
            run_status = str(run.get("status", ""))
            if run_status not in ("completed", "failed", "cancelled", "merged"):
                continue
            iid = str(item.get("id", "?"))
            title = str(item.get("title", ""))
            ended = run.get("finished_at_utc") or run.get("updated_at_utc") or _record_ts(run)
            run_age = _age_h(ended, now)
            findings.append(
                _finding(
                    f"I4:{iid}",
                    "I4",
                    f"Agent item idle after run {run_status}: {title[:70]}",
                    "agent",
                    "Close with the run outcome, or re-queue a follow-up run.",
                    [_member(f"run:{rid[:8]}", title, run_age, f"run {run_status}")],
                    run_age if run_age is not None else 0.0,
                )
            )
    return findings


def _followup_shorts(
    runs: list[dict[str, Any]], inbox: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Map E2E merge-commit short hash -> follow-up presence and run status."""
    info: dict[str, dict[str, Any]] = {}
    for run in runs:
        match = FOLLOWUP_RE.search(str(run.get("title", "")))
        if not match:
            continue
        short = match.group(1)[:12].lower()
        slot = info.setdefault(short, {"runs": [], "inbox": False})
        slot["runs"].append(str(run.get("status", "")))
    for item in inbox:
        match = FOLLOWUP_RE.search(str(item.get("title", "")))
        if match:
            info.setdefault(match.group(1)[:12].lower(), {"runs": [], "inbox": False})["inbox"] = (
                True
            )
    return info


def collect_e2e(
    tasks: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    inbox: list[dict[str, Any]],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    followups = _followup_shorts(runs, inbox)
    for task in tasks:
        if str(task.get("status", "")) == "submitted":
            continue
        tid = str(task.get("id", "?"))
        title = str(task.get("title", ""))
        age = _age_h(_record_ts(task), now)
        if age is None:
            continue
        merge = str(task.get("merge_commit") or "")
        if merge:
            own_ts = _parse_ts(_record_ts(task))
            superseded = any(
                str(other.get("merge_commit") or "") == merge
                and str(other.get("id", "")) != tid
                and (_parse_ts(_record_ts(other)) or now) > (own_ts or now)
                for other in tasks
            )
            if superseded:
                resolved.append(
                    {"key": f"E3:{tid}", "reason": "superseded by a newer task for the merge"}
                )
                continue
        behaviors = ", ".join(
            sorted(
                {
                    str(item.get("behavior") or item.get("id", ""))
                    for item in (task.get("items") or [])
                    if isinstance(item, dict)
                }
            )
        )
        findings.append(
            _finding(
                f"E3:{tid}",
                "E3",
                f"Open E2E task (owner testing): {title[:70]}",
                "owner",
                "Run the checklist and submit, or close as superseded.",
                [_member(tid, title, age, behaviors[:140])],
                age,
                _dash_link("e2e", tid),
            )
        )
    for report in reports:
        if str(report.get("overall", "")) in ("pass", "passed"):
            continue
        rid = str(report.get("id", "?"))
        title = str(report.get("title", ""))
        final_followup = next(
            (
                item
                for item in inbox
                if (item.get("metadata") or {}).get("report_id") == rid
                and item.get("status") == "closed"
                and item.get("resolution_kind") == "final"
                and str(item.get("resolution") or "").strip()
            ),
            None,
        )
        if final_followup is not None:
            resolved.append(
                {
                    "key": f"E2:{rid}",
                    "reason": "linked follow-up has a final resolution",
                    "inbox_id": final_followup["id"],
                }
            )
            continue
        age = _age_h(_record_ts(report), now)
        if age is None:
            continue
        commit = str(report.get("commit", "") or "")
        if commit:
            own_ts = _parse_ts(_record_ts(report))
            covered = any(
                str(other.get("commit", "") or "") == commit
                and str(other.get("id", "")) != rid
                and str(other.get("overall", "")) in ("pass", "passed")
                and (_parse_ts(_record_ts(other)) or now) > (own_ts or now)
                for other in reports
            )
            if covered:
                resolved.append({"key": f"E1:{rid}", "reason": "covered by a newer passing report"})
                continue
        shorts = {s[:12].lower() for s in SHORT_RE.findall(title)}
        commit = str(report.get("commit", "") or "").lower()
        if len(commit) >= 7:
            shorts.add(commit[:12])
        linked = [followups[s] for s in shorts if s in followups]
        if not linked:
            findings.append(
                _finding(
                    f"E1:{rid}",
                    "E1",
                    f"Failing E2E with no follow-up action: {title[:70]}",
                    "agent",
                    "File the E2E follow-up run (or close the report as superseded).",
                    [_member(rid, title, age)],
                    age,
                )
            )
        elif all("failed" in slot["runs"] or not slot["runs"] for slot in linked):
            runs_desc = ",".join(sorted({s for slot in linked for s in slot["runs"]}) or ["?"])
            findings.append(
                _finding(
                    f"E2:{rid}",
                    "E2",
                    f"Failing E2E whose follow-up failed ({runs_desc}): {title[:60]}",
                    "agent",
                    "Investigate the failed follow-up; requeue or fix directly.",
                    [_member(rid, title, age, runs_desc)],
                    age,
                )
            )
    return findings, resolved


def _aggregate_key(category: str, members: list[dict[str, Any]]) -> str:
    import hashlib

    digest = hashlib.sha256("|".join(sorted(m["id"] for m in members)).encode("utf-8")).hexdigest()[
        :12
    ]
    return f"{category}:{digest}:{len(members)}"


def collect_git(repo: Path, runs_dir: Path, now: datetime) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            cwd=repo,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        pass  # remote view may be stale; local view still valid
    try:
        merged_local = [
            b.strip().lstrip("*+ ")
            for b in _git(repo, "branch", "--merged", "develop").splitlines()
            if b.strip()
        ]
        merged_remote = [
            b.strip()
            for b in _git(repo, "branch", "-r", "--merged", "develop").splitlines()
            if b.strip() and "->" not in b
        ]
        linked = _worktree_branches(repo)
    except RuntimeError:
        return findings
    prune_local = [b for b in merged_local if b not in ("develop", "master") and b not in linked]
    members = []
    for branch in sorted(prune_local):
        try:
            stamp = _git(repo, "log", "-1", "--format=%ci", branch)
            age = _age_h(stamp.strip(), now)
        except RuntimeError:
            age = None
        if age is not None and age < 24:
            continue  # fresh pointer (e.g. just-spawned run branch); re-check next week
        members.append(_member(branch, branch, age))
    if members:
        findings.append(
            _finding(
                _aggregate_key("G1", members),
                "G1",
                f"Merged local branches to prune ({len(members)})",
                "agent",
                "Delete after verifying `git branch --merged develop` again.",
                members,
                max((m["age_h"] for m in members if m["age_h"] is not None), default=0.0),
            )
        )
    prune_remote = [
        b
        for b in merged_remote
        if b not in ("origin/develop", "origin/master", "origin/HEAD")
        and b.removeprefix("origin/") not in linked
    ]
    members = []
    for branch in sorted(prune_remote):
        try:
            stamp = _git(repo, "log", "-1", "--format=%ci", branch)
            age = _age_h(stamp.strip(), now)
        except RuntimeError:
            age = None
        if age is not None and age < 24:
            continue  # fresh pointer; re-check next week
        members.append(_member(branch, branch, age))
    if members:
        findings.append(
            _finding(
                _aggregate_key("G2", members),
                "G2",
                f"Merged remote branches to prune ({len(members)})",
                "agent",
                "Delete via `git push origin --delete` after re-verifying.",
                members,
                max((m["age_h"] for m in members if m["age_h"] is not None), default=0.0),
            )
        )
    try:
        spec = importlib.util.spec_from_file_location(
            "prune_run_worktrees", HERE / "prune-run-worktrees.py"
        )
        assert spec is not None and spec.loader is not None
        prune = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prune)
        candidates, _skipped = prune.collect_candidates(repo, runs_dir, older_than_days=7.0)
    except Exception:
        candidates = []
    if candidates:
        members = [
            _member(str(c.get("id", "?")), str(c.get("branch", "")), None, str(c.get("path", "")))
            for c in candidates
        ]
        findings.append(
            _finding(
                _aggregate_key("G3", members),
                "G3",
                f"Prunable run worktrees, 7d+ terminal ({len(members)})",
                "agent",
                "Review, then `scripts/prune-run-worktrees.py --apply`.",
                members,
                24 * 7.0,
            )
        )
    drift = _serve_drift(repo)
    if drift is not None:
        served, origin, age = drift
        members = [
            _member(
                served[:12],
                f"serve @ {served[:12]} vs origin @ {origin[:12]}",
                age,
            )
        ]
        findings.append(
            _finding(
                _aggregate_key("G4", members),
                "G4",
                "Serve tree lags origin/develop",
                "agent",
                "Let the supervisor tick redeploy, then verify serve-version.json.",
                members,
                age or 0.0,
            )
        )
    return findings


def _serve_drift(repo: Path) -> tuple[str, str, float | None] | None:
    """(served, origin, age_hours) when serve lags origin; else None.

    Fail-soft: a missing version file, unknown commits, or git trouble
    means no finding, never a crash.
    """
    try:
        version_file = repo / "apps" / "workbench_dashboard" / "data" / "serve-version.json"
        payload = json.loads(version_file.read_text(encoding="utf-8"))
        served = str(payload.get("commit", "") or "")
        origin = _git(repo, "rev-parse", "origin/develop").strip()
        if not served or not origin:
            return None
        if served == origin or origin.startswith(served) or served.startswith(origin):
            return None
        behind = subprocess.run(
            ["git", "merge-base", "--is-ancestor", served, origin],
            cwd=repo,
            capture_output=True,
            timeout=60,
        )
        if behind.returncode != 0:
            return None  # serve ahead or diverged: not drift
        try:
            serve_ts = int(_git(repo, "log", "-1", "--format=%ct", served))
            origin_ts = int(_git(repo, "log", "-1", "--format=%ct", origin))
            age: float | None = max(0.0, (origin_ts - serve_ts) / 3600.0)
        except RuntimeError:
            age = None
        return served, origin, age
    except (OSError, ValueError, RuntimeError):
        return None


def collect_plans(repo: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    plans_dir = repo / "docs" / "plans"
    unlinked: list[dict[str, Any]] = []
    if plans_dir.is_dir():
        for entry in sorted(plans_dir.iterdir()):
            if entry.suffix != ".md" or not entry.is_file():
                continue
            try:
                head = "".join(entry.read_text(encoding="utf-8").splitlines(True)[:8])
            except OSError:
                continue
            if "Project:" not in head:
                unlinked.append(_member(entry.name, entry.name, None))
    if unlinked:
        findings.append(
            _finding(
                _aggregate_key("P1", unlinked),
                "P1",
                f"Plans without a registry project header ({len(unlinked)})",
                "agent",
                "Add `<!-- Project: <id> | Status: ... -->` or archive the plan.",
                unlinked,
                0.0,
            )
        )
    registry_path = repo / "docs" / "goals" / "registry.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        projects = registry.get("projects", {})
    except (OSError, ValueError):
        return findings
    off_track = [
        _member(pid, pid, None, str(info.get("health", "")))
        for pid, info in sorted(projects.items())
        if isinstance(info, dict) and info.get("health") not in ("on-track", None)
    ]
    if off_track:
        findings.append(
            _finding(
                _aggregate_key("P2", off_track),
                "P2",
                f"Registry projects off on-track ({len(off_track)})",
                "agent",
                "Investigate each project and propose a concrete recovery "
                "(or re-scope); file the proposal for owner approval.",
                off_track,
                0.0,
            )
        )
    missing = [
        _member(pid, str(info.get("goal", "")), None)
        for pid, info in sorted(projects.items())
        if isinstance(info, dict) and info.get("goal") and not (repo / str(info["goal"])).exists()
    ]
    if missing:
        findings.append(
            _finding(
                _aggregate_key("P3", missing),
                "P3",
                f"Registry goal docs missing ({len(missing)})",
                "agent",
                "Restore or repoint the goal doc.",
                missing,
                0.0,
            )
        )
    return findings


def _env_names(env_path: Path) -> set[str]:
    """Configured variable names only; values are never read."""
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    names = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip().strip("'\"")
        if name:
            names.add(name)
    return names


def collect_stale_blockers(repo: Path) -> list[dict[str, Any]]:
    """Flag credential-blocker claims whose keys are already configured (P4).

    Matches "blocked on/waiting for account/keys/credentials" sentences in
    decisions + goal docs, then checks capitalized service tokens against
    .env variable NAMES (values never read). A match means the record is
    stale: correct it instead of repeating the claim.
    """
    import re

    claim_re = re.compile(
        r"[^.\n]{0,120}?(?:blocked on|waiting for|waits? for|needs?|requires?)\s+"
        r"[^.\n]{0,120}?(?:account creation|accounts?|api ?keys?|credentials?|secrets?)"
        r"[^.\n]{0,120}",
        re.IGNORECASE,
    )
    token_re = re.compile(r"\b([A-Z][a-zA-Z]{3,})\b")
    skip = {"Account", "Creation", "Keys", "Credentials", "Secrets", "Trial", "Vendor"}
    names = _env_names(repo / ".env")
    if not names:
        return []
    upper = {name.upper(): name for name in names}
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    docs = [repo / "docs" / "decisions.md", *(repo / "docs" / "goals").glob("*.md")]
    for path in sorted(docs):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        sections = re.split(r"(?m)^## ", text)
        for section in sections:
            if re.search(r"(?m)^Update \d{4}-\d{2}-\d{2}", section):
                continue  # reviewed record; the Update line carries the correction
            if not claim_re.search(section):
                continue
            for token in token_re.findall(section):
                if token in skip:
                    continue
                hit = next(
                    (orig for up, orig in upper.items() if token.upper() in up),
                    None,
                )
                if hit is None or (str(path), hit) in seen:
                    continue
                seen.add((str(path), hit))
                rel = path.relative_to(repo).as_posix()
                members.append(_member(f"{rel}:{hit}", f"{rel} claims blocker, {hit} set", None))
    if not members:
        return []
    keys = sorted({m["id"].split(":")[-1] for m in members})
    return [
        _finding(
            _aggregate_key("P4", members),
            "P4",
            f"Stale credential blockers ({len(members)}): {', '.join(keys)}",
            "agent",
            "Correct the record (accounts/keys exist); build the gated work instead of re-filing the block.",
            members,
            0.0,
        )
    ]


def collect_drafts(now: datetime) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    tmp = Path(tempfile.gettempdir())
    for entry in sorted(tmp.glob("e2e-draft-*.json")):
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC)
        except OSError:
            continue
        age_h = (now - mtime).total_seconds() / 3600.0
        if age_h >= 24 * 7:
            stale.append(_member(entry.name, entry.name, age_h))
    if not stale:
        return []
    return [
        _finding(
            _aggregate_key("D1", stale),
            "D1",
            f"Stale E2E draft files in TEMP ({len(stale)})",
            "agent",
            "Delete after confirming the tasks/reports landed.",
            stale,
            max(m["age_h"] for m in stale if m["age_h"] is not None),
        )
    ]


def _latest_receipt(out_dir: Path) -> dict[str, Any] | None:
    receipts = sorted(out_dir.glob("receipt-*.json"))
    if not receipts:
        return None
    try:
        return json.loads(receipts[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_file_brief() -> Any:
    spec = importlib.util.spec_from_file_location("file_brief", HERE / "file-brief.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_owner_gates(repo: Path) -> list[dict[str, Any]]:
    """Standing owner gates; missing/unreadable registry reads empty (fail-soft)."""
    try:
        payload = json.loads(
            (repo / "apps" / "workbench_dashboard" / "owner_gates.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return []
    gates = payload.get("gates") if isinstance(payload, dict) else None
    return [g for g in gates if isinstance(g, dict)] if isinstance(gates, list) else []


def _filing_body(finding: dict[str, Any], receipt_name: str) -> str:
    lines = [
        f"Forgotten-sweep finding {finding['key']} (gate {finding['gate_h']}h).",
        "",
        f"Suggested action: {finding['action']}",
        "",
    ]
    if finding.get("link"):
        lines += [f"Open: {finding['link']}", ""]
    lines.append("Members (up to 15):")
    for member in finding["members"][:15]:
        age = f"{member['age_h']}h" if member["age_h"] is not None else "age?"
        extra = f" — {member['extra']}" if member["extra"] else ""
        lines.append(f"- {member['id']} [{age}] {member['title']}{extra}")
    if len(finding["members"]) > 15:
        lines.append(f"- …and {len(finding['members']) - 15} more (see receipt).")
    lines += ["", f"Receipt: .tmp/forgotten-sweep/{receipt_name}"]
    return "\n".join(lines)


def run(
    *,
    data_dir: Path,
    out_dir: Path,
    repo: Path,
    file: bool = False,
    dry_run: bool = False,
    url: str = "http://127.0.0.1:8766",
    skip_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    now = _now()
    runs = _load_store(data_dir, "runs")
    inbox = _load_store(data_dir, "inbox")
    tasks = _load_store(data_dir, "e2e_tasks")
    reports = _load_store(data_dir, "e2e_reports")
    try:
        merged_branches = tuple(
            b.strip().lstrip("*+ ")
            for b in _git(repo, "branch", "--merged", "develop").splitlines()
            if b.strip()
        )
    except RuntimeError:
        merged_branches = ()
    findings: list[dict[str, Any]] = []
    run_findings, resolved = collect_runs(runs, inbox, now, merged_branches, repo)
    findings += run_findings
    findings += collect_inbox(inbox, now, runs, _load_owner_gates(repo))
    e2e_findings, e2e_resolved = collect_e2e(tasks, reports, runs, inbox, now)
    findings += e2e_findings
    resolved += e2e_resolved
    findings += collect_git(repo, data_dir / "runs", now)
    findings += collect_plans(repo)
    findings += collect_stale_blockers(repo)
    findings += collect_drafts(now)
    for finding in findings:
        if finding.get("link"):
            continue
        key = finding["key"]
        if key[:3] in ("R1:", "R2:", "R3:", "R4:"):
            finding["link"] = _dash_link("runs", key[3:])
        elif key[:3] in ("I1:", "I2:", "I3:", "I4:"):
            finding["link"] = _dash_link("inbox", key[3:])
    findings.sort(key=lambda f: (f["category"], f["key"]))

    previous = _latest_receipt(out_dir)
    filed_before: set[str] = set()
    if previous:
        filed_before = {f["key"] for f in previous.get("findings", []) if f.get("filed")}
    for finding in findings:
        finding["skipped"] = finding["key"] in skip_keys
    fileable = [
        f
        for f in findings
        if f["fileable"] and f["key"] not in filed_before and f["key"] not in skip_keys
    ]
    watching = [f for f in findings if not f["fileable"]]
    skipped_filed = [f for f in findings if f["fileable"] and f["key"] in filed_before]
    skipped_manual = [f for f in findings if f["fileable"] and f["key"] in skip_keys]

    stamp = now.strftime("%Y%m%d-%H%M%S")
    receipt_name = f"receipt-{stamp}.json"
    filed: dict[str, str] = {}
    file_errors: list[str] = []
    if file and fileable and not dry_run:
        brief = _load_file_brief()
        for finding in fileable:
            try:
                if finding.get("category") == "I5":
                    payload = brief.build_payload(
                        title=finding["title"],
                        body=finding.get("gate_body") or finding["title"],
                        options=finding.get("gate_options") or ["Done"],
                        item_type=finding.get("gate_type") or "decision",
                        created_by="supervisor",
                        assignee="owner",
                        metadata={"owner_gate": finding.get("gate_id")},
                    )
                else:
                    payload = brief.build_payload(
                        title=f"[sweep] {finding['title']}",
                        body=_filing_body(finding, receipt_name),
                        options=None,  # type: ignore[arg-type] - store defaults tasks to ["Done"]
                        item_type="task",
                        created_by="supervisor",
                        assignee=finding["assignee"],
                    )
                record = brief.send(url, payload)
                filed[finding["key"]] = str(record.get("id", "?"))
            except urllib.error.HTTPError as exc:
                try:
                    detail = exc.read().decode("utf-8", "replace")[:300]
                except Exception:  # noqa: BLE001 - fall back to status line
                    detail = str(exc)
                file_errors.append(f"{finding['key']}: HTTP {exc.code}: {detail}")
            except Exception as exc:  # noqa: BLE001 - record, keep sweeping
                file_errors.append(f"{finding['key']}: {exc}")
    for finding in findings:
        finding["filed"] = finding["key"] in filed or finding["key"] in filed_before
        if finding["key"] in filed:
            finding["inbox_id"] = filed[finding["key"]]
    receipt = {
        "stamp_utc": now.isoformat(),
        "counts": {
            "runs": len(runs),
            "inbox": len(inbox),
            "e2e_tasks": len(tasks),
            "e2e_reports": len(reports),
            "findings": len(findings),
            "fileable_new": len(fileable),
            "watching": len(watching),
            "already_filed": len(skipped_filed),
            "skipped_manual": len(skipped_manual),
            "resolved_skipped": len(resolved),
            "file_errors": len(file_errors),
        },
        "findings": findings,
        "resolved_skipped": resolved,
        "file_errors": file_errors,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / receipt_name).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    receipt["receipt"] = receipt_name
    receipt["dry_run"] = dry_run and file
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forgotten-items sweep.")
    parser.add_argument(
        "--data-dir", type=Path, default=ROOT / "apps" / "workbench_dashboard" / "data"
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / ".tmp" / "forgotten-sweep")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--file", action="store_true", help="File new findings as inbox tasks.")
    parser.add_argument("--dry-run", action="store_true", help="With --file: print, do not POST.")
    parser.add_argument(
        "--skip-keys", default="", help="Comma-separated finding keys to never file."
    )
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args(argv)
    skip = frozenset(k.strip() for k in args.skip_keys.split(",") if k.strip())
    try:
        receipt = run(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            repo=args.repo,
            file=args.file,
            dry_run=args.dry_run,
            url=args.url,
            skip_keys=skip,
        )
    except Exception as exc:  # noqa: BLE001 - top-level guard with receipt attempt
        print(f"sweep failed: {exc}", file=sys.stderr)
        return 1
    counts = receipt["counts"]
    print(
        f"sweep: findings={counts['findings']} fileable_new={counts['fileable_new']} "
        f"watching={counts['watching']} already_filed={counts['already_filed']} "
        f"skipped={counts['skipped_manual']} resolved={counts['resolved_skipped']} "
        f"file_errors={counts['file_errors']} receipt={receipt['receipt']}"
    )
    for finding in receipt["findings"]:
        if finding.get("skipped"):
            state = "skip"
        else:
            state = (
                "FILE"
                if finding["fileable"] and not finding["filed"]
                else ("filed" if finding["filed"] else "watch")
            )
        strage = f"{finding['max_age_h']}h" if finding["max_age_h"] is not None else "?"
        print(
            f"  [{state}] {finding['key']} age={strage} members={len(finding['members'])} {finding['title']}"
        )
    if receipt["dry_run"]:
        print("(dry run: nothing filed)")
    return 1 if counts["file_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
