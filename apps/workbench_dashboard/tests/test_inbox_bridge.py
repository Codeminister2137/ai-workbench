"""Inbox-to-run bridge: agent tasks become approval-gated runs."""

from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import post_json, serve_dashboard
from inbox_bridge import bridge_agent_queue


@pytest.fixture
def server(tmp_path):
    with serve_dashboard(tmp_path) as server:
        yield server


def _agent_task(stores, **overrides):
    payload = {
        "title": "Do the thing",
        "body": "Details here.",
        "task_type": "task",
        "created_by": "owner",
        "assignee": "agent",
    }
    payload.update(overrides)
    return stores.create_inbox_task(**payload)


def test_timeout_override_flows_to_run(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    _agent_task(stores, created_by="supervisor", metadata={"mai_timeout_seconds": 1200})
    (receipt,) = bridge_agent_queue(stores)
    assert stores.runs.get(receipt["run_id"])["mai_timeout_seconds"] == 1200
    _agent_task(stores, created_by="supervisor", metadata={"mai_timeout_seconds": "soon"})
    assert "mai_timeout_seconds" not in stores.runs.get(bridge_agent_queue(stores)[0]["run_id"])


def test_supervisor_filed_task_is_preapproved_as_agent_queue(tmp_path) -> None:
    """Owner decision C: every bridged task pre-approved, provenance kept."""
    stores = DashboardStores(tmp_path)
    item = _agent_task(stores, created_by="supervisor")
    (receipt,) = bridge_agent_queue(stores)
    assert receipt["inbox_id"] == item["id"]
    assert receipt["status"] == "preapproved"
    assert receipt["approval_id"] is None
    run = stores.runs.get(receipt["run_id"])
    assert run is not None
    assert run["status"] == "queued"
    assert run["origin"] == "inbox"
    assert run["inbox_id"] is None
    assert run["approval_mode"] == "agent-queue"
    approvals, _ = stores.inbox.list(limit=10)
    assert [i for i in approvals if i["title"].startswith("Approve agent run:")] == []
    marked = stores.inbox.get(item["id"])
    assert marked is not None
    assert marked["metadata"]["bridge_run_id"] == receipt["run_id"]
    # Second pass proposes nothing new.
    assert bridge_agent_queue(stores) == []


def test_resolve_bridge_fanout_coerces_and_fails_closed() -> None:
    from inbox_bridge import resolve_bridge_fanout

    assert resolve_bridge_fanout("allowed") == "allowed"
    assert resolve_bridge_fanout("denied") == "denied"
    assert resolve_bridge_fanout(None) == "restricted"
    assert resolve_bridge_fanout("sometimes") == "restricted"


def test_bridge_uses_configured_fanout_policy(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    _agent_task(stores, created_by="supervisor")
    (receipt,) = bridge_agent_queue(stores, fanout_policy="allowed")
    run = stores.runs.get(receipt["run_id"])
    assert run is not None
    assert run["fanout_policy"] == "allowed"
    assert run["fanout_effective"] == "allowed"


def test_e2e_followup_is_preapproved_without_approval(tmp_path) -> None:
    """E2E follow-ups skip owner approval: agent acts, owner re-tests (owner decision 2026-11-16)."""
    stores = DashboardStores(tmp_path)
    item = _agent_task(
        stores,
        created_by="supervisor",
        metadata={"kind": "e2e-followup", "merge_commit": "abc123"},
    )
    (receipt,) = bridge_agent_queue(stores)
    assert receipt["inbox_id"] == item["id"]
    assert receipt["status"] == "preapproved"
    assert receipt["approval_id"] is None
    run = stores.runs.get(receipt["run_id"])
    assert run is not None
    assert run["status"] == "queued"
    assert run["approval_mode"] == "e2e-followup"
    assert run["inbox_id"] is None
    approvals, _ = stores.inbox.list(limit=10)
    assert [i for i in approvals if i["title"].startswith("Approve agent run:")] == []
    assert bridge_agent_queue(stores) == []


def test_owner_filed_task_is_preapproved_without_approval(tmp_path) -> None:
    """Filing is approval: owner-created tasks skip the self-approval decision."""
    stores = DashboardStores(tmp_path)
    item = _agent_task(stores, created_by="owner")
    (receipt,) = bridge_agent_queue(stores)
    assert receipt["inbox_id"] == item["id"]
    assert receipt["status"] == "preapproved"
    assert receipt["approval_id"] is None
    run = stores.runs.get(receipt["run_id"])
    assert run is not None
    assert run["status"] == "queued"
    assert run["approval_mode"] == "owner-filed"
    assert run["inbox_id"] is None
    approvals, _ = stores.inbox.list(limit=10)
    assert [i for i in approvals if i["title"].startswith("Approve agent run:")] == []
    assert bridge_agent_queue(stores) == []


def test_skips_decisions_closed_and_foreign_items(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    _agent_task(stores, task_type="decision", options=["A", "B"])
    _agent_task(stores, title="Owner job", assignee="owner")
    assert bridge_agent_queue(stores) == []


def test_endpoint_bridges_and_reports(server) -> None:
    base, _tmp = server
    result = post_json(base, "/api/inbox/bridge-runs", {})
    assert result["ok"] is True
    assert result["bridged"] == []
