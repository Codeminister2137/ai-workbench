"""Base abstractions and registry for agent tools."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_agent.contracts import ToolCall, ToolDefinition, ToolResult


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Execution context provided to tools during runtime."""

    workspace_root: Path
    env: dict[str, str] = field(default_factory=dict)

    def resolve_path(self, relative_or_absolute: Path | str) -> Path:
        """Resolve a path safely against workspace root."""
        path = Path(relative_or_absolute)
        if path.is_absolute():
            return path.resolve()
        return (self.workspace_root / path).resolve()

    def is_within_workspace(self, target_path: Path | str) -> bool:
        """Check if a path is located inside the workspace root."""
        resolved = self.resolve_path(target_path)
        try:
            resolved.relative_to(self.workspace_root.resolve())
            return True
        except ValueError:
            return False


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return tool metadata, documentation, and parameter schema."""
        ...

    @abstractmethod
    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """Execute the tool with validated arguments and return the result."""
        ...

    def run(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """Run the tool for a ToolCall request."""
        try:
            self.validate_arguments(call.arguments)
            result = self.execute(call.arguments, context)
            if result.call_id is None and call.call_id is not None:
                return ToolResult(
                    name=result.name,
                    output=result.output,
                    call_id=call.call_id,
                    is_error=result.is_error,
                    metadata=result.metadata,
                )
            return result
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                name=self.definition.name,
                output=f"Error executing tool {self.definition.name}: {exc}",
                call_id=call.call_id,
                is_error=True,
            )

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Enforce declared parameter types before approval or side effects.

        Unknown keys remain allowed, matching the published schemas. Tools own
        semantic bounds and array item validation beyond these simple contracts.
        """
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object")
        types = {
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
            "array": list,
            "object": dict,
        }
        for parameter in self.definition.parameters:
            if parameter.name not in arguments:
                if parameter.required:
                    raise ValueError(f"Missing required parameter: {parameter.name}")
                continue
            value = arguments[parameter.name]
            expected = types.get(parameter.type_name)
            if expected is None or not isinstance(value, expected):
                raise ValueError(f"Parameter {parameter.name} must be {parameter.type_name}")
            if parameter.type_name in {"integer", "number"} and (
                isinstance(value, bool) or not math.isfinite(value)
            ):
                raise ValueError(f"Parameter {parameter.name} must be a finite number")
            if parameter.enum_values is not None and value not in parameter.enum_values:
                raise ValueError(f"Invalid value for parameter {parameter.name}")

    def approval_call(self, call: ToolCall) -> ToolCall | None:
        """Return the exact operation to show for approval, or refuse approval."""
        return call


class ToolRegistry:
    """Registry managing available tools and their schema exports."""

    def __init__(self, tools: tuple[BaseTool, ...] = ()) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """Register a new tool."""
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def list_definitions(self) -> tuple[ToolDefinition, ...]:
        """List definitions of all registered tools."""
        return tuple(tool.definition for tool in self._tools.values())

    def export_json_schemas(self) -> list[dict[str, Any]]:
        """Export all registered tool schemas in OpenAI/JSON format."""
        return [tool.definition.to_json_schema() for tool in self._tools.values()]

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """Execute a ToolCall by looking up the tool in the registry."""
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(
                name=call.name,
                output=f"Error: Unknown tool {call.name!r}",
                call_id=call.call_id,
                is_error=True,
            )
        return tool.run(call, context)
