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
    host_url: str | None = None
    token_env: str | None = None
    available_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ApprovalPolicyPreset(self.approval_policy)
        if not self.task_id or not self.run_id:
            raise ValueError("Shared coding needs task/run identity")


def inspection_server(workspace: Path, run: SharedToolRun | None = None) -> dict[str, object]:
    if run and run.host_url:
        if not run.token_env:
            raise ValueError("Foreground HTTP mapping needs its token environment name")
        return {
            "command": sys.executable,
            "args": [
                "-m",
                "ai_agent.mcp_server",
                "--proxy-url",
                run.host_url,
                "--proxy-token-env",
                run.token_env,
            ],
        }
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
        "mcp_servers.repo_shared.enabled_tools": list(run_tool_names(run, workspace)),
        "mcp_servers.repo_shared.default_tools_approval_mode": "approve",
    }
    if run and run.host_url:
        values["mcp_servers.repo_shared.env_vars"] = [run.token_env]
    return [item for key, value in values.items() for item in ("-c", key + "=" + json.dumps(value))]


def copilot_inspection_options(workspace: Path, run: SharedToolRun | None = None) -> list[str]:
    tools = run_tool_names(run, workspace)
    config = {
        "mcpServers": {
            "repo_shared": {
                "type": "local",
                **inspection_server(workspace, run),
                "tools": list(tools),
            }
        }
    }
    if run and run.host_url and run.token_env:
        config["mcpServers"]["repo_shared"]["env"] = {run.token_env: "${" + run.token_env + "}"}
    options = ["--disable-builtin-mcps", "--additional-mcp-config", json.dumps(config)]
    for tool in tools:
        options.extend(["--allow-tool", f"repo_shared({tool})"])
    options.extend(["--available-tools", *["repo_shared-" + tool for tool in tools]])
    return options


def kiro_inspection_agent(
    workspace: Path, name: str, run: SharedToolRun | None = None
) -> dict[str, object]:
    tools = ["@repo_shared/" + tool for tool in run_tool_names(run, workspace)]
    server = inspection_server(workspace, run)
    if run and run.host_url and run.token_env:
        server["env"] = {run.token_env: "${" + run.token_env + "}"}
    return {
        "name": name,
        "description": "Project-owned common inspection tools for this run",
        "prompt": "Use only the shared project tools and respect their permission decisions."
        if run
        else "Use shared repository inspection tools. No edits, shell, network or delegation.",
        "mcpServers": {"repo_shared": server},
        "tools": tools,
        "allowedTools": tools,
        "resources": [],
    }


def run_tool_names(run: SharedToolRun | None, workspace: Path) -> tuple[str, ...]:
    if run and run.available_tools:
        return run.available_tools
    tools = shared_tool_profile("coding" if run else "inspection").tool_names
    if run and run.host_url:
        tools += ("process_start", "process_status", "process_stop")
    from ai_agent.ide_bridge import CONFIG_PATH, IDE_TOOL_NAMES

    if (workspace / CONFIG_PATH).is_file():
        tools += IDE_TOOL_NAMES
    return tools
