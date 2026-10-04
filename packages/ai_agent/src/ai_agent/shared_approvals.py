"""Per-call shared permissions; terminal input is separate from MCP transport."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolResult
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry


class TerminalApproval:
    """Ask once for this exact operation; never read model-controlled stdio."""

    def __init__(self, task_id: str, run_id: str, workspace: Path):
        self.task_id, self.run_id, self.workspace = task_id, run_id, workspace.resolve()

    def __call__(self, call: ToolCall, category: ToolCategory) -> bool:
        operation = json.dumps({"tool": call.name, "arguments": call.arguments}, ensure_ascii=True)
        if len(operation) > 64000:
            return False  # Never shorten the operation the human is being asked to approve.
        reader_name, writer_name = (
            ("CONIN$", "CONOUT$") if os.name == "nt" else ("/dev/tty", "/dev/tty")
        )
        try:
            with (
                open(reader_name, encoding="utf-8") as reader,
                open(writer_name, "w", encoding="utf-8") as writer,
            ):
                if not reader.isatty() or not writer.isatty():
                    return False
                writer.write(
                    json.dumps(
                        {
                            "task": self.task_id,
                            "run": self.run_id,
                            "workspace": str(self.workspace),
                            "category": category.value,
                        }
                    )
                    + "\n"
                    + operation
                    + "\nApprove this operation once? [yes/NO] "
                )
                writer.flush()
                return reader.readline().strip().lower() == "yes"
        except (OSError, EOFError, KeyboardInterrupt):
            return False


class ScopedTool(BaseTool):
    """Retain the original tool boundary, with operation-scoped observed receipts."""

    def __init__(
        self,
        tool: BaseTool,
        permissions: PermissionManager,
        workspace: Path,
        task_id: str,
        run_id: str,
        is_active: Callable[[], bool] | None = None,
    ):
        self.tool, self.permissions = tool, permissions
        self.workspace, self.task_id, self.run_id = workspace.resolve(), task_id, run_id
        self.is_active = is_active or (lambda: True)

    @property
    def definition(self) -> ToolDefinition:
        return self.tool.definition

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.workspace_root.resolve() != self.workspace:
            raise ValueError("Shared approval workspace changed")
        call = ToolCall(self.definition.name, arguments)
        authorized = self.is_active() and self.permissions.check_and_authorize(self.tool, call)
        # The owner may exit while the human is considering the request.
        authorized = authorized and self.is_active()
        result = (
            self.tool.run(call, context)
            if authorized
            else ToolResult(
                self.definition.name,
                "Permission denied: no scoped approval for this operation",
                is_error=True,
            )
        )
        receipt = {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "workspace": str(self.workspace),
            "operation": self.definition.name,
            "category": self.definition.category.value,
            "authorized": authorized,
            "is_error": result.is_error,
            "arguments_sha256": hashlib.sha256(
                json.dumps(arguments, sort_keys=True).encode()
            ).hexdigest(),
            "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
            "observed_at_utc": datetime.now(UTC).isoformat(),
        }
        return replace(result, metadata={**result.metadata, "shared_receipt": receipt})


def scoped_registry(
    registry: ToolRegistry,
    permissions: PermissionManager,
    workspace: Path,
    task_id: str,
    run_id: str,
    is_active: Callable[[], bool] | None = None,
) -> ToolRegistry:
    if not task_id or not run_id:
        raise ValueError("Shared coding requires task and run identity")
    return ToolRegistry(
        tuple(
            ScopedTool(tool, permissions, workspace, task_id, run_id, is_active)
            for definition in registry.list_definitions()
            if (tool := registry.get(definition.name))
        )
    )
