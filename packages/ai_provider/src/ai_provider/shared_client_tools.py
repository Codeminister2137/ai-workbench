"""Per-run common inspection mappings, without changing user-wide client settings."""

import json
import sys
from pathlib import Path

from ai_agent.tool_profiles import shared_tool_profile


def inspection_server(workspace: Path) -> dict[str, object]:
    return {
        "command": sys.executable,
        "args": [
            "-m",
            "ai_agent.mcp_server",
            "--workspace-root",
            str(workspace.resolve()),
            "--read-search-only",
        ],
    }


def codex_inspection_overrides(workspace: Path) -> list[str]:
    """Require the server and selected tools; these operations cannot mutate."""
    values = {
        **{
            f"mcp_servers.repo_shared.{key}": value
            for key, value in inspection_server(workspace).items()
        },
        "mcp_servers.repo_shared.enabled": True,
        "mcp_servers.repo_shared.required": True,
        "mcp_servers.repo_shared.enabled_tools": list(shared_tool_profile("inspection").tool_names),
        "mcp_servers.repo_shared.default_tools_approval_mode": "approve",
    }
    return [item for key, value in values.items() for item in ("-c", key + "=" + json.dumps(value))]


def copilot_inspection_options(workspace: Path) -> list[str]:
    tools = shared_tool_profile("inspection").tool_names
    config = {
        "mcpServers": {
            "repo_shared": {"type": "local", **inspection_server(workspace), "tools": list(tools)}
        }
    }
    options = ["--disable-builtin-mcps", "--additional-mcp-config", json.dumps(config)]
    for tool in tools:
        options.extend(["--allow-tool", f"repo_shared({tool})"])
    options.extend(["--available-tools", *["repo_shared-" + tool for tool in tools]])
    return options


def kiro_inspection_agent(workspace: Path, name: str) -> dict[str, object]:
    tools = ["@repo_shared/" + tool for tool in shared_tool_profile("inspection").tool_names]
    return {
        "name": name,
        "description": "Project-owned common inspection tools for this run",
        "prompt": "Use shared repository inspection tools. No edits, shell, network or delegation.",
        "mcpServers": {"repo_shared": inspection_server(workspace)},
        "tools": tools,
        "allowedTools": tools,
        "resources": [],
    }
