"""Chat-channel tools: run status, pending inbox, and doc reads for chat only."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from agent_executor import build_executor_registry
from ai_agent.contracts import ToolCall, ToolCategory, ToolResult
from ai_agent.messenger import MessengerResult, run_messenger_turn
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry
from ai_agent.tools.filesystem import CreateFileTool
from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamEvent,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    UsageMetadata,
)
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from ai_provider.config import BackendConfig
from chat_channel_tools import CHAT_CHANNEL_TOOL_NAMES, build_chat_channel_tools
from dashboard_chat import DashboardChat
from dashboard_config import DashboardConfig
from dashboard_stores import DashboardStores
from document_library import DocumentLibrary


class ScriptedClient:
    """Reply with scripted messages; records every request for assertions."""

    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self, script: list[AIMessage]) -> None:
        self.requests: list[AIRequest] = []
        self.calls = 0
        self._script = script

    def complete(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        message = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        raise NotImplementedError("Scripted client does not stream")


def _tool_message(name: str, arguments: dict) -> AIMessage:
    return AIMessage(
        MessageRole.ASSISTANT,
        "",
        tool_calls=(AIToolCall("call-1", name, arguments),),
    )


@pytest.fixture
def stores(tmp_path: Path) -> DashboardStores:
    return DashboardStores(tmp_path / "data")


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    root = tmp_path / "lib"
    root.mkdir()
    return DocumentLibrary(tmp_path, roots={"library": root})


@pytest.fixture
def lib_root(tmp_path: Path) -> Path:
    return tmp_path / "lib"


def _channel_tool(stores: DashboardStores, library: DocumentLibrary, name: str) -> BaseTool:
    for tool in build_chat_channel_tools(stores, library):
        if tool.definition.name == name:
            return tool
    raise AssertionError(f"missing chat-channel tool {name}")


def _run_guarded(
    tool: BaseTool,
    arguments: dict[str, Any],
    workspace: Path,
    *,
    secrets: tuple[str, ...] = (),
) -> ToolResult:
    """Execute one tool through the guarded registry path (as the loop does)."""
    registry = ToolRegistry(tools=(tool,))
    call = ToolCall(name=tool.definition.name, arguments=arguments, call_id="call-1")
    return registry.execute(call, ToolContext(workspace, credential_secrets=secrets))


def test_get_run_status_by_id(
    stores: DashboardStores, library: DocumentLibrary, tmp_path: Path
) -> None:
    stores.runs.put(
        "run-1",
        {
            "id": "run-1",
            "title": "Fix login",
            "status": "queued",
            "body": "Repair the login flow end to end.",
            "fanout_effective": "restricted",
            "inbox_id": "inbox-1",
            "plan_id": None,
            "updated_at_utc": "2026-01-01T00:00:00+00:00",
        },
    )
    tool = _channel_tool(stores, library, "get_run_status")
    result = _run_guarded(tool, {"run_id": "run-1"}, tmp_path)
    assert not result.is_error
    assert "run run-1: Fix login" in result.output
    assert "status: queued" in result.output
    assert "fanout: restricted" in result.output
    assert "inbox: inbox-1" in result.output
    missing = _run_guarded(tool, {"run_id": "nope"}, tmp_path)
    assert missing.is_error
    assert "unknown run id" in missing.output
    invalid = _run_guarded(tool, {"run_id": "../escape"}, tmp_path)
    assert invalid.is_error


def test_list_pending_inbox_without_secrets(
    stores: DashboardStores, library: DocumentLibrary, tmp_path: Path
) -> None:
    secret = "token hunter2-secret-value"
    first = stores.create_inbox_task(
        title="Approve agent run: widget",
        body=f"Run details include {secret}",
        task_type="decision",
        task_id="run-9",
    )
    stores.create_inbox_task(title="Pick a color", body="red or blue?", task_type="clarification")
    done = stores.create_inbox_task(title="Old task", body="already handled", task_type="task")
    stores.answer_inbox_task(done["id"], answer="Done", option_index=0)
    tool = _channel_tool(stores, library, "list_pending_inbox")
    result = _run_guarded(tool, {}, tmp_path)
    assert not result.is_error
    assert "2 open inbox items" in result.output
    assert first["id"] in result.output
    assert "Approve agent run: widget" in result.output
    assert secret not in result.output
    assert "hunter2" not in result.output
    assert "red or blue?" not in result.output
    assert "already handled" not in result.output
    assert done["id"] not in result.output


def test_read_dashboard_doc_capped(
    stores: DashboardStores, library: DocumentLibrary, lib_root: Path, tmp_path: Path
) -> None:
    (lib_root / "notes.md").write_text(
        "---\ntitle: Field notes\n---\n" + "line of notes\n" * 1000, encoding="utf-8"
    )
    (lib_root / "sub").mkdir()
    (lib_root / "sub" / "dup.md").write_text("# one\n", encoding="utf-8")
    (lib_root / "dup.md").write_text("# two\n", encoding="utf-8")
    tool = _channel_tool(stores, library, "read_dashboard_doc")
    result = _run_guarded(tool, {"name": "library/notes.md"}, tmp_path)
    assert not result.is_error
    assert result.output.startswith("doc library/notes.md:")
    assert "line of notes" in result.output
    assert "truncated to 4000 chars" in result.output
    assert len(result.output) < 6000
    by_filename = _run_guarded(tool, {"name": "notes.md"}, tmp_path)
    assert not by_filename.is_error
    assert by_filename.output.startswith("doc library/notes.md:")
    missing = _run_guarded(tool, {"name": "library/missing.md"}, tmp_path)
    assert missing.is_error
    assert "unknown document" in missing.output
    ambiguous = _run_guarded(tool, {"name": "dup.md"}, tmp_path)
    assert ambiguous.is_error
    assert "several documents" in ambiguous.output


def test_credential_files_and_outputs_refused(
    stores: DashboardStores, library: DocumentLibrary, lib_root: Path, tmp_path: Path
) -> None:
    tool = _channel_tool(stores, library, "read_dashboard_doc")
    for name in (".env", "library/.env"):
        refused = _run_guarded(tool, {"name": name}, tmp_path)
        assert refused.is_error
        assert "refused" in refused.output.lower()
    (lib_root / "leak.md").write_text("the password is s3cr3t-value\n", encoding="utf-8")
    withheld = _run_guarded(tool, {"name": "library/leak.md"}, tmp_path, secrets=("s3cr3t-value",))
    assert withheld.is_error
    assert "withheld" in withheld.output
    assert "s3cr3t-value" not in withheld.output


def test_chat_tools_cannot_write(
    stores: DashboardStores, library: DocumentLibrary, tmp_path: Path
) -> None:
    tools = build_chat_channel_tools(stores, library)
    assert [tool.definition.name for tool in tools] == list(CHAT_CHANNEL_TOOL_NAMES)
    assert all(tool.definition.category is ToolCategory.READ for tool in tools)
    read_only = PermissionManager(policy=PermissionPolicy.read_only())
    valid_args = {
        "get_run_status": {"run_id": "run-1"},
        "list_pending_inbox": {},
        "read_dashboard_doc": {"name": "library/notes.md"},
    }
    for tool in tools:
        call = ToolCall(name=tool.definition.name, arguments=valid_args[tool.definition.name])
        assert read_only.check_and_authorize(tool, call) is True
    client = ScriptedClient([AIMessage(MessageRole.ASSISTANT, "unused")])
    with pytest.raises(ValueError, match="must be read-only"):
        run_messenger_turn(
            client=client,
            workspace_root=tmp_path,
            history_text="",
            prompt="Hi",
            system_prompt="Be brief.",
            extra_tools=(CreateFileTool(),),
        )
    assert client.calls == 0
    write_call = ToolCall(name="create_file", arguments={"path": "p", "content": "c"})
    assert read_only.check_and_authorize(CreateFileTool(), write_call) is False
    executor_names = {tool.name for tool in build_executor_registry().list_definitions()}
    assert executor_names.isdisjoint(CHAT_CHANNEL_TOOL_NAMES)


def test_tool_failure_surfaces_as_receipt(
    stores: DashboardStores, library: DocumentLibrary, tmp_path: Path
) -> None:
    client = ScriptedClient(
        [
            _tool_message("get_run_status", {"run_id": "missing"}),
            AIMessage(MessageRole.ASSISTANT, "That run id is unknown."),
        ]
    )
    result = run_messenger_turn(
        client=client,
        workspace_root=tmp_path,
        history_text="",
        prompt="What is the status of run missing?",
        system_prompt="Be brief.",
        extra_tools=build_chat_channel_tools(stores, library),
    )
    assert result.answer == "That run id is unknown."
    assert result.tool_receipts == ("get_run_status:error",)
    assert "unknown run id" in repr(client.requests[1].messages)


def test_chat_send_uses_channel_tools_end_to_end(
    stores: DashboardStores, library: DocumentLibrary, tmp_path: Path
) -> None:
    stores.runs.put(
        "run-7",
        {
            "id": "run-7",
            "title": "Fix login",
            "status": "queued",
            "body": "Repair the login flow.",
            "fanout_effective": "restricted",
            "updated_at_utc": "2026-01-01T00:00:00+00:00",
        },
    )
    made: list[ScriptedClient] = []

    def factory(config: BackendConfig) -> ScriptedClient:
        client = ScriptedClient(
            [
                _tool_message("get_run_status", {"run_id": "run-7"}),
                AIMessage(MessageRole.ASSISTANT, "Run run-7 is queued."),
            ]
        )
        made.append(client)
        return client

    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    chat = DashboardChat(
        store,
        DashboardConfig(provider="ollama", model="fake"),
        tmp_path,
        client_factory=factory,
        chat_tools=build_chat_channel_tools(stores, library),
    )
    record = chat.create_session(title="t")
    outcome = chat.send(record.session_id, "Status of run-7?")
    assert outcome.execution_status == "completed"
    assert outcome.response_text == "Run run-7 is queued.\n\n_Checked with tools: get_run_status._"
    advertised = {tool.name for tool in made[0].requests[0].tools}
    assert set(CHAT_CHANNEL_TOOL_NAMES) <= advertised
    messages = chat.list_messages(record.session_id)
    assert messages[1].content.endswith("get_run_status._")


def test_relay_kwargs_unchanged_when_tools_unused(tmp_path: Path) -> None:
    seen: dict[str, Any] = {}

    def fake_relay(**kwargs: Any) -> MessengerResult:
        seen.update(kwargs)
        return MessengerResult(answer="ok", tool_receipts=(), iterations=1)

    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    chat = DashboardChat(
        store,
        DashboardConfig(provider="ollama", model="fake"),
        tmp_path,
        client_factory=lambda config: ScriptedClient([AIMessage(MessageRole.ASSISTANT, "unused")]),
        relay_runner=fake_relay,
    )
    record = chat.create_session(title="t")
    chat.send(record.session_id, "Hi")
    assert set(seen) == {
        "client",
        "workspace_root",
        "history_text",
        "prompt",
        "system_prompt",
        "privacy_class",
    }
