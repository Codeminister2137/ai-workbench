"""Shared delegation routing, privacy and invocation lifetime without inference."""

import time

import pytest
from ai_agent import mcp_server
from ai_agent.contracts import ToolCall
from ai_agent.tool_profiles import shared_tool_registry
from ai_agent.tools import ToolContext
from ai_orchestrator import PrivacyClass as RoutingPrivacy
from ai_orchestrator import TaskProfile
from ai_provider import AIMessage, AIResponse, AIToolCall, BackendInfo, BackendLocation, MessageRole
from ai_provider.foreground_tools import ForegroundTools


def child_catalog(tmp_path):
    path = tmp_path / "catalog.toml"
    path.write_text("""[[models]]
route_id = "selected-child"
provider = "ollama"
product = "ollama"
model = "child-model"
location = "local"
access_method = "local_runtime"
auth_method = "none"
billing_source = "local_free"
cost_policy_tier = "local_only"
quality = "standard"
latency = "background"
base_url = "http://localhost:11434"
[models.capabilities]
chat = true
tools = true
""")
    return path


def test_unconfigured_shared_delegation_refuses_without_inference(tmp_path):
    registry = shared_tool_registry("coding")
    result = registry.execute(
        ToolCall("delegate_task", {"task": "Summarize source"}), ToolContext(tmp_path)
    )
    assert result.is_error and "not configured" in result.output
    assert shared_tool_registry("inspection").get("delegate_task") is None


@pytest.mark.parametrize("privacy", list(RoutingPrivacy))
def test_shared_child_uses_selected_catalog_and_inherits_privacy(monkeypatch, tmp_path, privacy):
    seen = []
    configs = []

    class Client:
        backend = BackendInfo("ollama", "child-model", BackendLocation.LOCAL)

        def complete(self, request):
            seen.append(request)
            return AIResponse(AIMessage(MessageRole.ASSISTANT, "Source findings"), self.backend)

    def factory(config):
        configs.append(config)
        return Client()

    monkeypatch.setattr(mcp_server, "create_chat_client", factory)
    runner = mcp_server._local_read_only_delegated_task_runner(
        catalog_path=child_catalog(tmp_path),
        parent_profile=TaskProfile(privacy_class=privacy),
        timeout_seconds=30,
        max_iterations=2,
        is_active=lambda: True,
        deadline=time.perf_counter() + 5,
    )
    result = runner("Summarize source", ToolContext(tmp_path))
    assert not result.is_error and "selected-child" in result.output
    assert seen[0].privacy_class.value == privacy.value
    assert {tool.name for tool in seen[0].tools} == {
        "read_file",
        "find_files",
        "list_dir",
        "grep_search",
    }
    assert all(
        config.model == "child-model" and 0 < config.timeout_seconds <= 5 for config in configs
    )


def test_revoked_child_response_cannot_read_files_or_make_another_request(monkeypatch, tmp_path):
    active = True
    requests = []
    (tmp_path / "source.txt").write_text("private sentinel")

    class Client:
        backend = BackendInfo("ollama", "child-model", BackendLocation.LOCAL)

        def complete(self, request):
            nonlocal active
            requests.append(request)
            active = False
            return AIResponse(
                AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(AIToolCall("read", "read_file", {"path": "source.txt"}),),
                ),
                self.backend,
            )

    monkeypatch.setattr(mcp_server, "create_chat_client", lambda config: Client())
    runner = mcp_server._local_read_only_delegated_task_runner(
        catalog_path=child_catalog(tmp_path),
        timeout_seconds=30,
        max_iterations=2,
        is_active=lambda: active,
    )
    from ai_agent.tools.delegation import DelegateTaskTool

    result = DelegateTaskTool(runner).run(
        ToolCall("delegate_task", {"task": "Inspect source.txt"}), ToolContext(tmp_path)
    )
    assert result.is_error and "scope expired" in result.output
    assert "private sentinel" not in result.output
    assert len(requests) == 1


@pytest.mark.parametrize("expired", ["revoked", "deadline"])
def test_expired_child_scope_does_not_load_catalog_or_model(monkeypatch, tmp_path, expired):
    def forbidden(*args, **kwargs):
        pytest.fail("Expired scope attempted routing or model access")

    monkeypatch.setattr(mcp_server, "load_model_catalog", forbidden)
    monkeypatch.setattr(mcp_server, "create_chat_client", forbidden)
    runner = mcp_server._local_read_only_delegated_task_runner(
        catalog_path=tmp_path / "unused.toml",
        timeout_seconds=30,
        max_iterations=2,
        is_active=lambda: expired != "revoked",
        deadline=time.perf_counter() - 1 if expired == "deadline" else None,
    )
    result = runner("Inspect source", ToolContext(tmp_path))
    assert result.is_error and "scope expired" in result.output


def test_foreground_delegation_factory_receives_invocation_scope(tmp_path):
    foreground = ForegroundTools(tmp_path)
    observed = []
    from ai_agent.tools.delegation import unavailable_delegation

    def factory(active, deadline):
        observed.append((active, deadline))
        return unavailable_delegation

    foreground.delegation_factory = factory

    def active():
        return False

    try:
        assert foreground.registry(is_active=active, deadline=123).get("delegate_task")
        assert observed == [(active, 123)]
    finally:
        foreground.close()


