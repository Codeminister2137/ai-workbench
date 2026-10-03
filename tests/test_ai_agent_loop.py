from __future__ import annotations

from pathlib import Path

import pytest
from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolCall,
    ToolContext,
    ToolResult,
    coding_tools_with_delegation,
    default_coding_tools,
)
from ai_provider import (
    AIMessage,
    AIResponse,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    UsageMetadata,
)


class FakeClient:
    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self) -> None:
        self.requests = []
        self.calls = 0

    def complete(self, request):
        self.requests.append(request)
        self.calls += 1
        if self.calls == 1:
            message = AIMessage(
                MessageRole.ASSISTANT,
                "",
                tool_calls=(
                    AIToolCall("call-1", "create_file", {"path": "out.txt", "content": "done"}),
                ),
            )
        else:
            message = AIMessage(MessageRole.ASSISTANT, "Finished")
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def test_agent_loop_executes_tools_and_returns_final_response(tmp_path: Path) -> None:
    client = FakeClient()
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=3,
    ).run("Create the file", privacy_class=PrivacyClass.LOCAL_ONLY)

    assert result.response.message.content == "Finished"
    assert result.iterations == 2
    assert result.tool_results[0].is_error is False
    assert (tmp_path / "out.txt").read_text() == "done"
    assert len(client.requests[0].tools) == 7
    assert client.requests[1].messages[-1].role is MessageRole.TOOL


def test_delegation_tool_runs_bounded_child_task(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner(task: str, context: ToolContext) -> ToolResult:
        calls.append(task)
        (context.workspace_root / "child.txt").write_text("child", encoding="utf-8")
        return ToolResult(name="delegate_task", output="child done")

    registry = coding_tools_with_delegation(runner)
    result = registry.execute(
        ToolCall("delegate_task", {"task": "write a small helper"}),
        ToolContext(tmp_path),
    )

    assert result.output == "child done"
    assert calls == ["write a small helper"]
    assert (tmp_path / "child.txt").read_text(encoding="utf-8") == "child"
    assert len(registry.list_definitions()) == 8


def test_provider_failure_preserves_completed_tool_receipt_without_replaying(
    tmp_path: Path,
) -> None:
    failure = ProviderError("Provider stopped after the tool completed")

    class FailingFollowupClient(FakeClient):
        def complete(self, request):
            if self.calls:
                self.requests.append(request)
                raise failure
            return super().complete(request)

    client = FailingFollowupClient()
    loop = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=3,
    )
    with pytest.raises(ProviderError) as raised:
        loop.run(
            "Create the file",
            system_prompt="Preserve receipts",
            privacy_class=PrivacyClass.LOCAL_ONLY,
        )
    assert raised.value is failure
    assert (tmp_path / "out.txt").read_text() == "done"
    assert failure.partial_messages == client.requests[-1].messages
    assert [message.role for message in failure.partial_messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
    ]
    assert failure.partial_messages[-1].tool_call_id == "call-1"
    assert failure.partial_messages[-1].content
    assert len(client.requests) == 2
    assert all(request.privacy_class is PrivacyClass.LOCAL_ONLY for request in client.requests)


def test_initial_provider_failure_preserves_prompt_without_tool_side_effects(
    tmp_path: Path,
) -> None:
    failure = ProviderError("Provider unavailable before any tools")

    class UnavailableClient(FakeClient):
        def complete(self, request):
            self.requests.append(request)
            raise failure

    client = UnavailableClient()
    with pytest.raises(ProviderError) as raised:
        AgentLoop(
            client,
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        ).run("Create the file", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert raised.value is failure
    assert failure.partial_messages == (AIMessage(MessageRole.USER, "Create the file"),)
    assert len(client.requests) == 1
    assert not (tmp_path / "out.txt").exists()
