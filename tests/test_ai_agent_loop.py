from __future__ import annotations

from pathlib import Path

from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
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
