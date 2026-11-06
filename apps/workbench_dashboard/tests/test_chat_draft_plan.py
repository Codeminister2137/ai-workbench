"""Chat draft-plan: deterministic proposed plans from transcripts plus endpoint."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest
from ai_provider import AIRequest
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from dashboard_chat import DashboardChat
from dashboard_config import DashboardConfig
from dashboard_stores import DashboardStores
from dashboard_test_http import post_json


class FakeClient:
    def __init__(self, config) -> None:
        from ai_provider.contracts import BackendInfo, BackendLocation

        self.config = config
        self._backend = BackendInfo(provider="ollama", model="fake", location=BackendLocation.LOCAL)

    @property
    def backend(self):
        return self._backend

    def stream(self, request):
        raise NotImplementedError("Fake client does not stream")

    def complete(self, request: AIRequest):
        from ai_provider.contracts import (
            AIMessage,
            AIResponse,
            FinishReason,
            MessageRole,
        )

        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content="noted"),
            backend=self._backend,
            finish_reason=FinishReason.STOP,
        )


@pytest.fixture
def chat(tmp_path):
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(provider="ollama", model="fake")
    return DashboardChat(store, config, tmp_path, client_factory=FakeClient)


def test_draft_plan_from_transcript(chat, tmp_path) -> None:
    record = chat.create_session(title="Shop design")
    chat.send(record.session_id, "I need an online shop for handmade soaps with checkout")
    stores = DashboardStores(tmp_path / "data")
    plan = chat.draft_plan(record.session_id, stores=stores)
    assert plan["status"] == "proposed"
    assert plan["title"] == "Shop design (draft plan)"
    assert plan["source"] == f"chat:{record.session_id}"
    assert "handmade soaps" in plan["body"]
    assert "## Open sections" in plan["body"]
    assert stores.plans.get(plan["id"]) is not None


def test_draft_plan_custom_title_and_empty_chat(chat, tmp_path) -> None:
    record = chat.create_session(title="Shop design")
    chat.send(record.session_id, "Sell soap online please with a cart")
    stores = DashboardStores(tmp_path / "data")
    plan = chat.draft_plan(record.session_id, stores=stores, title="Soap shop")
    assert plan["title"] == "Soap shop"
    empty = chat.create_session(title="Silent")
    with pytest.raises(ValueError, match="no turns"):
        chat.draft_plan(empty.session_id, stores=stores)
    with pytest.raises(ValueError, match="not found"):
        chat.draft_plan("ghost", stores=stores)


def test_draft_plan_endpoint(dashboard_server, tmp_path) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "data" / "chats.sqlite3")
    config = DashboardConfig(provider="ollama", model="fake")
    server_chat = DashboardChat(store, config, tmp_path, client_factory=FakeClient)
    record = server_chat.create_session(title="Shop design")
    server_chat.send(record.session_id, "Sell soap online please with a cart")
    payload = post_json(dashboard_server, f"/api/chat/sessions/{record.session_id}/draft-plan", {})
    assert payload["ok"] is True
    assert payload["plan"]["status"] == "proposed"
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/chat/sessions/ghost/draft-plan", {})
    assert exc.value.code == 404
