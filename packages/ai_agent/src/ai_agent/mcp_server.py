"""Minimal MCP stdio server for the repository coding tools."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from ai_orchestrator import (
    CostPolicyTier,
    LatencyTarget,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
    derive_subtask_profile,
    load_model_catalog,
    prepare_execution,
)
from ai_orchestrator import (
    PrivacyClass as OrchestratorPrivacyClass,
)
from ai_provider import BackendConfig, PrivacyClass, ProviderKind, create_chat_client

from ai_agent.contracts import ToolCall, ToolDefinition, ToolResult
from ai_agent.loop import AgentLoop
from ai_agent.tools import (
    FindFilesTool,
    GitDiffTool,
    GitStatusTool,
    GrepSearchTool,
    ListDirTool,
    ReadFileTool,
    ToolContext,
)
from ai_agent.tools.base import BaseTool, ToolRegistry
from ai_agent.tools.delegation import DelegateTaskTool

READ_SEARCH_TOOLS = ("read_file", "list_dir", "find_files", "grep_search")
CODEX_MCP_TOOLS = (*READ_SEARCH_TOOLS, "delegate_task")
PROTOCOL_VERSION = "2025-06-18"
DEFAULT_CATALOG_PATH = Path("packages/ai_orchestrator/examples/model_catalog.toml")
DEFAULT_DELEGATION_TIMEOUT_SECONDS = 180.0
DEFAULT_DELEGATION_MAX_ITERATIONS = 8


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


def repo_inspection_tool_registry() -> ToolRegistry:
    """Extend read/search with bounded local Git status and diff inspection."""
    registry = read_search_tool_registry()
    registry.register(GitStatusTool())
    registry.register(GitDiffTool())
    return registry


def codex_mcp_tool_registry(
    *,
    catalog_path: Path,
    timeout_seconds: float = DEFAULT_DELEGATION_TIMEOUT_SECONDS,
    max_iterations: int = DEFAULT_DELEGATION_MAX_ITERATIONS,
) -> ToolRegistry:
    """Create the MCP-exposed registry, including bounded local delegation."""

    registry = read_search_tool_registry()
    registry.register(
        DelegateTaskTool(
            runner=_local_read_only_delegated_task_runner(
                catalog_path=catalog_path,
                timeout_seconds=timeout_seconds,
                max_iterations=max_iterations,
            )
        )
    )
    return registry


def _local_read_only_delegated_task_runner(
    *,
    catalog_path: Path,
    timeout_seconds: float,
    max_iterations: int,
):
    def run(task: str, context: ToolContext) -> ToolResult:
        parent_profile = TaskProfile(
            task_type=TaskType.CODING,
            privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
            cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
        )
        profile = derive_subtask_profile(
            parent=parent_profile,
            task_type=TaskType.CODING,
            required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
            quality_threshold=QualityThreshold.STANDARD,
            latency_target=LatencyTarget.BACKGROUND,
            cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
            privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY,
        )
        catalog = load_model_catalog(catalog_path)
        orchestration = prepare_execution(
            task,
            profile,
            catalog,
            review_prompt=False,
            timeout_seconds=timeout_seconds,
        )
        if not orchestration.is_ready or orchestration.execution_plan is None:
            reason = orchestration.failure_reason or orchestration.status.value
            return ToolResult(
                name="delegate_task",
                output=f"Error: delegated subtask route was not ready: {reason}",
                is_error=True,
            )

        target = orchestration.execution_plan.target
        if target.access_method.value != "local_runtime":
            return ToolResult(
                name="delegate_task",
                output=(
                    "Error: delegated subtask selected a non-local route. "
                    f"route={target.route_id} access_method={target.access_method.value}"
                ),
                is_error=True,
            )

        config = BackendConfig(
            provider=ProviderKind(target.provider),
            model=target.model,
            base_url=target.base_url,
            timeout_seconds=target.timeout_seconds,
        )
        agent = AgentLoop(
            create_chat_client(config),
            read_search_tool_registry(),
            context,
            max_iterations=max_iterations,
        )
        result = agent.run(
            _delegated_task_prompt(task),
            model=config.model,
            privacy_class=PrivacyClass.LOCAL_ONLY,
        )
        failed_count = sum(1 for item in result.tool_results if item.is_error)
        output = "\n".join(
            [
                "Delegated task status: " + ("failed" if failed_count else "completed"),
                f"Route: {target.route_id}",
                f"Model: {target.model}",
                "Tool surface: read/search only; nested delegation, writes, "
                "and shell are disabled.",
                f"Iterations: {result.iterations}",
                f"Tool results: {len(result.tool_results)} total, {failed_count} failed",
                "Child final response:",
                result.response.message.content.strip() or "(empty)",
            ]
        )
        return ToolResult(
            name="delegate_task",
            output=output,
            is_error=failed_count > 0,
            metadata={
                "route_id": target.route_id,
                "model": target.model,
                "iterations": result.iterations,
                "tool_results": len(result.tool_results),
                "child_response": result.response.message.content.strip(),
            },
        )

    return run


def _delegated_task_prompt(task: str) -> str:
    return (
        "You are a bounded local child agent for the repository coding assistant.\n"
        "Use only read/search tools. Do not edit files, run shell commands, choose "
        "architecture, or make product decisions. Return concise findings with file "
        "paths and line references when relevant.\n\n"
        f"Task:\n{task}"
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
            "readOnlyHint": definition.name != "delegate_task",
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
                    "Use these tools only for repository inspection and bounded local "
                    "delegation inside the configured workspace. Paths outside the "
                    "workspace are rejected. The delegate_task tool routes to a local-only "
                    "child agent with read/search tools only. No write or shell tools are "
                    "exposed by this MCP server."
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
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Model catalog used for local-only delegated subtasks.",
    )
    parser.add_argument(
        "--read-search-only",
        action="store_true",
        help="Expose only repository read/search tools; omit model-backed delegation.",
    )
    parser.add_argument(
        "--delegation-timeout-seconds",
        type=float,
        default=DEFAULT_DELEGATION_TIMEOUT_SECONDS,
        help="Provider timeout for local-only delegated subtasks.",
    )
    parser.add_argument(
        "--delegation-max-iterations",
        type=int,
        default=DEFAULT_DELEGATION_MAX_ITERATIONS,
        help="Maximum child-agent tool iterations for delegated subtasks.",
    )
    args = parser.parse_args(argv)
    workspace_root = args.workspace_root.resolve()
    catalog_path = args.catalog if args.catalog.is_absolute() else workspace_root / args.catalog
    return run_stdio_server(
        workspace_root=workspace_root,
        registry=(
            repo_inspection_tool_registry()
            if args.read_search_only
            else codex_mcp_tool_registry(
                catalog_path=catalog_path,
                timeout_seconds=args.delegation_timeout_seconds,
                max_iterations=args.delegation_max_iterations,
            )
        ),
    )


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
                "output": result.output,
                "tool": result.name,
            },
        },
    }


def _write_message(output_stream: Any, message: dict[str, Any]) -> None:
    output_stream.write(json.dumps(message, ensure_ascii=True) + "\n")
    output_stream.flush()


def _error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    raise SystemExit(main())
