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


def test_agent_loop_carries_provider_continuation_through_tool_result(tmp_path):
    from dataclasses import replace

    from ai_provider import ProviderContinuation

    client = FakeClient()
    complete = client.complete
    state = ProviderContinuation("fake", "test", "local", {"opaque": "private-state"})

    def with_state(request):
        response = complete(request)
        if client.calls == 1:
            return replace(response, message=replace(response.message, continuation=state))
        return response

    client.complete = with_state
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
    ).run("Create the file")
    assert result.response.message.content == "Finished"
    assert client.requests[1].messages[1].continuation is state
    assert client.requests[1].messages[2].role is MessageRole.TOOL
    assert "private-state" not in repr(client.requests[1].messages)
    assert result.messages == (*client.requests[-1].messages, result.response.message)
    assert result.messages[1].continuation is state
    assert "Create the file" not in repr(result)
    assert "private-state" not in repr(result)


def test_agent_loop_executes_tools_and_returns_final_response(tmp_path: Path) -> None:
    client = FakeClient()
    tools = default_coding_tools()
    result = AgentLoop(
        client,
        tools,
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=3,
    ).run("Create the file", privacy_class=PrivacyClass.LOCAL_ONLY)

    assert result.response.message.content == "Finished"
    assert result.iterations == 2
    assert result.tool_results[0].is_error is False
    assert (tmp_path / "out.txt").read_text() == "done"
    # All registered tools are forwarded to the provider request.
    assert len(client.requests[0].tools) == len(tools.list_definitions())
    assert client.requests[1].messages[-1].role is MessageRole.TOOL


def test_shared_process_argv_element_type_survives_provider_translation(tmp_path):
    from ai_provider.foreground_tools import ForegroundTools

    client = FakeClient()
    owner = ForegroundTools(tmp_path)
    try:
        AgentLoop(
            client,
            owner.registry(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        ).run("Create the file")
        for request in client.requests:
            process = next(tool for tool in request.tools if tool.name == "process_start")
            argv = process.to_json_schema()["function"]["parameters"]["properties"]["argv"]
            assert argv["type"] == "array" and argv["items"] == {"type": "string"}
    finally:
        owner.close()


def test_invalid_arguments_get_safe_schema_feedback_and_can_be_corrected(tmp_path):
    class Client(FakeClient):
        def complete(self, request):
            self.requests.append(request)
            self.calls += 1
            if self.calls == 1:
                call = AIToolCall(
                    "bad", "create_file", {"path": "PRIVATE_FILENAME", "content": 123}
                )
            elif self.calls == 2:
                feedback = request.messages[-1].content
                assert "invalid arguments" in feedback and "content: string" in feedback
                assert "unknown" not in feedback and "PRIVATE_FILENAME" not in feedback
                assert not list(tmp_path.iterdir())
                call = AIToolCall("fixed", "create_file", {"path": "out.txt", "content": "done"})
            else:
                return AIResponse(AIMessage(MessageRole.ASSISTANT, "Finished"), self.backend)
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "", tool_calls=(call,)), self.backend
            )

    result = AgentLoop(
        Client(),
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
    ).run("Create one file")
    assert [item.is_error for item in result.tool_results] == [True, False]
    assert (tmp_path / "out.txt").read_text() == "done"
    assert not (tmp_path / "PRIVATE_FILENAME").exists()


@pytest.mark.parametrize("unknown", [False, True])
def test_unknown_tool_and_permission_denial_have_distinct_feedback(tmp_path, unknown):
    class Client(FakeClient):
        def complete(self, request):
            self.calls += 1
            if self.calls > 1:
                return AIResponse(AIMessage(MessageRole.ASSISTANT, "Stopped"), self.backend)
            call = AIToolCall(
                "denied",
                "missing_tool" if unknown else "create_file",
                {"path": "PRIVATE_FILENAME", "content": "PRIVATE_CONTENT"},
            )
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "", tool_calls=(call,)), self.backend
            )

    result = AgentLoop(
        Client(),
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
    ).run("Inspect only")
    feedback = result.tool_results[0].output
    assert result.tool_results[0].is_error
    assert ("unknown tool" in feedback) is unknown
    assert ("not authorized" in feedback) is not unknown
    assert "PRIVATE" not in feedback and not list(tmp_path.iterdir())


