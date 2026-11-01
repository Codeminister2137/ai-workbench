from __future__ import annotations

import pytest
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.contracts import AIRequest, AIResponse
from dashboard_chat import DashboardChat
from dashboard_config import DashboardConfig


class FakeClient:
    def __init__(self, config) -> None:
        from ai_provider.contracts import BackendInfo, BackendLocation

        self.config = config
        self.seen: list[AIRequest] = []
        self._backend = BackendInfo(provider="ollama", model="fake", location=BackendLocation.LOCAL)

    @property
    def backend(self):
        return self._backend

    def stream(self, request):
        raise NotImplementedError("Fake client does not stream")

    def complete(self, request: AIRequest) -> AIResponse:
        from ai_provider.contracts import (
            AIMessage,
            BackendInfo,
            BackendLocation,
            FinishReason,
            MessageRole,
        )

        self.seen.append(request)
        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content="Fake answer."),
            backend=BackendInfo(provider="ollama", model="fake", location=BackendLocation.LOCAL),
            finish_reason=FinishReason.STOP,
            latency_ms=3.0,
        )


@pytest.fixture
def chat(tmp_path):
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(provider="ollama", model="fake")
    return DashboardChat(store, config, tmp_path, client_factory=FakeClient)


def test_send_appends_user_and_assistant_turn(chat) -> None:
    record = chat.create_session(title="Hello")
    outcome = chat.send(record.session_id, "What would you do?")
    assert outcome.execution_status == "completed"
    assert outcome.response_text == "Fake answer."
    messages = chat.list_messages(record.session_id)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "What would you do?"


def test_send_unknown_provider_fails_in_transcript(tmp_path) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(provider="nope", model="fake")
    chat = DashboardChat(store, config, tmp_path, client_factory=FakeClient)
    record = chat.create_session(title="Bad provider")
    outcome = chat.send(record.session_id, "Hi")
    assert outcome.execution_status == "failed"
    assert "Unknown provider" in (outcome.failure_reason or "")
    messages = chat.list_messages(record.session_id)
    assert messages[-1].role == "assistant"


def test_missing_session_refused(chat) -> None:
    with pytest.raises(ValueError, match="not found"):
        chat.send("missing", "Hi")
