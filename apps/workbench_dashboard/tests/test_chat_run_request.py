from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_test_http import get_json, post_json
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def chat_run_server(tmp_path, monkeypatch):
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


def post_status(base: str, path: str, payload: dict) -> int:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            return 200
    except HTTPError as exc:
        return exc.code


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _new_session(base: str) -> str:
    created = post_json(base, "/api/chat/sessions", {"title": "Wake me"})
    assert created["ok"] is True
    return created["id"]


def test_run_request_queues_run_and_approval(chat_run_server) -> None:
    """Chat run-request creates a queued run + approval decision + receipt."""
    base, tmp_path = chat_run_server
    session_id = _new_session(base)

    receipt = post_json(
        base,
        f"/api/chat/sessions/{session_id}/run-request",
        {"text": "Give me a status report", "title": "Status report"},
    )
    assert receipt["ok"] is True
    assert receipt["status"] == "queued"
    assert receipt["fanout_effective"] == "restricted"
    run_id = receipt["run_id"]
    inbox_id = receipt["inbox_id"]

    run = _read_json(tmp_path / "data" / "runs" / f"{run_id}.json")
    assert run["status"] == "queued"
    assert run["origin"] == "chat"
    assert run["session_id"] == session_id
    assert run["fanout_policy"] == "restricted"
    assert run["fanout_effective"] == "restricted"
    assert run["inbox_id"] == inbox_id
    assert "Give me a status report" in run["body"]

    inbox = _read_json(tmp_path / "data" / "inbox" / f"{inbox_id}.json")
    assert inbox["type"] == "decision"
    assert inbox["status"] == "open"
    assert inbox["task_id"] == run_id
    assert inbox["options"] == ["Approve", "Reject"]
    assert f"run:{run_id}" in inbox["context_refs"]


def test_run_request_appends_transcript_receipt(chat_run_server) -> None:
    """The chat thread keeps a visible system note for the queued run."""
    base, _tmp_path = chat_run_server
    session_id = _new_session(base)

    receipt = post_json(
        base, f"/api/chat/sessions/{session_id}/run-request", {"text": "Summarize plans"}
    )
    assert receipt["ok"] is True

    messages = get_json(base, f"/api/chat/sessions/{session_id}/messages")
    assert messages["ok"] is True
    notes = [m for m in messages["messages"] if m["role"] == "system"]
    assert len(notes) == 1
    assert receipt["run_id"] in notes[0]["content"]
    assert "restricted" in notes[0]["content"]


def test_run_request_unknown_session_is_404(chat_run_server) -> None:
    base, _tmp_path = chat_run_server
    assert post_status(base, "/api/chat/sessions/nope/run-request", {"text": "Hi"}) == 404


def test_run_request_empty_text_is_400(chat_run_server) -> None:
    base, _tmp_path = chat_run_server
    session_id = _new_session(base)
    assert post_status(base, f"/api/chat/sessions/{session_id}/run-request", {"text": "  "}) == 400


def test_run_request_honors_configured_policy(chat_run_server) -> None:
    """The owner can widen the chat fan-out policy via dashboard config."""
    base, tmp_path = chat_run_server
    (tmp_path / "dashboard.json").write_text(
        json.dumps(
            {
                "provider": "ollama",
                "model": "fake",
                "title": "Test Board",
                "chat_fanout_policy": "allowed",
            }
        ),
        encoding="utf-8",
    )
    session_id = _new_session(base)
    receipt = post_json(base, f"/api/chat/sessions/{session_id}/run-request", {"text": "Do it"})
    assert receipt["ok"] is True
    assert receipt["fanout_effective"] == "allowed"
    run = _read_json(tmp_path / "data" / "runs" / f"{receipt['run_id']}.json")
    assert run["fanout_effective"] == "allowed"


def test_run_request_rejects_unknown_policy(chat_run_server) -> None:
    """An unknown configured policy fails closed instead of guessing."""
    base, tmp_path = chat_run_server
    (tmp_path / "dashboard.json").write_text(
        json.dumps(
            {
                "provider": "ollama",
                "model": "fake",
                "title": "Test Board",
                "chat_fanout_policy": "sometimes",
            }
        ),
        encoding="utf-8",
    )
    session_id = _new_session(base)
    assert (
        post_status(base, f"/api/chat/sessions/{session_id}/run-request", {"text": "Do it"}) == 400
    )


def test_run_request_attaches_transcript_digest(chat_run_server) -> None:
    """Run body and approval carry the conversation, not just one message."""
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore

    base, tmp_path = chat_run_server
    session_id = _new_session(base)
    store = SQLiteChatTranscriptStore(tmp_path / "data" / "chats.sqlite3")
    store.append_message(session_id, role="user", content="We need a status page")
    store.append_message(session_id, role="assistant", content="Drafted the layout")

    receipt = post_json(base, f"/api/chat/sessions/{session_id}/run-request", {"text": "Build it"})
    assert receipt["ok"] is True
    run = _read_json(tmp_path / "data" / "runs" / f"{receipt['run_id']}.json")
    assert "Build it" in run["body"]
    assert "We need a status page" in run["body"]
    assert "Drafted the layout" in run["body"]
    assert session_id in run["body"]
    inbox = _read_json(tmp_path / "data" / "inbox" / f"{receipt['inbox_id']}.json")
    assert "We need a status page" in inbox["body"]
