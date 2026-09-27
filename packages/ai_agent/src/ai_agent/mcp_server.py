"""Minimal MCP stdio server for the repository coding tools."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCall, ToolDefinition
from ai_agent.tools import FindFilesTool, GrepSearchTool, ListDirTool, ReadFileTool, ToolContext
from ai_agent.tools.base import BaseTool, ToolRegistry

READ_SEARCH_TOOLS = ("read_file", "list_dir", "find_files", "grep_search")
PROTOCOL_VERSION = "2025-06-18"


def read_search_tool_registry() -> ToolRegistry:
    """Create the MCP-exposed read/search tool registry."""

    return ToolRegistry(
        tools=(
            ReadFileTool(),
            ListDirTool(),
            FindFilesTool(),
            GrepSearchTool(),
        )
    )


def tool_definition_to_mcp_tool(definition: ToolDefinition) -> dict[str, Any]:
    """Convert an ai-agent tool definition to an MCP tool descriptor."""

    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in definition.parameters:
        properties[parameter.name] = parameter.to_json_schema()
        if parameter.required:
            required.append(parameter.name)
    return {
        "name": definition.name,
        "description": definition.description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
    }


def handle_mcp_message(
    message: dict[str, Any],
    *,
    registry: ToolRegistry,
    context: ToolContext,
) -> dict[str, Any] | None:
    """Handle one JSON-RPC MCP message."""

    message_id = message.get("id")
    method = message.get("method")
    if message_id is None:
        return None
    if not isinstance(method, str):
        return _error_response(message_id, -32600, "Invalid request: method is required.")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "ai-projects-repo-tools",
                    "version": "0.1.0",
                },
                "instructions": (
                    "Use these tools only for read-only repository inspection inside the "
                    "configured workspace. Paths outside the workspace are rejected. "
                    "No write or shell tools are exposed by this MCP server."
                ),
            },
        }
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "tools": [
                    tool_definition_to_mcp_tool(definition)
                    for definition in registry.list_definitions()
                ]
            },
        }
    if method == "tools/call":
        return _handle_tool_call(message_id, message.get("params"), registry, context)
    if method in {"ping", "notifications/initialized"}:
        return {"jsonrpc": "2.0", "id": message_id, "result": {}}
    return _error_response(message_id, -32601, f"Method not found: {method}")


def run_stdio_server(
    *,
    workspace_root: Path,
    input_stream: Iterable[str] = sys.stdin,
    output_stream: Any = sys.stdout,
    registry: ToolRegistry | None = None,
) -> int:
    """Run the JSONL stdio MCP server loop."""

    context = ToolContext(workspace_root=workspace_root.resolve())
    tool_registry = registry or read_search_tool_registry()
    for line in input_stream:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError as exc:
            _write_message(
                output_stream,
                _error_response(None, -32700, f"Parse error: {exc.msg}"),
            )
            continue
        if not isinstance(message, dict):
            _write_message(output_stream, _error_response(None, -32600, "Invalid request."))
            continue
        response = handle_mcp_message(message, registry=tool_registry, context=context)
        if response is not None:
            _write_message(output_stream, response)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the repo tool MCP stdio server."""

    parser = argparse.ArgumentParser(description="Run the AI Projects repository MCP tools.")
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path.cwd(),
        help="Workspace root that MCP tool calls are restricted to.",
    )
    args = parser.parse_args(argv)
    return run_stdio_server(workspace_root=args.workspace_root)


def _handle_tool_call(
    message_id: Any,
    params: Any,
    registry: ToolRegistry,
    context: ToolContext,
) -> dict[str, Any]:
    if not isinstance(params, dict):
        return _error_response(message_id, -32602, "Invalid params: expected object.")
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not name:
        return _error_response(message_id, -32602, "Invalid params: tool name is required.")
    if not isinstance(arguments, dict):
        return _error_response(message_id, -32602, "Invalid params: arguments must be an object.")

    tool: BaseTool | None = registry.get(name)
    if tool is None:
        return _error_response(message_id, -32602, f"Unknown tool: {name}")
    result = tool.run(ToolCall(name=name, arguments=arguments), context)
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "result": {
            "content": [{"type": "text", "text": result.output}],
            "isError": result.is_error,
            "structuredContent": {
                "metadata": result.metadata,
                "tool": result.name,
            },
        },
    }


def _write_message(output_stream: Any, message: dict[str, Any]) -> None:
    output_stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    output_stream.flush()


def _error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    raise SystemExit(main())
