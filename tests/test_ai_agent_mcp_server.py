from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from ai_agent import mcp_server as _MCP_SERVER
from ai_agent.mcp_server import (
    codex_mcp_tool_registry,
    handle_mcp_message,
    read_search_tool_registry,
    tool_definition_to_mcp_tool,
)
from ai_agent.tools import CreateFileTool, ReadFileTool, ToolContext
from ai_orchestrator import AccessMethod, TaskCapability


def test_mcp_initialize_and_tools_list(tmp_path: Path) -> None:
    registry = read_search_tool_registry()
    context = ToolContext(workspace_root=tmp_path)

    initialized = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        registry=registry,
        context=context,
    )
    listed = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        registry=registry,
        context=context,
    )

    assert initialized is not None
    assert initialized["result"]["capabilities"] == {"tools": {}}
    assert "No write or shell tools" in initialized["result"]["instructions"]
    assert "delegate_task" not in initialized["result"]["instructions"]
    assert listed is not None
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert tool_names == {"read_file", "list_dir", "find_files", "grep_search"}
    assert "run_command" not in tool_names


def test_write_definition_is_not_annotated_read_only() -> None:
    descriptor = tool_definition_to_mcp_tool(CreateFileTool().definition)
    assert descriptor["annotations"]["readOnlyHint"] is False


def test_read_search_only_entrypoint_omits_model_backed_delegation(monkeypatch, tmp_path):
    captured = []

    def serve(*, workspace_root, registry):
        captured.extend(tool.name for tool in registry.list_definitions())
        assert workspace_root == tmp_path
        return 0

    monkeypatch.setattr(_MCP_SERVER, "run_stdio_server", serve)
    monkeypatch.setattr(
        _MCP_SERVER,
        "codex_mcp_tool_registry",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("delegation registry created")),
    )
    assert _MCP_SERVER.main(["--workspace-root", str(tmp_path), "--read-search-only"]) == 0
    assert captured == [
        "read_file",
        "list_dir",
        "find_files",
        "grep_search",
        "git_status",
        "git_diff",
    ]


def test_codex_mcp_registry_includes_bounded_delegate_task(tmp_path: Path) -> None:
    registry = codex_mcp_tool_registry(catalog_path=tmp_path / "catalog.toml")
    context = ToolContext(workspace_root=tmp_path)

    initialized = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        registry=registry,
        context=context,
    )
    listed = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        registry=registry,
        context=context,
    )

    assert initialized is not None
    assert (
        "local-only child agent with read/search tools only"
        in initialized["result"]["instructions"]
    )
    assert listed is not None
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert set(tools) == {"read_file", "list_dir", "find_files", "grep_search", "delegate_task"}
    assert tools["delegate_task"]["annotations"]["readOnlyHint"] is False
    assert tools["delegate_task"]["annotations"]["destructiveHint"] is False
    assert "run_command" not in tools


def test_mcp_tools_call_runs_workspace_bounded_tool(tmp_path: Path) -> None:
    (tmp_path / "source.txt").write_text("first\nsecond\n", encoding="utf-8")
    registry = read_search_tool_registry()

    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "read_file",
                "arguments": {"path": "source.txt", "start_line": 2},
            },
        },
        registry=registry,
        context=ToolContext(workspace_root=tmp_path),
    )

    assert response is not None
    assert response["result"]["isError"] is False
    assert "   2 | second" in response["result"]["content"][0]["text"]


def test_mcp_write_message_escapes_non_ascii_for_stdio_transport() -> None:
    output = StringIO()

    _MCP_SERVER._write_message(  # noqa: SLF001 - regression for stdio transport encoding.
        output,
        {"jsonrpc": "2.0", "id": 1, "result": {"text": "non-breaking hyphen: \u2011"}},
    )

    text = output.getvalue()
    assert "\\u2011" in text
    assert "\u2011" not in text


def test_mcp_delegate_task_runs_local_read_only_child_agent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FakeAgentLoop:
        def __init__(self, client, registry, context, *, max_iterations):
            self.client = client
            self.registry = registry
            self.context = context
            self.max_iterations = max_iterations

        def run(self, prompt, *, model, privacy_class):
            return SimpleNamespace(
                response=SimpleNamespace(message=SimpleNamespace(content="child findings")),
                iterations=1,
                tool_results=(),
            )

    target = SimpleNamespace(
        route_id="local-child",
        access_method=AccessMethod.LOCAL_RUNTIME,
        provider="ollama",
        model="child-model",
        base_url="http://localhost:11434",
        timeout_seconds=30.0,
    )
    orchestration = SimpleNamespace(
        is_ready=True,
        execution_plan=SimpleNamespace(target=target),
        failure_reason=None,
        status=SimpleNamespace(value="ready"),
    )
    captured_profile = None

    def fake_prepare_execution(prompt, profile, *args, **kwargs):
        nonlocal captured_profile
        captured_profile = profile
        return orchestration

    monkeypatch.setattr(_MCP_SERVER, "load_model_catalog", lambda path: ())
    monkeypatch.setattr(_MCP_SERVER, "prepare_execution", fake_prepare_execution)
    monkeypatch.setattr(_MCP_SERVER, "create_chat_client", lambda config: object())
    monkeypatch.setattr(_MCP_SERVER, "AgentLoop", FakeAgentLoop)
    registry = codex_mcp_tool_registry(catalog_path=tmp_path / "catalog.toml")

    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "delegate_task", "arguments": {"task": "Summarize README.md"}},
        },
        registry=registry,
        context=ToolContext(workspace_root=tmp_path),
    )

    assert response is not None
    assert response["result"]["isError"] is False
    text = response["result"]["content"][0]["text"]
    structured = response["result"]["structuredContent"]
    assert "Delegated task status: completed" in text
    assert "Route: local-child" in text
    assert "Tool surface: read/search only" in text
    assert "child findings" in text
    assert structured["output"] == text
    assert structured["metadata"]["child_response"] == "child findings"
    assert captured_profile is not None
    assert captured_profile.required_capabilities == frozenset(
        {TaskCapability.CHAT, TaskCapability.TOOLS}
    )


def test_mcp_tools_call_rejects_unknown_or_outside_workspace_tool(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    registry = read_search_tool_registry()
    context = ToolContext(workspace_root=tmp_path)

    unknown = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "run_command", "arguments": {"command": "echo no"}},
        },
        registry=registry,
        context=context,
    )
    outside_read = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": str(outside)}},
        },
        registry=registry,
        context=context,
    )

    assert unknown is not None
    assert unknown["error"]["message"] == "Unknown tool: run_command"
    assert outside_read is not None
    assert outside_read["result"]["isError"] is True
    assert "outside the allowed workspace boundary" in outside_read["result"]["content"][0]["text"]


def test_mcp_tool_descriptor_uses_mcp_input_schema() -> None:
    descriptor = tool_definition_to_mcp_tool(ReadFileTool().definition)

    assert descriptor["name"] == "read_file"
    assert "inputSchema" in descriptor
    assert descriptor["inputSchema"]["properties"]["path"]["type"] == "string"
    assert descriptor["annotations"]["readOnlyHint"] is True