@pytest.mark.parametrize("with_invocation", [False, True])
def test_child_deadline_stops_later_tools_in_same_model_response(
    monkeypatch, tmp_path, with_invocation
):
    from ai_agent.tools.delegation import DelegateTaskTool
    from ai_agent.tools.filesystem import ReadFileTool

    now = 0.0
    reads = []
    requests = []
    (tmp_path / "first.txt").write_text("first evidence")
    (tmp_path / "second.txt").write_text("must not be read after deadline")
    original_read = ReadFileTool.execute

    def read(self, arguments, context):
        nonlocal now
        reads.append(arguments["path"])
        result = original_read(self, arguments, context)
        now = 11.0
        return result

    class Client:
        backend = BackendInfo("ollama", "child-model", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            return AIResponse(
                AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall("first", "read_file", {"path": "first.txt"}),
                        AIToolCall("second", "read_file", {"path": "second.txt"}),
                    ),
                ),
                self.backend,
            )

    monkeypatch.setattr(mcp_server.time, "perf_counter", lambda: now)
    monkeypatch.setattr(mcp_server, "create_chat_client", lambda config: Client())
    monkeypatch.setattr(ReadFileTool, "execute", read)
    runner = mcp_server._local_read_only_delegated_task_runner(
        catalog_path=child_catalog(tmp_path),
        timeout_seconds=30,
        max_iterations=3,
        is_active=(lambda: True) if with_invocation else None,
        deadline=10.0,
    )
    result = DelegateTaskTool(runner).run(
        ToolCall("delegate_task", {"task": "Inspect both files"}), ToolContext(tmp_path)
    )
    assert result.is_error and "scope expired" in result.output
    assert reads == ["first.txt"]
    assert len(requests) == 1


def test_child_scope_expiring_during_catalog_load_stops_before_planning(monkeypatch, tmp_path):
    now = 0.0
    catalog = child_catalog(tmp_path)
    load_catalog = mcp_server.load_model_catalog

    def load(path):
        nonlocal now
        result = load_catalog(path)
        now = 11.0
        return result

    def forbidden(*args, **kwargs):
        pytest.fail("Expired scope attempted planning or client creation")

    monkeypatch.setattr(mcp_server.time, "perf_counter", lambda: now)
    monkeypatch.setattr(mcp_server, "load_model_catalog", load)
    monkeypatch.setattr(mcp_server, "prepare_execution", forbidden)
    monkeypatch.setattr(mcp_server, "create_chat_client", forbidden)
    runner = mcp_server._local_read_only_delegated_task_runner(
        catalog_path=catalog, timeout_seconds=30, max_iterations=3, deadline=10.0
    )
    result = runner("Inspect source", ToolContext(tmp_path))
    assert result.is_error and "scope expired" in result.output


def test_shared_http_delegation_reads_source_and_records_scoped_receipt(monkeypatch, tmp_path):
    from ai_agent.http_proxy import HttpMcpConnection
    from ai_orchestrator import AccessMethod
    from ai_provider.external_agents import ExternalAgentConfig

    (tmp_path / "source.txt").write_text("source evidence")
    requests = []

    class Client:
        backend = BackendInfo("ollama", "child-model", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            if len(requests) == 1:
                message = AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(AIToolCall("read", "read_file", {"path": "source.txt"}),),
                )
            else:
                assert "source evidence" in request.messages[-1].content
                message = AIMessage(MessageRole.ASSISTANT, "Verified source findings")
            return AIResponse(message, self.backend)

    monkeypatch.setattr(mcp_server, "create_chat_client", lambda config: Client())
    catalog = child_catalog(tmp_path)
    foreground = ForegroundTools(tmp_path)
    foreground.delegation_factory = lambda active, deadline: (
        mcp_server._local_read_only_delegated_task_runner(
            catalog_path=catalog,
            timeout_seconds=30,
            max_iterations=3,
            is_active=active,
            deadline=deadline,
        )
    )
    config = ExternalAgentConfig(
        AccessMethod.CODEX_CLI,
        "synthetic-client",
        "parent-model",
        tmp_path,
        30,
        approval_policy="trusted_local",
        shared_tool_profile="coding",
        shared_task_id="parent-task",
        shared_run_id="parent-turn",
    )
    try:
        with foreground.invocation(config, deadline=time.perf_counter() + 10) as scoped:
            assert "delegate_task" in scoped.shared_available_tools
            assert scoped.shared_child_env is not None and scoped.shared_token_env is not None
            assert scoped.shared_host_url is not None
            connection = HttpMcpConnection(
                scoped.shared_host_url, scoped.shared_child_env[scoped.shared_token_env]
            )
            assert connection.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            connection.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            reply = connection.send(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "delegate_task",
                        "arguments": {"task": "Summarize source.txt"},
                    },
                }
            )
            assert reply is not None
            result = reply["result"]
            assert not result["isError"], result["content"]
            assert "Verified source findings" in result["content"][0]["text"]
            receipt = result["structuredContent"]["metadata"]["shared_receipt"]
            assert receipt["task_id"] == "parent-task" and receipt["run_id"] == "parent-turn"
            assert receipt["authorized"] and "source evidence" not in str(receipt)
            assert len(requests) == 2
    finally:
        foreground.close()
