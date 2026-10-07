"""Read-only diagnostics for the active Python runtime and workspace hints."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext


class PythonRuntimeTool(BaseTool):
    """Report the interpreter running this agent without selecting or executing one."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            "python_runtime",
            (
                "Report the Python interpreter running this agent and workspace environment "
                "hints. This does not switch interpreters or execute workspace code."
            ),
            ToolCategory.READ,
            (),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        del arguments
        workspace = context.workspace_root.resolve()
        project_file = workspace / "pyproject.toml"
        requires_python = None
        if project_file.is_file():
            try:
                project = tomllib.loads(project_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
                raise ValueError(f"Cannot read workspace pyproject.toml: {exc}") from exc
            project_metadata = project.get("project", {})
            if not isinstance(project_metadata, dict):
                raise ValueError("Workspace pyproject.toml [project] must be a table")
            requires_python = project_metadata.get("requires-python")
            if requires_python is not None and not isinstance(requires_python, str):
                raise ValueError("Workspace project.requires-python must be a string")

        venv_python = (
            workspace / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else workspace / ".venv" / "bin" / "python"
        )
        runtime = {
            "executable": str(Path(sys.executable).resolve()),
            "version": sys.version.split()[0],
            "implementation": sys.implementation.name,
            "prefix": str(Path(sys.prefix).resolve()),
            "base_prefix": str(Path(sys.base_prefix).resolve()),
            "in_virtual_environment": sys.prefix != sys.base_prefix,
        }
        hints = {
            "workspace_requires_python": requires_python,
            "workspace_venv_python": str(venv_python) if venv_python.is_file() else None,
            "uv_lock_present": (workspace / "uv.lock").is_file(),
            "workspace_venv_active": Path(sys.prefix).resolve().is_relative_to(workspace),
        }
        details = {"runtime": runtime, "workspace": hints}
        return ToolResult(
            self.definition.name,
            json.dumps(details, indent=2),
            metadata=details,
        )
