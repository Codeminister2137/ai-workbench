"""Supervisor follow-up guarantee: retries, drift self-audit, chain reports.

Supervisor evolution (ADR-090 extension): the supervisor owns follow-up
issuance end to end. Event-time issuance lives in the stores/drain paths;
this module holds the tick-time self-audit (retry refused filings, detect
orphans) and chain-end report finalization. No new processes or tabs.

Metadata link keys (frozen contracts shared with battery arms T1/T5):
``triage_for`` (run id), ``elaboration_for`` (idea id), ``closeout_for``
(inbox source id), ``chain_report_for`` (inbox source id).
"""

from __future__ import annotations

from typing import Any

from dashboard_stores import StoreError

TRIAGE_KEY = "triage_for"
ELABORATION_KEY = "elaboration_for"
CLOSEOUT_KEY = "closeout_for"
CHAIN_REPORT_KEY = "chain_report_for"


def _open_link_exists(stores: Any, key: str, target: str) -> bool:
    items, _total = stores.inbox.list(limit=1000)
    return any(
        isinstance(item, dict)
        and item.get("status") == "open"
        and str((item.get("metadata") or {}).get(key, "")) == target
        for item in items
    )


def retry_pending_followups(stores: Any) -> dict[str, int]:
    """Re-attempt cap-refused filings; returns healed counts by kind."""
    healed = {"closeout": 0, "e2e_followup": 0, "chain_report": 0}
    items, _total = stores.inbox.list(limit=1000)
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            if item.get("closeout_pending") and stores.retry_closeout(item):
                healed["closeout"] += 1
        except Exception:  # noqa: BLE001 - audit heals what it can
            continue
        try:
            if item.get("report_pending"):
                outcome = finalize_chain_report(stores, str(item.get("id")))
                if outcome.get("action") == "filed":
                    healed["chain_report"] += 1
        except Exception:  # noqa: BLE001 - audit heals what it can
            continue
    try:
        tasks, _total = stores.e2e_tasks.list(limit=1000)
    except Exception:  # noqa: BLE001 - audit heals what it can
        tasks = []
    for task in tasks:
        if not isinstance(task, dict) or not task.get("followup_error"):
            continue
        try:
            if stores.retry_e2e_followup(str(task.get("id"))):
                healed["e2e_followup"] += 1
        except Exception:  # noqa: BLE001 - audit heals what it can
            continue
    return healed


def find_followup_orphans(stores: Any) -> list[dict[str, Any]]:
    """Terminal records whose follow-up was never issued nor flagged.

    Detection only; the tick audit heals refused filings while orphans
    surface here (and failed-run orphans surface as probe dead-ends).
    """
    orphans: list[dict[str, Any]] = []
    items, _total = stores.inbox.list(limit=1000)
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        if (
            item.get("status") == "answered"
            and not metadata.get("closeout_id")
            and not item.get("closeout_pending")
        ):
            orphans.append(
                {"kind": "answered-no-closeout", "id": item.get("id"), "title": item.get("title")}
            )
    try:
        runs, _total = stores.runs.list(limit=1000)
    except Exception:  # noqa: BLE001 - audit detects what it can
        runs = []
    for run in runs:
        if not isinstance(run, dict) or run.get("status") != "failed":
            continue
        run_id = str(run.get("id") or "")
        if not run_id or _open_link_exists(stores, TRIAGE_KEY, run_id):
            continue
        source_id = run.get("bridged_from") or run.get("inbox_id")
        source = stores.inbox.get(str(source_id)) if source_id else None
        if isinstance(source, dict) and source.get("status") == "open":
            continue  # live thread: the open source tracks this failure
        orphans.append({"kind": "failed-no-triage", "id": run_id, "title": run.get("title")})
    try:
        ideas, _total = stores.ideas.list(limit=1000)
    except Exception:  # noqa: BLE001 - audit detects what it can
        ideas = []
    for idea in ideas:
        if not isinstance(idea, dict) or idea.get("status") != "adopted":
            continue
        idea_id = str(idea.get("id") or "")
        if not idea_id or idea.get("elaboration_pending"):
            continue
        if _open_link_exists(stores, ELABORATION_KEY, idea_id):
            continue
        orphans.append(
            {"kind": "adopted-no-elaboration", "id": idea_id, "title": idea.get("title")}
        )
    return orphans


