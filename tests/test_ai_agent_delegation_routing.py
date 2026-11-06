"""Per-delegation model routing: allowlist + factory, fail-closed."""

from ai_agent.contracts import ToolCall
from ai_agent.delegation_runner import build_child_runner
from ai_agent.delegation_scope import DelegationBudget, DelegationScope
from ai_agent.fanout import FanoutPolicy
from ai_agent.loop import AgentLoop, AgentResult
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tools.base import ToolContext, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool
from ai_agent.tools.filesystem import ReadFileTool
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


def _backend(model: str) -> BackendInfo:
    return BackendInfo(provider="fake", model=model, location=BackendLocation.LOCAL)


def _response(message: AIMessage, model: str = "parent") -> AIResponse:
    return AIResponse(
        message=message,
        backend=_backend(model),
        finish_reason=FinishReason.STOP,
        usage=UsageMetadata(),
    )


class FakeClient:
    def __init__(self, script, model="fake") -> None:
        self.backend = _backend(model)
        self._script = script
        self.calls = 0
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        message = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        return _response(message, self.backend.model)

    def stream(self, request):
        raise NotImplementedError


class FakeLoop:
    def __init__(self, client, registry, context, **kwargs) -> None:
        self.client = client
        self.registry = registry
        self.context = context
        self.result = AgentResult(
            response=_response(AIMessage(MessageRole.ASSISTANT, "child done"))
        )

    def run(self, prompt: str, **kwargs):
        return self.result


def _scope(tmp_path, approved_client, factory=None, allowed=()) -> DelegationScope:
    return DelegationScope(
        registry=ToolRegistry(tools=(ReadFileTool(),)),
        permissions=PermissionManager(),
        workspace=tmp_path,
        budget=DelegationBudget(5),
        approved_client=approved_client,
        client_factory=factory,
        allowed_models=frozenset(allowed),
    )


def _tool(factory_calls, child_clients):
    def factory(client, registry, context, **kwargs):
        child_clients.append(client)
        return FakeLoop(client, registry, context, **kwargs)

    def client_factory(model: str):
        factory_calls.append(model)
        return FakeClient([AIMessage(MessageRole.ASSISTANT, "routed")], model=model)

    runner = build_child_runner(loop_factory=factory)
    return DelegateTaskTool(runner=runner), client_factory


def test_model_override_routes_child_client(tmp_path) -> None:
    factory_calls: list = []
    child_clients: list = []
    tool, client_factory = _tool(factory_calls, child_clients)
    parent = FakeClient([])
    scope = _scope(tmp_path, parent, client_factory, allowed=("codex",))
    registry = ToolRegistry(tools=(tool,))
    result = registry.execute(
        ToolCall("delegate_task", {"task": "do it", "model": "codex"}),
        ToolContext(workspace_root=tmp_path, delegation=scope),
    )
    assert result.is_error is False
    assert factory_calls == ["codex"]
    assert len(child_clients) == 1
    assert child_clients[0].backend.model == "codex"
    assert child_clients[0] is not parent


def test_unknown_model_refused_without_factory_call(tmp_path) -> None:
    factory_calls: list = []
    child_clients: list = []
    tool, client_factory = _tool(factory_calls, child_clients)
    scope = _scope(tmp_path, FakeClient([]), client_factory, allowed=("codex",))
    registry = ToolRegistry(tools=(tool,))
    result = registry.execute(
        ToolCall("delegate_task", {"task": "do it", "model": "evil"}),
        ToolContext(workspace_root=tmp_path, delegation=scope),
    )
    assert result.is_error is True
    assert "not granted" in result.output
    assert factory_calls == []
    assert child_clients == []


def test_model_without_factory_refused(tmp_path) -> None:
    child_clients: list = []
    runner = build_child_runner(loop_factory=FakeLoop)
    tool = DelegateTaskTool(runner=runner)
    scope = _scope(tmp_path, FakeClient([]), None, allowed=("codex",))
    registry = ToolRegistry(tools=(tool,))
    result = registry.execute(
        ToolCall("delegate_task", {"task": "do it", "model": "codex"}),
        ToolContext(workspace_root=tmp_path, delegation=scope),
    )
    assert result.is_error is True
    assert "not configured" in result.output
    assert child_clients == []


def test_default_uses_approved_client(tmp_path) -> None:
    factory_calls: list = []
    child_clients: list = []
    tool, client_factory = _tool(factory_calls, child_clients)
    parent = FakeClient([])
    scope = _scope(tmp_path, parent, client_factory, allowed=("codex",))
    registry = ToolRegistry(tools=(tool,))
    result = registry.execute(
        ToolCall("delegate_task", {"task": "do it"}),
        ToolContext(workspace_root=tmp_path, delegation=scope),
    )
    assert result.is_error is False
    assert factory_calls == []
    assert child_clients == [parent]


def test_unscoped_model_override_refused(tmp_path) -> None:
    factory_calls: list = []
    child_clients: list = []
    tool, _ = _tool(factory_calls, child_clients)
    registry = ToolRegistry(tools=(tool,))
    result = registry.execute(
        ToolCall("delegate_task", {"task": "do it", "model": "codex"}),
        ToolContext(workspace_root=tmp_path),
    )
    assert result.is_error is True
    assert "no host-bound parent authority" in result.output


def test_narrow_resolves_child_backends(tmp_path) -> None:
    _, client_factory = _tool([], [])
    scope = _scope(tmp_path, FakeClient([]), client_factory, allowed=("muse",))
    child = scope.narrow(model="muse")
    assert child.backends == frozenset({("fake", "muse", None)})
    assert child.approved_client is not None
    assert child.approved_client.backend.model == "muse"


def test_parent_loop_end_to_end_routed_delegation(tmp_path) -> None:
    factory_calls: list = []
    child_clients: list = []
    tool, client_factory = _tool(factory_calls, child_clients)
    parent_script = [
        AIMessage(
            MessageRole.ASSISTANT,
            "",
            tool_calls=(
                AIToolCall(
                    "call-1", "delegate_task", {"task": "summarize a.txt", "model": "codex"}
                ),
            ),
        ),
        AIMessage(MessageRole.ASSISTANT, "delegated and done"),
    ]
    parent = FakeClient(parent_script, model="parent")
    scope = _scope(tmp_path, parent, client_factory, allowed=("codex",))
    registry = ToolRegistry(tools=(tool,))
    context = ToolContext(workspace_root=tmp_path, delegation=scope)
    loop = AgentLoop(
        parent,
        registry,
        context,
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=4,
        fanout_policy=FanoutPolicy.ALLOWED,
    )
    result = loop.run("delegate the summary")
    assert result.response.message.content == "delegated and done"
    assert factory_calls == ["codex"]
    assert [c.backend.model for c in child_clients] == ["codex"]
    assert any(
        item.name == "delegate_task" and item.is_error is False for item in result.tool_results
    )
