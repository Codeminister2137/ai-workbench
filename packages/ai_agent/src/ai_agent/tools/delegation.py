"""Delegation tool for routing bounded subtasks to a child agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from ai_agent.contracts import ToolCategory, ToolDefinition, ToolParameter, ToolResult
from ai_agent.fanout import FanoutPolicy
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
    fanout: FanoutPolicy = FanoutPolicy.ALLOWED

    def __post_init__(self) -> None:
        object.__setattr__(self, "fanout", FanoutPolicy.coerce(self.fanout))

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delegate_task",
            description=(
                "Delegate coding within the host-bound parent authority and shared budget. "
                "Use this for scoped inspection, implementation and validation when granted. "
                "A model request cannot escalate the supervisor's actual authority: "
                "unknown or unconfigured models are refused."
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
                ToolParameter(
                    name="permission_profile",
                    type_name="string",
                    description=(
                        "Optional child permission profile; omit or use 'default' "
                        "to inherit actual parent permissions, or request a "
                        "narrower profile; never escalates parent authority."
                    ),
                    required=False,
                    enum_values=(
                        "inherit",
                        "default",
                        "read_only",
                        "interactive",
                        "workspace_write",
                        "trusted_local",
                    ),
                ),
                ToolParameter(
                    name="allowed_tools",
                    type_name="array",
                    description="Optional narrower tool names.",
                    required=False,
                    item_type_name="string",
                ),
                ToolParameter(
                    name="allowed_paths",
                    type_name="array",
                    description=(
                        "Optional workspace-relative file-tool paths; commands require "
                        "an explicit command set when paths are narrowed."
                    ),
                    required=False,
                    item_type_name="string",
                ),
                ToolParameter(
                    name="allowed_commands",
                    type_name="array",
                    description=(
                        "Optional exact permitted command strings; does not grant "
                        "OS isolation or broader parent privileges."
                    ),
                    required=False,
                    item_type_name="string",
                ),
                ToolParameter(
                    name="model",
                    type_name="string",
                    description=(
                        "Optional child model route from the host allowlist; "
                        "refused when not granted or unconfigured."
                    ),
                    required=False,
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
        if not self.fanout.allows_spawn:
            # Host-level gate for the unscoped path below; the scoped path is
            # additionally refused by DelegationScope.narrow().
            return ToolResult(
                name=self.definition.name,
                output=(f"Error: run fan-out policy is {self.fanout.value}: child spawn refused."),
                is_error=True,
            )
        scope = context.delegation
        overrides = {
            name: arguments.get(name)
            for name in ("allowed_tools", "allowed_paths", "allowed_commands")
        }
        profile = arguments.get("permission_profile", "inherit")
        if profile == "default":
            profile = "inherit"
        model = arguments.get("model")
        if scope is None:
            if (
                profile != "inherit"
                or model is not None
                or any(value is not None for value in overrides.values())
            ):
                return ToolResult(
                    self.definition.name,
                    "Error: no host-bound parent authority for permission overrides.",
                    is_error=True,
                )
            return self.runner(task.strip(), context)
        try:
            child = scope.narrow(
                profile=profile,
                tools=tuple(overrides["allowed_tools"])
                if overrides["allowed_tools"] is not None
                else None,
                paths=tuple(overrides["allowed_paths"])
                if overrides["allowed_paths"] is not None
                else None,
                commands=tuple(overrides["allowed_commands"])
                if overrides["allowed_commands"] is not None
                else None,
                model=model,
            )
            with scope.budget.child():
                return self.runner(task.strip(), replace(context, delegation=child))
        except ValueError as error:
            return ToolResult(self.definition.name, "Error: " + str(error), is_error=True)


def coding_tools_with_delegation(
    runner: DelegatedTaskRunner,
    *,
    fanout: FanoutPolicy | str = FanoutPolicy.ALLOWED,
) -> ToolRegistry:
    """Return the default coding registry plus the bounded delegation tool."""
    from ai_agent.tools import default_coding_tools

    registry = default_coding_tools()
    registry.register(DelegateTaskTool(runner=runner, fanout=FanoutPolicy.coerce(fanout)))
    return registry
