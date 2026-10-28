"""Shell tool for executing system and terminal commands."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext
from ai_agent.validation_process import run_validation_process


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

        env = context.command_environment()

        # On Windows, run in powershell; on Unix, run with default shell
        if sys.platform == "win32":
            shell_cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            shell_cmd = ["/bin/sh", "-c", command]

        try:
            completed = run_validation_process(
                shell_cmd,
                cwd=target_cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # Keep useful progress bounded; never render the exception's command args.
            progress: list[str] = []
            for label, value in (("", exc.stdout), ("[STDERR]\n", exc.stderr)):
                if value:
                    decoded = value.decode(errors="replace") if isinstance(value, bytes) else value
                    progress.append(label + decoded[-16_000:].strip())
            progress.append(f"Error: Command timed out after {timeout_seconds} seconds.")
            return ToolResult(
                name="run_command",
                output="\n\n".join(progress),
                is_error=True,
                metadata={"command": command, "timeout": timeout_seconds},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name="run_command",
                output=f"Error running command ({type(exc).__name__}); execution did not complete.",
                is_error=True,
                metadata={"command": command},
            )

        # Match subprocess text-mode universal newlines after file-backed capture.
        stdout = completed.stdout.replace("\r\n", "\n").replace("\r", "\n").strip()
        stderr = completed.stderr.replace("\r\n", "\n").replace("\r", "\n").strip()
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
