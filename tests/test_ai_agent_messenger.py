"""Messenger relay turns: inspection tools only, receipts always."""

from __future__ import annotations

from pathlib import Path

from ai_agent.messenger import run_messenger_turn
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    UsageMetadata,
)


class FakeClient:
    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self, script) -> None:
        self.requests = []
        self.calls = 0
        self._script = script

    def complete(self, request):
        self.requests.append(request)
        message = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def _tool_message(name: str, arguments: dict) -> AIMessage:
    return AIMessage(
        MessageRole.ASSISTANT,
        "",
        tool_calls=(AIToolCall("call-1", name, arguments),),
    )


def test_messenger_answers_with_inspection_receipts(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello workspace", encoding="utf-8")
    client = FakeClient(
        [
            _tool_message("read_file", {"path": "notes.txt"}),
            AIMessage(MessageRole.ASSISTANT, "The file says hello."),
        ]
    )
    result = run_messenger_turn(
        client=client,
        workspace_root=tmp_path,
        history_text="",
        prompt="What is in notes.txt?",
        system_prompt="Be brief.",
    )
    assert result.answer == "The file says hello."
    assert result.tool_receipts == ("read_file",)
    assert result.iterations == 2
    assert result.hit_iteration_limit is False
    assert "hello workspace" in repr(client.requests[1].messages)


def test_messenger_registers_inspection_profile_only(tmp_path: Path) -> None:
    client = FakeClient([AIMessage(MessageRole.ASSISTANT, "done")])
    run_messenger_turn(
        client=client,
        workspace_root=tmp_path,
        history_text="",
        prompt="Hi",
        system_prompt="Be brief.",
    )
    names = {tool.name for tool in client.requests[0].tools}
    assert names == {
        "read_file",
        "list_dir",
        "find_files",
        "grep_search",
        "git_status",
        "git_diff",
    }


def test_messenger_refuses_credential_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("GMAIL_PASSWORD=hunter2", encoding="utf-8")
    client = FakeClient(
        [
            _tool_message("read_file", {"path": ".env"}),
            AIMessage(MessageRole.ASSISTANT, "I cannot read that file."),
        ]
    )
    result = run_messenger_turn(
        client=client,
        workspace_root=tmp_path,
        history_text="",
        prompt="Read the env file.",
        system_prompt="Be brief.",
    )
    assert result.answer == "I cannot read that file."
    tool_text = repr(client.requests[1].messages)
    assert "refused" in tool_text.lower()
    assert "hunter2" not in tool_text


def test_messenger_falls_back_on_iteration_limit(tmp_path: Path) -> None:
    client = FakeClient([_tool_message("list_dir", {"path": "."})])
    result = run_messenger_turn(
        client=client,
        workspace_root=tmp_path,
        history_text="",
        prompt="Keep listing.",
        system_prompt="Be brief.",
        max_iterations=1,
    )
    assert result.hit_iteration_limit is True
    assert "ran out of steps" in result.answer
    assert result.tool_receipts == ("list_dir",)