def test_iteration_limit_preserves_effect_and_observed_history(tmp_path: Path) -> None:
    from ai_provider import ProviderError, ProviderErrorCategory

    client = FakeClient()
    with pytest.raises(ProviderError, match="exceeded max_iterations=1") as captured:
        AgentLoop(
            client,
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
            max_iterations=1,
        ).run("Create the file", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert captured.value.category is ProviderErrorCategory.NON_RETRYABLE
    assert (tmp_path / "out.txt").read_text() == "done"
    assert captured.value.partial_messages[-1].role is MessageRole.TOOL
    assert captured.value.partial_messages[-1].tool_call_id == "call-1"


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
    # coding_tools_with_delegation adds DelegateTaskTool on top of default_coding_tools.
    assert len(registry.list_definitions()) == len(default_coding_tools().list_definitions()) + 1


@pytest.mark.parametrize("expired_at", ["initial", "response"])
def test_deadline_prevents_initial_request_or_late_response_effects(
    tmp_path, monkeypatch, expired_at
):
    from ai_provider import ProviderErrorCategory

    now = 11.0 if expired_at == "initial" else 0.0

    class LateClient(FakeClient):
        def complete(self, request):
            nonlocal now
            response = super().complete(request)
            now = 11.0
            return response

    monkeypatch.setattr("ai_agent.loop.time.perf_counter", lambda: now)
    client = LateClient()
    with pytest.raises(ProviderError) as raised:
        AgentLoop(
            client,
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
            deadline=10.0,
        ).run("Create the file")
    assert raised.value.category is ProviderErrorCategory.TIMEOUT
    assert len(client.requests) == (0 if expired_at == "initial" else 1)
    assert not (tmp_path / "out.txt").exists()
    assert raised.value.partial_messages


def test_deadline_preserves_first_effect_and_prevents_next_tool_in_response(tmp_path, monkeypatch):
    from ai_agent.tools.filesystem import CreateFileTool
    from ai_provider import ProviderErrorCategory

    now = 0.0
    original = CreateFileTool.execute

    def create(self, arguments, context):
        nonlocal now
        result = original(self, arguments, context)
        now = 11.0
        return result

    class Client(FakeClient):
        def complete(self, request):
            self.requests.append(request)
            return AIResponse(
                AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=tuple(
                        AIToolCall(name, "create_file", {"path": name, "content": name})
                        for name in ("first.txt", "second.txt")
                    ),
                ),
                self.backend,
            )

    monkeypatch.setattr("ai_agent.loop.time.perf_counter", lambda: now)
    monkeypatch.setattr(CreateFileTool, "execute", create)
    client = Client()
    with pytest.raises(ProviderError) as raised:
        AgentLoop(
            client,
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
            deadline=10.0,
        ).run("Create both files")
    assert raised.value.category is ProviderErrorCategory.TIMEOUT
    assert (tmp_path / "first.txt").read_text() == "first.txt"
    assert not (tmp_path / "second.txt").exists()
    assert len(client.requests) == 1
    assert raised.value.partial_messages[-1].role is MessageRole.TOOL
    assert raised.value.partial_messages[-1].tool_call_id == "first.txt"


def test_approval_that_outlasts_deadline_cannot_authorize_effect(tmp_path, monkeypatch):
    from ai_provider import ProviderErrorCategory

    now = 0.0

    def approve(*args):
        nonlocal now
        now = 11.0
        return True

    monkeypatch.setattr("ai_agent.loop.time.perf_counter", lambda: now)
    with pytest.raises(ProviderError) as raised:
        AgentLoop(
            FakeClient(),
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(approval_callback=approve),
            deadline=10.0,
        ).run("Create the file")
    assert raised.value.category is ProviderErrorCategory.TIMEOUT
    assert not (tmp_path / "out.txt").exists()


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_deadline_is_refused_before_any_execution(tmp_path, deadline):
    client = FakeClient()
    with pytest.raises(ValueError, match="deadline must be finite"):
        AgentLoop(client, default_coding_tools(), ToolContext(tmp_path), deadline=deadline)
    assert not client.requests


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


def test_unknown_alias_feedback_uses_current_registry_without_execution(tmp_path):
    from ai_agent.tools.base import ToolRegistry
    from ai_agent.tools.filesystem import ReadFileTool
    from ai_agent.tools.search import GrepSearchTool

    class Client(FakeClient):
        def complete(self, request):
            self.calls += 1
            self.requests.append(request)
            if self.calls == 1:
                call = AIToolCall(
                    "unknown-call",
                    "open_file",
                    {"path": "PRIVATE_ARGUMENT", "content": "PRIVATE_CONTENT"},
                )
                return AIResponse(
                    AIMessage(MessageRole.ASSISTANT, "", tool_calls=(call,)), self.backend
                )
            return AIResponse(AIMessage(MessageRole.ASSISTANT, "Stopped"), self.backend)

    # Reverse insertion order verifies stable names from this registry only.
    registry = ToolRegistry((ReadFileTool(), GrepSearchTool()))
    client = Client()
    result = AgentLoop(
        client,
        registry,
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
    ).run("Inspect only")
    refusal = result.tool_results[0]
    assert refusal.is_error and refusal.call_id == "unknown-call" and refusal.name == "open_file"
    assert "unknown tool 'open_file'" in refusal.output
    assert "Registered tool names: 'grep_search', 'read_file'." in refusal.output
    assert "create_file" not in refusal.output and "PRIVATE" not in refusal.output
    assert "No operation was attempted." in refusal.output
    assert not list(tmp_path.iterdir())
    assert client.requests[1].messages[-1].role is MessageRole.TOOL
    assert client.requests[1].messages[-1].content == refusal.output


def test_empty_registry_unknown_call_retains_safe_refusal_feedback(tmp_path):
    from ai_agent.tools.base import ToolRegistry

    class Client(FakeClient):
        def complete(self, request):
            self.calls += 1
            if self.calls == 1:
                call = AIToolCall("empty-call", "search", {"query": "PRIVATE_QUERY"})
                return AIResponse(
                    AIMessage(MessageRole.ASSISTANT, "", tool_calls=(call,)), self.backend
                )
            return AIResponse(AIMessage(MessageRole.ASSISTANT, "Stopped"), self.backend)

    result = AgentLoop(
        Client(),
        ToolRegistry(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.read_only()),
    ).run("No tools available")
    refusal = result.tool_results[0]
    assert refusal.is_error and refusal.call_id == "empty-call" and refusal.name == "search"
    assert "unknown tool 'search'" in refusal.output
    assert "No tools are registered in this run." in refusal.output
    assert "No operation was attempted." in refusal.output
    assert "PRIVATE" not in refusal.output and "Registered tool names:" not in refusal.output
    assert not list(tmp_path.iterdir())
