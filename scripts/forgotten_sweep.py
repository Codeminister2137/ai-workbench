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
    "I1": 24,  # answered-never-closed inbox
    "I2": 48,  # open agent inbox rotting
    "I3": 168,  # open owner inbox backlog (7d)
    "E1": 24,  # fail E2E report, no follow-up action
    "E2": 24,  # fail E2E report, follow-up itself failed
    "E3": 48,  # open E2E task (owner testing backlog)
    "G1": 0,  # merged local branches (housekeeping; always actionable)
    "G2": 0,  # merged remote branches
    "G3": 0,  # prunable run worktrees (7d+ terminal, via prune script)
    "P1": 0,  # plans without registry project header
    "P2": 0,  # registry projects off on-track
    "P3": 0,  # registry goal docs missing
    "D1": 0,  # stale TEMP E2E drafts (7d+)
}

SHORT_RE = re.compile(r"[0-9a-f]{7,40}")
FOLLOWUP_RE = re.compile(r"E2E follow-up:\s*([0-9a-f]{7,40})", re.IGNORECASE)


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
    }


def _member(record_id: str, title: str, age_h: float | None, extra: str = "") -> dict[str, Any]:
    return {
        "id": record_id,
        "title": title[:100],
        "age_h": round(age_h, 1) if age_h is not None else None,
        "extra": extra[:140],
    }


def collect_runs(
    runs: list[dict[str, Any]], inbox: list[dict[str, Any]], now: datetime
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    by_inbox: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        if run.get("inbox_id"):
            by_inbox.setdefault(str(run["inbox_id"]), []).append(run)
    open_refs: list[str] = []
    for item in inbox:
        if item.get("status") in ("open", "answered"):
            open_refs.append(
                f"{item.get('title', '')} {item.get('body', '')} "
                f"{item.get('resolution', '')} {item.get('note', '')}".lower()
            )
    for run in runs:
        rid = str(run.get("id", "?"))
        title = str(run.get("title", ""))
        status = str(run.get("status", ""))
        created = _record_ts(run)
        age = _age_h(created, now)
        if age is None:
            continue
        if status == "failed":
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
                continue  # superseded or already queued
            findings.append(
                _finding(
                    f"R1:{rid}",
                    "R1",
                    f"Failed run with no follow-up: {title[:70]}",
                    "agent",
                    "Investigate the error; queue a fix run or close with a note.",
                    [_member(rid, title, age, str(run.get("error", "")))],
                    age,
                )
            )
        elif status in IDLE_RUN:
            findings.append(
                _finding(
                    f"R2:{rid}",
                    "R2",
                    f"Idle {status} run: {title[:70]}",
                    "agent",
                    "Drain it, requeue it, or cancel with a note.",
                    [_member(rid, title, age)],
                    age,
                )
            )
        elif status == "branch-ready":
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
    return findings


def collect_inbox(inbox: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
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
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    followups = _followup_shorts(runs, inbox)
    for task in tasks:
        if str(task.get("status", "")) == "submitted":
            continue
        tid = str(task.get("id", "?"))
        title = str(task.get("title", ""))
        age = _age_h(_record_ts(task), now)
        if age is None:
            continue
        findings.append(
            _finding(
                f"E3:{tid}",
                "E3",
                f"Open E2E task (owner testing): {title[:70]}",
                "owner",
                "Run the checklist and submit, or close as superseded.",
                [_member(tid, title, age)],
                age,
            )
        )
    for report in reports:
        if str(report.get("overall", "")) in ("pass", "passed"):
            continue
        rid = str(report.get("id", "?"))
        title = str(report.get("title", ""))
        age = _age_h(_record_ts(report), now)
        if age is None:
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
    return findings


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
    if prune_local:
        members = []
        for branch in sorted(prune_local):
            try:
                stamp = _git(repo, "log", "-1", "--format=%ci", branch)
                age = _age_h(stamp.strip(), now)
            except RuntimeError:
                age = None
            members.append(_member(branch, branch, age))
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
    if prune_remote:
        members = [_member(b, b, None) for b in sorted(prune_remote)]
        findings.append(
            _finding(
                _aggregate_key("G2", members),
                "G2",
                f"Merged remote branches to prune ({len(members)})",
                "agent",
                "Delete via `git push origin --delete` after re-verifying.",
                members,
                0.0,
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
    return findings


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
                "owner",
                "Review health; update the registry or queue recovery work.",
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


def _filing_body(finding: dict[str, Any], receipt_name: str) -> str:
    lines = [
        f"Forgotten-sweep finding {finding['key']} (gate {finding['gate_h']}h).",
        "",
        f"Suggested action: {finding['action']}",
        "",
        "Members (up to 15):",
    ]
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
    findings: list[dict[str, Any]] = []
    findings += collect_runs(runs, inbox, now)
    findings += collect_inbox(inbox, now)
    findings += collect_e2e(tasks, reports, runs, inbox, now)
    findings += collect_git(repo, data_dir / "runs", now)
    findings += collect_plans(repo)
    findings += collect_drafts(now)
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
            payload = brief.build_payload(
                title=f"[sweep] {finding['title']}",
                body=_filing_body(finding, receipt_name),
                options=None,  # type: ignore[arg-type] - store defaults tasks to ["Done"]
                item_type="task",
                created_by="supervisor",
                assignee=finding["assignee"],
            )
            try:
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
            "file_errors": len(file_errors),
        },
        "findings": findings,
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
        f"skipped={counts['skipped_manual']} file_errors={counts['file_errors']} "
        f"receipt={receipt['receipt']}"
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
