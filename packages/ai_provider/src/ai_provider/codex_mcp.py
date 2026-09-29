"""Helpers for configuring Codex MCP access to repository-local tools."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_provider.external_agents import default_codex_command

CODEX_MCP_SERVER_NAME = "repo_assistant_tools"
CODEX_MCP_ENABLED_TOOLS = (
    "read_file",
    "list_dir",
    "find_files",
    "grep_search",
    "delegate_task",
)


@dataclass(frozen=True, slots=True)
class CodexMcpSetupResult:
    """Result of writing project-scoped Codex MCP configuration."""

    config_path: Path
    server_name: str
    command: str
    args: tuple[str, ...]
    enabled_tools: tuple[str, ...]
    created: bool
    global_registered: bool = False
    global_add_stdout: str = ""
    global_add_stderr: str = ""


def setup_project_codex_mcp(
    repo_root: Path,
    *,
    server_name: str = CODEX_MCP_SERVER_NAME,
    register_global: bool = True,
    codex_command: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CodexMcpSetupResult:
    """Create/update Codex MCP config for repo inspection and delegation tools."""

    repo_root = repo_root.resolve()
    config_path = repo_root / ".codex" / "config.toml"
    command = sys.executable
    args = (
        "-m",
        "ai_agent.mcp_server",
        "--workspace-root",
        str(repo_root),
    )
    block = _mcp_server_config_block(
        server_name=server_name,
        repo_root=repo_root,
        command=command,
        args=args,
        enabled_tools=CODEX_MCP_ENABLED_TOOLS,
    )
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    updated = _replace_or_append_mcp_server_block(original, server_name, block)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(updated, encoding="utf-8")
    global_registered = False
    add_stdout = ""
    add_stderr = ""
    if register_global:
        add_result = register_global_codex_mcp(
            repo_root,
            server_name=server_name,
            codex_command=codex_command,
            runner=runner,
        )
        global_registered = add_result.returncode == 0
        add_stdout = add_result.stdout or ""
        add_stderr = add_result.stderr or ""
        if not global_registered:
            raise RuntimeError(
                "Failed to register Codex MCP server: "
                + (add_stderr.strip() or add_stdout.strip() or f"exit {add_result.returncode}")
            )
    return CodexMcpSetupResult(
        config_path=config_path,
        server_name=server_name,
        command=command,
        args=args,
        enabled_tools=CODEX_MCP_ENABLED_TOOLS,
        created=not bool(original),
        global_registered=global_registered,
        global_add_stdout=add_stdout.strip(),
        global_add_stderr=add_stderr.strip(),
    )


def register_global_codex_mcp(
    repo_root: Path,
    *,
    server_name: str = CODEX_MCP_SERVER_NAME,
    codex_command: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    """Register the repo MCP server with the official Codex MCP CLI."""

    command = codex_command or default_codex_command()
    if command is None:
        raise FileNotFoundError(
            "Could not find Codex CLI. Set CODEX_COMMAND or install/configure Codex CLI."
        )
    runner(
        (command, "mcp", "remove", server_name),
        text=True,
        capture_output=True,
        timeout=30,
        cwd=repo_root,
    )
    return runner(
        build_codex_mcp_add_command(repo_root, server_name=server_name, codex_command=command),
        text=True,
        capture_output=True,
        timeout=60,
        cwd=repo_root,
    )


def build_codex_mcp_add_command(
    repo_root: Path,
    *,
    server_name: str = CODEX_MCP_SERVER_NAME,
    codex_command: str,
) -> tuple[str, ...]:
    """Build the official `codex mcp add` command for repo read/search tools."""

    return (
        codex_command,
        "mcp",
        "add",
        server_name,
        "--",
        sys.executable,
        "-m",
        "ai_agent.mcp_server",
        "--workspace-root",
        str(repo_root.resolve()),
    )


def _mcp_server_config_block(
    *,
    server_name: str,
    repo_root: Path,
    command: str,
    args: tuple[str, ...],
    enabled_tools: tuple[str, ...],
) -> str:
    return "\n".join(
        [
            f"[mcp_servers.{server_name}]",
            f"command = {_toml_string(command)}",
            f"args = {_toml_array(args)}",
            f"cwd = {_toml_string(str(repo_root))}",
            "enabled = true",
            "required = false",
            'default_tools_approval_mode = "auto"',
            "startup_timeout_sec = 10",
            "tool_timeout_sec = 60",
            f"enabled_tools = {_toml_array(enabled_tools)}",
            "",
        ]
    )


def _replace_or_append_mcp_server_block(text: str, server_name: str, block: str) -> str:
    stripped = text.rstrip()
    if not stripped:
        return block
    pattern = re.compile(rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}\]\n.*?(?=^\[|\Z)")
    if pattern.search(text):
        return pattern.sub(lambda _match: block, text).rstrip() + "\n"
    return stripped + "\n\n" + block


def _toml_array(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
