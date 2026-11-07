"""Owner->AI agent queue: direction fields, FIFO listing, API filter, UI hooks."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores, StoreError
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@pytest.fixture
def queue_server(tmp_path):
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


def test_create_defaults_to_supervisor_owner(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    record = stores.create_inbox_task(title="T", body="b", task_type="task")
    assert record["created_by"] == "supervisor"
    assert record["assignee"] == "owner"


def test_create_owner_to_agent_direction(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    record = stores.create_inbox_task(
        title="T", body="b", task_type="task", created_by="owner", assignee="agent"
    )
    assert record["created_by"] == "owner"
    assert record["assignee"] == "agent"


def test_create_rejects_unknown_party(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    with pytest.raises(StoreError, match="creator"):
        stores.create_inbox_task(title="T", body="b", task_type="task", created_by="stranger")
    with pytest.raises(StoreError, match="assignee"):
        stores.create_inbox_task(title="T", body="b", task_type="task", assignee="crowd")


def test_agent_queue_fifo_open_only(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    first = stores.create_inbox_task(
        title="First", body="b", task_type="task", created_by="owner", assignee="agent"
    )
    second = stores.create_inbox_task(
        title="Second", body="b", task_type="task", created_by="owner", assignee="agent"
    )
    stores.create_inbox_task(title="Mine", body="b", task_type="task")
    # Force distinct stamps so FIFO order is deterministic.
    for record, stamp in (
        (first, "2026-11-06T10:00:00+00:00"),
        (second, "2026-11-06T11:00:00+00:00"),
    ):
        stored = stores.inbox.get(record["id"])
        assert stored is not None
        stored["created_at"] = stamp
        stores.inbox.put(record["id"], stored)
    stores.close_inbox_task(first["id"], resolution="Done by agent.")
    queue = stores.agent_queue()
    assert [item["id"] for item in queue] == [second["id"]]
    stores.reopen_inbox_task(first["id"])
    queue = stores.agent_queue()
    assert [item["id"] for item in queue] == [first["id"], second["id"]]


def test_post_accepts_owner_agent_direction(queue_server) -> None:
    base, _tmp_path = queue_server
    created = post_json(
        base,
        "/api/inbox",
        {
            "title": "Refactor planner",
            "body": "Split run_tracking.",
            "type": "task",
            "created_by": "owner",
            "assignee": "agent",
        },
    )
    assert created["ok"] is True
    item = get_json(base, f"/api/inbox/{created['id']}")
    assert item["item"]["created_by"] == "owner"
    assert item["item"]["assignee"] == "agent"


def test_post_rejects_bad_assignee(queue_server) -> None:
    base, _tmp_path = queue_server
    with pytest.raises(HTTPError) as raised:
        post_json(
            base,
            "/api/inbox",
            {"title": "T", "body": "b", "type": "task", "assignee": "crowd"},
        )
    assert raised.value.code == 400


def test_get_filters_by_assignee(queue_server) -> None:
    base, _tmp_path = queue_server
    post_json(base, "/api/inbox", {"title": "Mine", "body": "b", "type": "task"})
    filed = post_json(
        base,
        "/api/inbox",
        {
            "title": "For AI",
            "body": "b",
            "type": "task",
            "created_by": "owner",
            "assignee": "agent",
        },
    )
    agent_only = get_json(base, "/api/inbox?assignee=agent")
    assert [item["id"] for item in agent_only["items"]] == [filed["id"]]
    owner_only = get_json(base, "/api/inbox?assignee=owner")
    assert {item["id"] for item in owner_only["items"]} == {
        item["id"] for item in get_json(base, "/api/inbox")["items"]
    } - {filed["id"]}
    with pytest.raises(HTTPError) as raised:
        get_json(base, "/api/inbox?assignee=crowd")
    assert raised.value.code == 400


def test_queue_tab_present_in_js() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "#/inbox?status=queue" in js
    assert 'id="f-for"' in js
    assert "for AI" in js
