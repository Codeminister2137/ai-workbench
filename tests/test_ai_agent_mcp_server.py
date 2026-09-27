from pathlib import Path

from ai_agent.mcp_server import (
    handle_mcp_message,
    read_search_tool_registry,
    tool_definition_to_mcp_tool,
)
from ai_agent.tools import ReadFileTool, ToolContext


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
