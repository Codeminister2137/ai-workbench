"""Shell tool for executing system and terminal commands."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext


class RunCommandTool(BaseTool):
    """Tool for running shell commands in the workspace."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_command",
            description=(
                "Execute a shell command (PowerShell on Windows, shell on POSIX) and return output."
            ),
            category=ToolCategory.SHELL,
            parameters=(
                ToolParameter(
                    name="command",
                    type_name="string",
                    description="The command line string to execute.",
                    required=True,
                ),
                ToolParameter(
                    name="cwd",
                    type_name="string",
                    description="Working directory for the command (default: workspace root).",
                    required=False,
                    default=".",
                ),
                ToolParameter(
                    name="timeout_seconds",
                    type_name="number",
                    description="Execution timeout in seconds (default: 60.0).",
                    required=False,
                    default=60.0,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        command = arguments.get("command")
        raw_cwd = arguments.get("cwd", ".")
        timeout_seconds = float(arguments.get("timeout_seconds", 60.0))

        if not isinstance(command, str) or not command.strip():
            return ToolResult(
                name="run_command",
                output="Error: 'command' parameter is required.",
                is_error=True,
            )

        target_cwd = context.resolve_path(raw_cwd)
        if not context.is_within_workspace(target_cwd):
            return ToolResult(
                name="run_command",
                output=f"Error: Working directory {raw_cwd!r} is outside workspace boundary.",
                is_error=True,
            )

        env = os.environ.copy()
        env.update(context.env)

        # On Windows, run in powershell; on Unix, run with default shell
        if sys.platform == "win32":
            shell_cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["/bin/sh", "-c", command]

        try:
            completed = subprocess.run(
                shell_cmd,
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                name="run_command",
                output=f"Error: Command timed out after {timeout_seconds} seconds.",
                is_error=True,
                metadata={"command": command, "timeout": timeout_seconds},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="run_command",
                output=f"Error running command: {exc}",
                is_error=True,
                metadata={"command": command},
            )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        exit_code = completed.returncode

        output_parts: list[str] = []
        if stdout:
            output_parts.append(stdout)
        if stderr:
            output_parts.append(f"[STDERR]\n{stderr}")
        if exit_code != 0:
            output_parts.append(f"[Process exited with code {exit_code}]")

        combined_output = "\n\n".join(output_parts) if output_parts else "(No output)"
        is_error = exit_code != 0

        return ToolResult(
            name="run_command",
            output=combined_output,
            is_error=is_error,
            metadata={
                "command": command,
                "exit_code": exit_code,
                "cwd": str(target_cwd),
            },
        )
