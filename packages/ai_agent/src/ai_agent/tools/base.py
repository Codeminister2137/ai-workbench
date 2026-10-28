"""Base abstractions and registry for agent tools."""

from __future__ import annotations

import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_provider.credential_guard import contains_credentials

if TYPE_CHECKING:
    from ai_agent.delegation_scope import DelegationScope

from ai_agent.contracts import ToolCall, ToolDefinition, ToolResult
from ai_agent.tools.credential_paths import is_credential_path


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Execution context provided to tools during runtime."""

    workspace_root: Path
    env: dict[str, str] = field(default_factory=dict)
    delegation: DelegationScope | None = field(default=None, repr=False, compare=False)
    inherit_environment: bool = True
    credential_secrets: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def command_environment(self) -> dict[str, str]:
        """Preserve ordinary parent behavior; delegated processes get a host allowlist."""
        allowed = {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "LANG",
            "LC_ALL",
        }
        environment = (
            os.environ.copy()
            if self.inherit_environment
            else {name: value for name, value in os.environ.items() if name.upper() in allowed}
        )
        environment.update(self.env)
        return environment

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
        call_id = (
            None
            if contains_credentials(call.call_id, extra=context.credential_secrets)
            else call.call_id
        )
        try:
            self.validate_arguments(call.arguments)
            if contains_credentials(call.arguments, extra=context.credential_secrets):
                return ToolResult(
                    name=self.definition.name,
                    output="Credential-bearing tool arguments refused; no operation was attempted.",
                    call_id=call_id,
                    is_error=True,
                )
            if self.definition.name in {
                "read_file",
                "create_file",
                "edit_file",
                "list_dir",
                "find_files",
                "grep_search",
            }:
                raw_path = call.arguments.get("path", ".")
                if isinstance(raw_path, str) and (
                    is_credential_path(Path(raw_path))
                    or is_credential_path(context.resolve_path(raw_path))
                ):
                    return ToolResult(
                        name=self.definition.name,
                        output=(
                            "Credential-file operation refused; no file operation was attempted."
                        ),
                        call_id=call_id,
                        is_error=True,
                    )
            result = self.execute(call.arguments, context)
        except Exception as exc:  # noqa: BLE001
            result = ToolResult(
                name=self.definition.name,
                output=f"Error executing tool {self.definition.name}: {exc}",
                call_id=call_id,
                is_error=True,
            )
        if result.call_id is None and call_id is not None:
            result = replace(result, call_id=call_id)
        if contains_credentials(result, extra=context.credential_secrets):
            return ToolResult(
                name=self.definition.name,
                output=(
                    "Credential-bearing tool output withheld. Effects may already have occurred; "
                    "inspect locally before continuing."
                ),
                call_id=call_id,
                is_error=True,
                metadata={"credential_output_refused": True},
            )
        return result

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
