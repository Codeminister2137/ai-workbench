"""Delegation tool for routing bounded subtasks to a child agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry

DelegatedTaskRunner = Callable[[str, ToolContext], ToolResult]


@dataclass(frozen=True, slots=True)
class DelegateTaskTool(BaseTool):
    """Tool that lets a primary agent delegate bounded coding subtasks."""

    runner: DelegatedTaskRunner

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delegate_task",
            description=(
                "Delegate a bounded coding subtask to a cheaper/local child model. "
                "Use this for focused file inspection, small code edits, test-case "
                "drafting, or verification steps that do not need the primary model."
            ),
            category=ToolCategory.CUSTOM,
            parameters=(
                ToolParameter(
                    name="task",
                    type_name="string",
                    description=(
                        "Specific subtask for the child model, including files, expected "
                        "output, and any write boundaries."
                    ),
                    required=True,
                ),
            ),
        )

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        task = arguments.get("task")
        if not isinstance(task, str) or not task.strip():
            return ToolResult(
                name=self.definition.name,
                output="Error: 'task' parameter is required.",
                is_error=True,
            )
        return self.runner(task.strip(), context)


def coding_tools_with_delegation(runner: DelegatedTaskRunner) -> ToolRegistry:
    """Return the default coding registry plus the bounded delegation tool."""
    from ai_agent.tools import default_coding_tools

    registry = default_coding_tools()
    registry.register(DelegateTaskTool(runner=runner))
    return registry
