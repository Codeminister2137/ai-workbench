"""Inbox-to-run bridge: agent tasks become approval-gated runs."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import post_json
from dashboard_web_app import DashboardRequestHandler
from inbox_bridge import bridge_agent_queue


@pytest.fixture
def server(tmp_path):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path
    finally:
        server.shutdown()
        server.server_close()


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


def test_supervisor_filed_task_keeps_approval_gate(tmp_path) -> None:
    stores = DashboardStores(tmp_path)
    item = _agent_task(stores, created_by="supervisor")
    (receipt,) = bridge_agent_queue(stores)
    assert receipt["inbox_id"] == item["id"]
    assert receipt["status"] == "proposed"
    run = stores.runs.get(receipt["run_id"])
    assert run is not None
    assert run["status"] == "queued"
    assert run["origin"] == "inbox"
    assert run["inbox_id"] == receipt["approval_id"]
    approval = stores.inbox.get(receipt["approval_id"])
    assert approval is not None
    assert approval["options"] == ["Approve", "Reject"]
    marked = stores.inbox.get(item["id"])
    assert marked is not None
    assert marked["metadata"]["bridge_run_id"] == receipt["run_id"]
    # Second pass proposes nothing new.
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
