"""Per-run shared tool mappings, without changing user-wide client settings."""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from ai_agent.permissions import ApprovalPolicyPreset
from ai_agent.tool_profiles import shared_tool_profile


@dataclass(frozen=True)
class SharedToolRun:
    """Runtime-only mapping; it never grants permissions through saved client settings."""

    task_id: str
    run_id: str
    approval_policy: str
    terminal_approvals: bool = False
    session_database: Path | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        ApprovalPolicyPreset(self.approval_policy)
        if not self.task_id or not self.run_id:
            raise ValueError("Shared coding needs task/run identity")


def inspection_server(workspace: Path, run: SharedToolRun | None = None) -> dict[str, object]:
    extra = ["--read-search-only"]
    if run:
        from ai_provider.acceptance_processes import process_identity

        birth = process_identity(os.getpid())
        if not birth:
            raise ValueError("Shared coding owner identity cannot be verified")
        extra = [
            "--shared-profile",
            "coding",
            "--approval-policy",
            run.approval_policy,
            "--task-id",
            run.task_id,
            "--run-id",
            run.run_id,
            "--owner-pid",
            str(os.getpid()),
            "--owner-birth",
            birth,
        ]
        if run.terminal_approvals:
            extra.append("--terminal-approvals")
        if run.session_database is not None:
            extra.extend(
                [
                    "--session-database",
                    str(run.session_database),
                    "--session-id",
                    str(run.session_id),
                ]
            )
    return {
        "command": sys.executable,
        "args": [
            "-m",
            "ai_agent.mcp_server",
            "--workspace-root",
            str(workspace.resolve()),
            *extra,
        ],
    }


def codex_inspection_overrides(workspace: Path, run: SharedToolRun | None = None) -> list[str]:
    """Require selected tools; the coding server enforces scoped mutation policy."""
    values = {
        **{
            f"mcp_servers.repo_shared.{key}": value
            for key, value in inspection_server(workspace, run).items()
        },
        "mcp_servers.repo_shared.enabled": True,
        "mcp_servers.repo_shared.required": True,
        "mcp_servers.repo_shared.enabled_tools": list(
            shared_tool_profile("coding" if run else "inspection").tool_names
        ),
        "mcp_servers.repo_shared.default_tools_approval_mode": "approve",
    }
    return [item for key, value in values.items() for item in ("-c", key + "=" + json.dumps(value))]


def copilot_inspection_options(workspace: Path, run: SharedToolRun | None = None) -> list[str]:
    tools = shared_tool_profile("coding" if run else "inspection").tool_names
    config = {
        "mcpServers": {
            "repo_shared": {
                "type": "local",
                **inspection_server(workspace, run),
                "tools": list(tools),
            }
        }
    }
    options = ["--disable-builtin-mcps", "--additional-mcp-config", json.dumps(config)]
    for tool in tools:
        options.extend(["--allow-tool", f"repo_shared({tool})"])
    options.extend(["--available-tools", *["repo_shared-" + tool for tool in tools]])
    return options


def kiro_inspection_agent(
    workspace: Path, name: str, run: SharedToolRun | None = None
) -> dict[str, object]:
    tools = [
        "@repo_shared/" + tool
        for tool in shared_tool_profile("coding" if run else "inspection").tool_names
    ]
    return {
        "name": name,
        "description": "Project-owned common inspection tools for this run",
        "prompt": "Use only the shared project tools and respect their permission decisions."
        if run
        else "Use shared repository inspection tools. No edits, shell, network or delegation.",
        "mcpServers": {"repo_shared": inspection_server(workspace, run)},
        "tools": tools,
        "allowedTools": tools,
        "resources": [],
    }
