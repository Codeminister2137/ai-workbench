from pathlib import Path
from types import SimpleNamespace

from ai_agent import mcp_server as _MCP_SERVER
from ai_agent.mcp_server import (
    codex_mcp_tool_registry,
    handle_mcp_message,
    read_search_tool_registry,
    tool_definition_to_mcp_tool,
)
from ai_agent.tools import ReadFileTool, ToolContext
from ai_orchestrator import AccessMethod


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
    assert listed is not None
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert tool_names == {"read_file", "list_dir", "find_files", "grep_search"}
    assert "run_command" not in tool_names


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

    monkeypatch.setattr(_MCP_SERVER, "load_model_catalog", lambda path: ())
    monkeypatch.setattr(_MCP_SERVER, "prepare_execution", lambda *args, **kwargs: orchestration)
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
    assert "Delegated task status: completed" in text
    assert "Route: local-child" in text
    assert "Tool surface: read/search only" in text
    assert "child findings" in text


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
