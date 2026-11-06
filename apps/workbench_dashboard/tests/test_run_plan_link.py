"""Run↔plan linking: request with plan, fail-closed, filter runs by plan."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores
from dashboard_test_http import get_json, post_json


def _seed_session_and_plan(tmp_path):
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
    from dashboard_chat import DashboardChat
    from dashboard_config import DashboardConfig

    store = SQLiteChatTranscriptStore(tmp_path / "data" / "chats.sqlite3")
    chat = DashboardChat(store, DashboardConfig(provider="ollama", model="fake"), tmp_path)
    session = chat.create_session(title="Design")
    stores = DashboardStores(tmp_path / "data")
    stores.plans.put("p1", {"id": "p1", "title": "Shop", "status": "proposed", "body": "b"})
    return session.session_id


def test_run_request_links_plan(dashboard_server, tmp_path) -> None:
    session_id = _seed_session_and_plan(tmp_path)
    receipt = post_json(
        dashboard_server,
        f"/api/chat/sessions/{session_id}/run-request",
        {"text": "Build the shop", "plan": "p1"},
    )
    run_id = receipt["run_id"]
    stores = DashboardStores(tmp_path / "data")
    run = stores.runs.get(run_id)
    assert run is not None and run["plan_id"] == "p1"
    inbox = stores.inbox.get(receipt["inbox_id"])
    assert inbox is not None and inbox["plan_id"] == "p1"
    assert "plan:p1" in inbox["context_refs"]
    filtered = get_json(dashboard_server, "/api/runs?plan_id=p1")
    assert [item["id"] for item in filtered["items"]] == [run_id]
    assert get_json(dashboard_server, "/api/runs?plan_id=other")["items"] == []


def test_run_request_unknown_plan_refused(dashboard_server, tmp_path) -> None:
    session_id = _seed_session_and_plan(tmp_path)
    with pytest.raises(HTTPError) as exc:
        post_json(
            dashboard_server,
            f"/api/chat/sessions/{session_id}/run-request",
            {"text": "Build it", "plan": "ghost"},
        )
    assert exc.value.code == 400
    stores = DashboardStores(tmp_path / "data")
    assert stores.runs.list(limit=100)[1] == 0
