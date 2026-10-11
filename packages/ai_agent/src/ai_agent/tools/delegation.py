"""Delegation tool for routing bounded subtasks to a child agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.tools.base import BaseTool, ToolContext, ToolRegistry

DelegatedTaskRunner = Callable[[str, ToolContext], ToolResult]


def unavailable_delegation(task: str, context: ToolContext) -> ToolResult:
    """Expose a capability without granting unconfigured model execution."""
    return ToolResult(
        name="delegate_task",
        output="Error: bounded local delegation is not configured for this execution scope.",
        is_error=True,
    )


@dataclass(frozen=True, slots=True)
class DelegateTaskTool(BaseTool):
    """Tool that lets a primary agent delegate bounded coding subtasks."""

    runner: DelegatedTaskRunner

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delegate_task",
            description=(
                "Delegate bounded coding support to a local read-only child model. "
                "Use this for file inspection, source summarization or test-case drafting. "
                "Architecture, implementation decisions and edits remain with the primary."
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