def supervisor_tick_audit(stores: Any) -> dict[str, Any]:
    """One drift self-check: heal refused filings, report orphans."""
    healed = retry_pending_followups(stores)
    orphans = find_followup_orphans(stores)
    return {"healed": healed, "orphans": orphans}


def _chain_members(stores: Any, source_id: str) -> tuple[dict | None, dict | None, list]:
    items, _total = stores.inbox.list(limit=1000)
    source = None
    closeout = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("id") == source_id:
            source = item
        elif str((item.get("metadata") or {}).get(CLOSEOUT_KEY, "")) == source_id:
            closeout = item
    runs: list = []
    try:
        all_runs, _total = stores.runs.list(limit=1000)
    except Exception:  # noqa: BLE001 - reports cite what exists
        all_runs = []
    want = {source_id, (closeout or {}).get("id")}
    for run in all_runs:
        if not isinstance(run, dict):
            continue
        if run.get("bridged_from") in want or run.get("inbox_id") in want:
            runs.append(run)
    return source, closeout, runs


def _report_body(source: dict, closeout: dict | None, runs: list) -> str:
    lines = [
        "## Initial",
        f"Source: {source.get('title')} ({source.get('id')})",
        f"Answer: {source.get('answer') or '(none)'}",
        "",
        "## Evolution",
    ]
    if closeout is not None:
        lines.append(f"Close-out: {closeout.get('title')} ({closeout.get('id')})")
        lines.append(f"Resolution: {(closeout.get('resolution') or '')[:1000]}")
    else:
        lines.append("Close-out: (none filed)")
    lines += ["", "## Achieved"]
    if source.get("resolution"):
        lines.append(f"Source resolution: {(source.get('resolution') or '')[:1000]}")
    else:
        lines.append("Source resolution: (source still open)")
    lines += ["", "## Links"]
    refs = list(source.get("context_refs") or [])
    if closeout is not None:
        refs += list(closeout.get("context_refs") or [])
    for ref in refs:
        lines.append(f"- {ref}")
    for run in runs:
        lines.append(f"- run:{run.get('id')} ({run.get('status')})")
    return "\n".join(lines).strip()


def finalize_chain_report(stores: Any, source_id: str) -> dict[str, Any]:
    """File the supervisor chain-end report for one source (deduped).

    Composes initial + evolution + achieved + links from closed records;
    files nothing twice and never raises. A cap refusal flags
    ``report_pending`` on the source for the tick audit to retry.
    """
    try:
        items, _total = stores.inbox.list(limit=1000)
        for item in items:
            if (
                isinstance(item, dict)
                and str((item.get("metadata") or {}).get(CHAIN_REPORT_KEY, "")) == source_id
            ):
                return {"action": "skipped", "reason": "report exists", "id": item.get("id")}
        source, closeout, runs = _chain_members(stores, source_id)
        if source is None:
            return {"action": "skipped", "reason": "source gone"}
        report = stores.create_inbox_task(
            title=f"Chain report: {str(source.get('title') or source_id)[:70]}",
            body=_report_body(source, closeout, runs),
            task_type="report",
            created_by="supervisor",
            assignee="owner",
            project_id=str(source.get("project_id") or stores.default_project_id()),
            metadata={CHAIN_REPORT_KEY: source_id},
            context_refs=[f"inbox:{source_id}"],
        )
        source.pop("report_pending", None)
        stores.inbox.put(source["id"], source)
        return {"action": "filed", "id": report["id"]}
    except StoreError as exc:
        if "open inbox tasks" not in str(exc):
            return {"action": "skipped", "reason": f"StoreError: {exc}"[:200]}
        try:
            source = stores.inbox.get(source_id)
            if source is not None:
                source["report_pending"] = True
                stores.inbox.put(source_id, source)
        except Exception:  # noqa: BLE001 - flagging never raises
            pass
        return {"action": "skipped", "reason": "cap refused; flagged"}
    except Exception as exc:  # noqa: BLE001 - finalization never raises
        return {"action": "skipped", "reason": f"{type(exc).__name__}: {exc}"[:200]}
