"""Supervisor follow-up guarantee: one test per trigger plus chain reports."""

from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores, StoreError
from supervisor_followups import (
    finalize_chain_report,
    find_followup_orphans,
    supervisor_tick_audit,
)


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def _e2e_items() -> list[dict]:
    return [
        {
            "id": "behavior:dashboard",
            "kind": "behavior",
            "area": "dashboard",
            "behavior": "dashboard views and actions",
            "files": ["apps/workbench_dashboard/web/app.js"],
            "goals": ["docs/goals/dashboard.md"],
            "status": "pending",
        }
    ]


def test_answer_issues_closeout_synchronously(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    stores.answer_inbox_task(record["id"], answer="A")
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    closeout = stores.inbox.get((stored.get("metadata") or {}).get("closeout_id"))
    assert closeout is not None
    assert closeout["status"] == "open" and closeout["assignee"] == "agent"
    assert (closeout.get("metadata") or {}).get("closeout_for") == record["id"]


def test_closeout_pending_retry_heals_on_audit(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    for num in range(49):  # cap the inbox: 1 source + 49 fillers
        stores.create_inbox_task(title=f"filler {num}", body="b", task_type="task")
    stores.answer_inbox_task(record["id"], answer="A")
    stored = stores.inbox.get(record["id"])
    assert stored is not None and stored.get("closeout_pending") is True
    assert "closeout_id" not in (stored.get("metadata") or {})
    # Free one slot, then the tick audit heals the refused filing.
    fillers, _ = stores.inbox.list(limit=100)
    victim = next(i for i in fillers if (i.get("title") or "").startswith("filler"))
    stores.close_inbox_task(victim["id"], resolution="room")
    audit = supervisor_tick_audit(stores)
    assert audit["healed"]["closeout"] == 1
    healed = stores.inbox.get(record["id"])
    assert healed is not None and "closeout_pending" not in healed
    assert (healed.get("metadata") or {}).get("closeout_id")


def test_agent_close_reports_back_to_source(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    stores.answer_inbox_task(record["id"], answer="A")
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    closeout_id = (stored.get("metadata") or {}).get("closeout_id")
    assert closeout_id
    stores.close_inbox_task(closeout_id, resolution="implemented A")
    source = stores.inbox.get(record["id"])
    assert source is not None
    assert f"closeout:{closeout_id}" in (source.get("note") or "")
    assert "implemented A" in (source.get("note") or "")


def test_e2e_verdict_files_followup_immediately(stores) -> None:
    task = stores.create_e2e_task(merge_commit="abc", title="t", items=_e2e_items())
    outcome = stores.submit_e2e_task(
        task["id"], [{"item_id": "behavior:dashboard", "verdict": "fail", "notes": "x"}]
    )
    assert outcome["followup_id"]
    followup = stores.inbox.get(outcome["followup_id"])
    assert followup is not None and followup["status"] == "open"


def test_e2e_followup_refusal_retries_on_audit(stores) -> None:
    for num in range(50):
        stores.create_inbox_task(title=f"filler {num}", body="b", task_type="task")
    task = stores.create_e2e_task(merge_commit="abc", title="t", items=_e2e_items())
    outcome = stores.submit_e2e_task(
        task["id"], [{"item_id": "behavior:dashboard", "verdict": "fail", "notes": "x"}]
    )
    assert outcome["followup_id"] is None
    fillers, _ = stores.inbox.list(limit=100)
    victim = next(i for i in fillers if (i.get("title") or "").startswith("filler"))
    stores.close_inbox_task(victim["id"], resolution="room")
    audit = supervisor_tick_audit(stores)
    assert audit["healed"]["e2e_followup"] == 1
    healed = stores.e2e_tasks.get(task["id"])
    assert healed is not None and "followup_error" not in healed


def test_orphan_answered_without_closeout_is_detected(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    stored["status"] = "answered"  # answered with no close-out ever queued
    stored.pop("closeout_pending", None)
    stores.inbox.put(record["id"], stored)
    orphans = find_followup_orphans(stores)
    assert [o for o in orphans if o["kind"] == "answered-no-closeout" and o["id"] == record["id"]]


def test_orphan_failed_run_without_triage_is_detected(stores) -> None:
    stores.runs.put("run-1", {"id": "run-1", "title": "r", "status": "failed"})
    orphans = find_followup_orphans(stores)
    assert [o for o in orphans if o["kind"] == "failed-no-triage" and o["id"] == "run-1"]


def test_failed_run_with_open_source_is_not_orphaned(stores) -> None:
    source = stores.create_inbox_task(title="work", body="b", task_type="task", assignee="agent")
    stores.runs.put(
        "run-1",
        {"id": "run-1", "title": "r", "status": "failed", "bridged_from": source["id"]},
    )
    orphans = find_followup_orphans(stores)
    assert not [o for o in orphans if o["id"] == "run-1"]


def test_orphan_adopted_idea_without_elaboration_is_detected(stores) -> None:
    idea = stores.create_idea(title="i", body="b", source="owner")
    stores.set_idea_status(idea["id"], status="adopted", decision="go")
    items, _ = stores.inbox.list(limit=100)  # simulate issuance ever missed
    for item in items:
        if (item.get("metadata") or {}).get("elaboration_for") == idea["id"]:
            stores.inbox.delete(item["id"])
    orphans = find_followup_orphans(stores)
    assert [o for o in orphans if o["kind"] == "adopted-no-elaboration" and o["id"] == idea["id"]]


def test_finalize_files_chain_report_with_sections(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    stores.answer_inbox_task(record["id"], answer="A")
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    closeout_id = (stored.get("metadata") or {}).get("closeout_id")
    assert closeout_id
    stores.runs.put(
        "run-1",
        {"id": "run-1", "title": "r", "status": "completed", "bridged_from": closeout_id},
    )
    stores.close_inbox_task(closeout_id, resolution="did A")
    stores.close_inbox_task(record["id"], resolution="A implemented")
    items, _ = stores.inbox.list(limit=100)
    reports = [i for i in items if i.get("type") == "report"]
    assert len(reports) == 1
    body = reports[0].get("body") or ""
    for section in (
        "## What was asked",
        "## What happened",
        "## What was achieved",
        "## Runs in this chain",
        "## Where to look",
    ):
        assert section in body
    assert "run:run-1: finished successfully (status completed)." in body
    assert f"inbox:{record['id']}" in body
    assert "did A" in body and "A implemented" in body  # quotes stay verbatim
    assert (reports[0].get("metadata") or {}).get("chain_report_for") == record["id"]


def test_report_body_explains_empty_chain(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    filed = finalize_chain_report(stores, record["id"])
    assert filed["action"] == "filed"
    stored = stores.inbox.get(filed["id"])
    assert stored is not None
    body = stored.get("body") or ""
    assert "Owner answer: (no answer recorded)." in body
    assert "No close-out brief was filed for this chain." in body
    assert "nothing is confirmed achieved yet" in body
    assert "No runs were linked to this chain." in body


def test_claim_defers_closeout_until_release(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    claimed = stores.claim_inbox_task(record["id"], by="loop-20261120")
    assert (claimed.get("metadata") or {}).get("claimed_by") == "loop-20261120"
    stores.answer_inbox_task(record["id"], answer="A")
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    assert stored.get("status") == "answered"
    assert (stored.get("metadata") or {}).get("closeout_id") is None
    assert stored.get("closeout_pending") is True
    assert stores.retry_closeout(stored) is False
    released = stores.claim_inbox_task(record["id"], by=None)
    assert (released.get("metadata") or {}).get("claimed_by") is None
    assert (released.get("metadata") or {}).get("closeout_id")
    assert released.get("closeout_pending") is not True


def test_claim_missing_item_raises(stores) -> None:
    with pytest.raises(StoreError):
        stores.claim_inbox_task("nope", by="loop-x")


def test_finalize_dedupes_and_flags_cap(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    other = stores.create_inbox_task(
        title="Q2?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    first = finalize_chain_report(stores, record["id"])
    assert first["action"] == "filed"
    second = finalize_chain_report(stores, record["id"])
    assert second["action"] == "skipped" and second["id"] == first["id"]
    for num in range(47):  # cap the inbox: 2 sources + 1 report + 47
        stores.create_inbox_task(title=f"filler {num}", body="b", task_type="task")
    capped = finalize_chain_report(stores, other["id"])
    assert capped["action"] == "skipped"
    flagged = stores.inbox.get(other["id"])
    assert flagged is not None and flagged.get("report_pending") is True
    fillers, _ = stores.inbox.list(limit=100)
    victim = next(i for i in fillers if (i.get("title") or "").startswith("filler"))
    stores.close_inbox_task(victim["id"], resolution="room")
    audit = supervisor_tick_audit(stores)
    assert audit["healed"]["chain_report"] == 1


def test_acknowledge_archives_report_out_of_badge(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    filed = finalize_chain_report(stores, record["id"])
    assert filed["action"] == "filed"
    assert stores.attention_inbox_count() == 2  # source + unacknowledged report
    acked = stores.acknowledge_report(filed["id"])
    assert acked["status"] == "closed" and acked["acknowledged"] is True
    assert stores.attention_inbox_count() == 1
    with pytest.raises(StoreError):
        stores.acknowledge_report(filed["id"])


def test_reports_reject_answer_and_close(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    filed = finalize_chain_report(stores, record["id"])
    assert filed["action"] == "filed"
    with pytest.raises(StoreError):
        stores.answer_inbox_task(filed["id"], answer="x")
    with pytest.raises(StoreError):
        stores.close_inbox_task(filed["id"], resolution="x")


def test_report_creation_is_supervisor_only(stores) -> None:
    with pytest.raises(StoreError):
        stores.create_inbox_task(
            title="fake",
            body="b",
            task_type="report",
            created_by="agent",
            assignee="owner",
        )
    with pytest.raises(StoreError):
        stores.create_inbox_task(
            title="fake",
            body="b",
            task_type="report",
            created_by="supervisor",
            assignee="agent",
        )


def test_supersede_appends_link_only(stores) -> None:
    first_src = stores.create_inbox_task(
        title="Q1?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    second_src = stores.create_inbox_task(
        title="Q2?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    first = finalize_chain_report(stores, first_src["id"])
    second = finalize_chain_report(stores, second_src["id"])
    assert first["action"] == "filed" and second["action"] == "filed"
    with pytest.raises(StoreError):  # open reports take no supersede links
        stores.supersede_report(first["id"], by_id=second["id"])
    stores.acknowledge_report(first["id"])
    stores.supersede_report(first["id"], by_id=second["id"])
    stored = stores.inbox.get(first["id"])
    assert stored is not None
    assert (stored.get("metadata") or {}).get("supersede_links") == [second["id"]]
    assert f"Superseded by report {second['id']}." in (stored.get("body") or "")
    with pytest.raises(StoreError):  # target must be a report
        stores.supersede_report(first["id"], by_id=first_src["id"])


def test_reopen_is_the_owner_override_for_reports(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick?", body="b", task_type="decision", options=["A"], assignee="owner"
    )
    filed = finalize_chain_report(stores, record["id"])
    assert filed["action"] == "filed"
    stores.acknowledge_report(filed["id"])
    reopened = stores.reopen_inbox_task(filed["id"])
    assert reopened["status"] == "open"
