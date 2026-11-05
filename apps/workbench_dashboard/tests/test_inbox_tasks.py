"""Owner-task inbox items: creation, Done default, completion with a note."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest
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


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


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
