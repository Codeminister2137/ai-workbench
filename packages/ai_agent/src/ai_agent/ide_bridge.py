"""Read-only project tools over an explicitly imported local PyCharm endpoint."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.http_proxy import validate_loopback_url
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry

CONFIG_PATH = Path("data/pycharm-mcp.json")
PROJECT_HEADER = "IJ_MCP_SERVER_PROJECT_PATH"
IDE_TOOL_NAMES = ("python_environment", "file_diagnostics", "symbol_info")
REMOTE_TOOLS = {
    "python_environment": "get_python_environment",
    "file_diagnostics": "get_file_problems",
    "symbol_info": "get_symbol_info",
}


@dataclass(frozen=True)
class IdeConfiguration:
    url: str
    headers: dict[str, str]

    @classmethod
    def parse(cls, data: Any, workspace: Path) -> IdeConfiguration:
        if not isinstance(data, dict) or set(data) != {"type", "url", "headers"}:
            raise ValueError("Expected copied HTTP Stream type, url and headers")
        if data["type"] != "streamable-http" or not isinstance(data["url"], str):
            raise ValueError("Only explicit local HTTP Stream configuration is supported")
        validate_loopback_url(data["url"])
        headers = data["headers"]
        if not isinstance(headers, dict) or set(headers) != {PROJECT_HEADER}:
            raise ValueError("Only the non-secret PyCharm project-selection header is supported")
        project = headers[PROJECT_HEADER]
        if not isinstance(project, str) or "\r" in project or "\n" in project:
            raise ValueError("Invalid PyCharm project-selection header")
        if Path(project).resolve() != workspace.resolve():
            raise ValueError("PyCharm endpoint configuration belongs to a different workspace")
        return cls(data["url"], dict(headers))

    @classmethod
    def load(cls, workspace: Path) -> IdeConfiguration:
        target = (workspace / CONFIG_PATH).resolve()
        if not target.is_relative_to(workspace.resolve()):
            raise ValueError("IDE configuration path leaves the workspace")
        return cls.parse(json.loads(target.read_text(encoding="utf-8")), workspace)


async def _request(
    config: IdeConfiguration, operation: str | None, arguments: dict[str, Any]
) -> dict[str, Any]:
    """The optional official SDK owns handshake, SSE and session termination."""
    try:
        sdk = importlib.import_module("mcp")
        transport_module = importlib.import_module("mcp.client.streamable_http")
        http = importlib.import_module("httpx2")
    except ImportError as exc:
        raise RuntimeError(
            "Install the ai-agent ide optional extra to use the PyCharm bridge"
        ) from exc
    try:
        async with http.AsyncClient(
            headers=config.headers, timeout=30, trust_env=False, follow_redirects=False
        ) as http_client:
            transport = transport_module.streamable_http_client(config.url, http_client=http_client)
            async with sdk.Client(transport) as client:
                listed = await client.list_tools()
                available = {tool.name for tool in listed.tools}
                if operation is None:
                    return {name: remote in available for name, remote in REMOTE_TOOLS.items()}
                remote = REMOTE_TOOLS[operation]
                if remote not in available:
                    raise ValueError(f"PyCharm does not expose the required tool: {remote}")
                result = await client.call_tool(remote, arguments)
                return {
                    "output": "\n".join(
                        block.text for block in result.content if block.type == "text"
                    ),
                    "is_error": result.is_error,
                    "metadata": result.structured_content or {},
                }
    except ValueError:
        raise
    except Exception as exc:
        # Transport/task-group errors must not print endpoint headers or SDK internals.
        raise RuntimeError(
            "Cannot communicate with the configured local PyCharm MCP endpoint"
        ) from exc


class IdeTool(BaseTool):
    """Fixed allowlist; neither arbitrary IDE tools nor refactors are forwarded."""

    def __init__(self, operation: str, configuration: IdeConfiguration, workspace: Path):
        self.operation, self.configuration, self.workspace = (
            operation,
            configuration,
            workspace.resolve(),
        )

    @property
    def definition(self) -> ToolDefinition:
        parameters = [ToolParameter("path", "string", "File inside the configured workspace")]
        if self.operation == "symbol_info":
            parameters += [
                ToolParameter("line", "integer", "One-based line number"),
                ToolParameter("column", "integer", "One-based column number"),
            ]
        return ToolDefinition(
            self.operation,
            "Read " + self.operation.replace("_", " ") + " from the configured local IDE",
            ToolCategory.READ,
            tuple(parameters),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.workspace_root.resolve() != self.workspace:
            raise ValueError("IDE bridge workspace changed")
        path = context.resolve_path(arguments["path"])
        if not context.is_within_workspace(path) or not path.is_file():
            raise ValueError("IDE file must exist inside the workspace")
        remote_arguments: dict[str, Any] = {"filePath": path.relative_to(self.workspace).as_posix()}
        if self.operation == "symbol_info":
            for name in ("line", "column"):
                value = arguments[name]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError("Symbol positions must be positive one-based integers")
                remote_arguments[name] = value
        result = asyncio.run(_request(self.configuration, self.operation, remote_arguments))
        return ToolResult(self.operation, **result)


def add_ide_tools(registry: ToolRegistry, workspace: Path) -> None:
    if (workspace / CONFIG_PATH).is_file():
        config = IdeConfiguration.load(workspace)
        for operation in IDE_TOOL_NAMES:
            registry.register(IdeTool(operation, config, workspace))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import/check this machine's PyCharm MCP settings")
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument("--import-config", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    workspace = args.workspace_root.resolve()
    try:
        if args.import_config:
            data = json.loads(args.import_config.read_text(encoding="utf-8"))
            IdeConfiguration.parse(data, workspace)
            target = workspace / CONFIG_PATH
            if not target.resolve().is_relative_to(workspace):
                raise ValueError("IDE configuration path leaves the workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w" if args.replace else "x", encoding="utf-8") as output:
                output.write(json.dumps(data, indent=2) + "\n")
            print("Imported machine-local PyCharm configuration")
        if args.check:
            print(json.dumps(asyncio.run(_request(IdeConfiguration.load(workspace), None, {}))))
        if not args.import_config and not args.check:
            parser.error("Select --import-config or --check")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"PyCharm bridge unavailable: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
