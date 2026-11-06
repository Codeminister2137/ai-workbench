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


def test_rename_and_delete_session(chat, tmp_path) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    record = chat.create_session(title="Typo name")
    renamed = chat.rename_session(record.session_id, title="Fixed name")
    assert renamed.title == "Fixed name"
    got = store.get_session(record.session_id)
    assert got is not None and got.title == "Fixed name"
    chat.delete_session(record.session_id)
    assert store.get_session(record.session_id) is None
    with pytest.raises(ValueError, match="not found"):
        chat.delete_session(record.session_id)
    with pytest.raises(ValueError, match="not be empty"):
        chat.rename_session(record.session_id, title="   ")


def test_delete_removes_messages(chat) -> None:
    record = chat.create_session(title="Gone")
    chat.send(record.session_id, "hello")
    assert len(chat.list_messages(record.session_id)) == 2
    chat.delete_session(record.session_id)
    with pytest.raises(ValueError, match="not found"):
        chat.list_messages(record.session_id)


def test_system_prompt_grounds_capabilities(tmp_path) -> None:
    """The supervisor prompt states its real limits (no tools/mail/live view)."""
    from ai_agent.supervisor_prompt import (
        SUPERVISOR_CORE_BUDGET_CHARS,
        assemble_supervisor_prompt,
    )
    from ai_provider.contracts import MessageRole
    from dashboard_chat import SUPERVISOR_SYSTEM_PROMPT, DashboardChat

    made: list = []

    def factory(config):
        client = FakeClient(config)
        made.append(client)
        return client

    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    chat = DashboardChat(
        store,
        DashboardConfig(provider="ollama", model="fake"),
        tmp_path,
        client_factory=factory,
    )
    record = chat.create_session(title="t")
    chat.send(record.session_id, "Hi")
    system = made[0].seen[0].messages[0]
    assert system.role is MessageRole.SYSTEM
    assert system.content == assemble_supervisor_prompt(approval_policy="restricted")
    assert system.content.startswith(SUPERVISOR_SYSTEM_PROMPT)
    assert len(SUPERVISOR_SYSTEM_PROMPT) <= SUPERVISOR_CORE_BUDGET_CHARS
    for phrase in (
        "inspect the workspace",
        "cannot edit files",
        "never claim an email was or will be sent",
        "no live view of services",
        "Request-run button",
        "runs Windows",
    ):
        assert phrase in SUPERVISOR_SYSTEM_PROMPT


def test_send_uses_relay_and_appends_receipts(tmp_path) -> None:
    """Relay answers land in the transcript with visible tool receipts."""
    from ai_agent.messenger import MessengerResult
    from dashboard_chat import DashboardChat

    seen: dict = {}

    def fake_relay(**kwargs):
        seen.update(kwargs)
        return MessengerResult(answer="Found it.", tool_receipts=("read_file",), iterations=2)

    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    chat = DashboardChat(
        store,
        DashboardConfig(provider="ollama", model="fake"),
        tmp_path,
        client_factory=lambda config: FakeClient(config),
        relay_runner=fake_relay,
    )
    record = chat.create_session(title="t")
    outcome = chat.send(record.session_id, "Hi")
    assert outcome.response_text == "Found it.\n\n_Checked with tools: read_file._"
    assert outcome.execution_status == "completed"
    assert seen["prompt"] == "Hi"
    assert seen["workspace_root"] == tmp_path.resolve()
    messages = chat.list_messages(record.session_id)
    assert messages[1].content.endswith("read_file._")
