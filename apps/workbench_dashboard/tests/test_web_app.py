from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def dashboard_server(tmp_path, monkeypatch):
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

    def fake_execute(self, request):
        from ai_agent.coding_chat import CodingTurnResult

        return CodingTurnResult(0, "Fake answer.", "completed", provider="ollama")

    monkeypatch.setattr("dashboard_chat.DashboardChat._execute", fake_execute)

    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base: str, path: str, payload: dict, headers: dict | None = None) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_status_reports_empty_state(dashboard_server) -> None:
    payload = get_json(dashboard_server, "/api/status")
    assert payload["ok"] is True
    assert payload["title"] == "Test Board"
    assert payload["open_inbox"] == 0
    assert payload["current_plan"] is None
    assert payload["evidence"]["available"] is False


def test_evidence_merges_snapshots(dashboard_server, tmp_path) -> None:
    probes = tmp_path / "artifacts" / "route-probes"
    evals = tmp_path / "artifacts" / "route-evals"
    probes.mkdir(parents=True)
    evals.mkdir(parents=True)
    (probes / "route-probe-20261101T000000Z.json").write_text(
        json.dumps([{"route": "meta", "reachable": True}]), encoding="utf-8"
    )
    (evals / "route-eval-20261101T000000Z.json").write_text(
        json.dumps([{"route": "meta", "passed": True}]), encoding="utf-8"
    )
    payload = get_json(dashboard_server, "/api/evidence")
    assert payload["ok"] is True
    assert payload["available"] is True
    assert payload["routes"] == [{"route": "meta", "reachable": True, "passed_eval": True}]


def test_chat_round_trip(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/chat/sessions", {"title": "Hello"})
    assert created["ok"] is True
    session_id = created["id"]

    answer = post_json(
        dashboard_server, f"/api/chat/sessions/{session_id}/messages", {"text": "Hi there"}
    )
    assert answer["ok"] is True
    assert answer["response_text"] == "Fake answer."

    messages = get_json(dashboard_server, f"/api/chat/sessions/{session_id}/messages")
    assert [message["role"] for message in messages["messages"]] == ["user", "assistant"]

    sessions = get_json(dashboard_server, "/api/chat/sessions")
    assert [session["id"] for session in sessions["sessions"]] == [session_id]


def test_chat_rejects_empty_message(dashboard_server) -> None:
    created = post_json(dashboard_server, "/api/chat/sessions", {})
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, f"/api/chat/sessions/{created['id']}/messages", {"text": "  "})
    assert raised.value.code == 400
    raised.value.close()


def test_inbox_flow_and_token_gate(dashboard_server, tmp_path) -> None:
    created = post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "Pick one", "body": "A or B?", "type": "decision", "options": ["A", "B"]},
    )
    assert created["ok"] is True
    item_id = created["id"]

    status = get_json(dashboard_server, "/api/status")
    assert status["open_inbox"] == 1

    answered = post_json(
        dashboard_server, f"/api/inbox/{item_id}/answer", {"answer": "", "option_index": 0}
    )
    assert answered["status"] == "answered"

    closed = post_json(dashboard_server, f"/api/inbox/{item_id}/close", {})
    assert closed["status"] == "closed"

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "supervisor.token").write_text("s3cret", encoding="utf-8")
    with pytest.raises(HTTPError) as raised:
        post_json(dashboard_server, "/api/inbox", {"title": "t", "body": "b", "type": "decision"})
    assert raised.value.code == 403
    raised.value.close()

    gated = post_json(
        dashboard_server,
        "/api/inbox",
        {"title": "t", "body": "b", "type": "decision"},
        headers={"X-Supervisor-Token": "s3cret"},
    )
    assert gated["ok"] is True


def test_untrusted_origin_refused(dashboard_server) -> None:
    request = Request(
        f"{dashboard_server}/api/status", headers={"Origin": "https://evil.invalid"}, method="GET"
    )
    with pytest.raises(HTTPError) as raised:
        urlopen(request, timeout=5)
    assert raised.value.code == 403
    raised.value.close()
