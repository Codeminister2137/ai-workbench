"""Owner-task inbox items: creation, Done default, completion with a note."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores, StoreError
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def tasks_server(tmp_path, monkeypatch):
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


def test_task_defaults_to_done_choice(tasks_server) -> None:
    base, _tmp_path = tasks_server
    created = post_json(
        base,
        "/api/inbox",
        {
            "title": "Probe the dictate button",
            "body": "1. Open chat. 2. Press Dictate. 3. Say hi. 4. Confirm text lands.",
            "type": "task",
        },
    )
    assert created["ok"] is True
    item = get_json(base, f"/api/inbox/{created['id']}")
    assert item["item"]["type"] == "task"
    assert item["item"]["options"] == ["Done"]
    assert item["item"]["status"] == "open"


def test_task_completes_with_note(tasks_server) -> None:
    base, _tmp_path = tasks_server
    created = post_json(
        base, "/api/inbox", {"title": "Add the key", "body": "Put it in .env.", "type": "task"}
    )
    answered = post_json(
        base,
        f"/api/inbox/{created['id']}/answer",
        {"answer": "Key stored in User env.", "option_index": 0},
    )
    assert answered["ok"] is True
    assert answered["status"] == "answered"
    item = get_json(base, f"/api/inbox/{created['id']}")
    assert item["item"]["answer"] == "Done"
    assert item["item"]["note"] == "Key stored in User env."


def test_task_lists_alongside_decisions(tasks_server) -> None:
    base, _tmp_path = tasks_server
    post_json(base, "/api/inbox", {"title": "T", "body": "b", "type": "task"})
    inbox = get_json(base, "/api/inbox")
    types = {item["type"] for item in inbox["items"]}
    assert "task" in types


def _lifecycle_stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def _lifecycle_task(stores):
    return stores.create_inbox_task(
        title="Ship it?", body="b", task_type="decision", options=["Yes", "No"]
    )


def test_close_requires_resolution(tmp_path) -> None:
    stores = _lifecycle_stores(tmp_path)
    task = _lifecycle_task(stores)
    with pytest.raises(StoreError, match="resolution"):
        stores.close_inbox_task(task["id"])
    with pytest.raises(StoreError, match="resolution"):
        stores.close_inbox_task(task["id"], resolution="   ")


def test_close_stores_resolution_resolved_at_closed(tmp_path) -> None:
    stores = _lifecycle_stores(tmp_path)
    task = _lifecycle_task(stores)
    closed = stores.close_inbox_task(task["id"], resolution="Shipped in abc123.")
    assert closed["status"] == "closed"
    assert closed["resolution"] == "Shipped in abc123."
    assert closed["resolved_at"]


def test_reclose_updates_resolution(tmp_path) -> None:
    stores = _lifecycle_stores(tmp_path)
    task = _lifecycle_task(stores)
    stores.close_inbox_task(task["id"], resolution="First outcome.")
    updated = stores.close_inbox_task(task["id"], resolution="Follow-up outcome.")
    assert updated["status"] == "closed"
    assert updated["resolution"] == "Follow-up outcome."


def test_reopen_closed_to_open_keeping_history(tmp_path) -> None:
    stores = _lifecycle_stores(tmp_path)
    task = _lifecycle_task(stores)
    stores.answer_inbox_task(task["id"], answer="Yes")
    stores.close_inbox_task(task["id"], resolution="Done.")
    reopened = stores.reopen_inbox_task(task["id"])
    assert reopened["status"] == "open"
    assert reopened["answer"] == "Yes"
    assert reopened["resolution"] == "Done."


def test_reopen_of_open_task_errors(tmp_path) -> None:
    stores = _lifecycle_stores(tmp_path)
    task = _lifecycle_task(stores)
    with pytest.raises(StoreError):
        stores.reopen_inbox_task(task["id"])


def test_answer_still_refused_on_closed(tmp_path) -> None:
    stores = _lifecycle_stores(tmp_path)
    task = _lifecycle_task(stores)
    stores.close_inbox_task(task["id"], resolution="Done.")
    with pytest.raises(StoreError):
        stores.answer_inbox_task(task["id"], answer="Late")


def test_delete_removes_item_and_404s_after(tasks_server) -> None:
    base, tmp_path = tasks_server
    created = post_json(
        base,
        "/api/inbox",
        {"title": "Scratch", "body": "x", "type": "task"},
    )
    item_id = created["id"]
    deleted = post_json(base, f"/api/inbox/{item_id}/delete", {})
    assert deleted == {"ok": True, "id": item_id}
    assert not (tmp_path / "data" / "inbox" / f"{item_id}.json").exists()
    with pytest.raises(HTTPError) as raised:
        get_json(base, f"/api/inbox/{item_id}")
    assert raised.value.code == 404
    with pytest.raises(HTTPError) as raised:
        post_json(base, f"/api/inbox/{item_id}/delete", {})
    assert raised.value.code == 404


def test_collection_delete_rejects_bad_ids(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    assert stores.inbox.delete("no-such-id") is False
    with pytest.raises(StoreError):
        stores.inbox.delete("../escape")
