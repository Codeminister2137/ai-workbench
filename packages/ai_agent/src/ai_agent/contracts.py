"""Contracts and data structures for agent tools, calls, and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ToolCategory(StrEnum):
    """Broad category defining tool risk and side-effect profile."""

    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    SEARCH = "search"
    CUSTOM = "custom"


class PermissionAction(StrEnum):
    """Decision produced by a permission manager for a tool call."""

    ALLOW = "allow"
    ASK_USER = "ask_user"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ToolParameter:
    """Specification of a single tool argument."""

    name: str
    type_name: str
    description: str
    required: bool = True
    default: Any = None
    enum_values: tuple[str, ...] | None = None

    def to_json_schema(self) -> dict[str, Any]:
        """Convert parameter specification into a standard JSON schema fragment."""
        schema: dict[str, Any] = {
            "type": self.type_name,
            "description": self.description,
        }
        if self.enum_values:
            schema["enum"] = list(self.enum_values)
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Complete specification of a callable tool."""

    name: str
    description: str
    category: ToolCategory
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)

    def to_json_schema(self) -> dict[str, Any]:
        """Export tool definition into standard OpenAI/JSON tool format."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool execution requested by a model."""

    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of executing a single tool call."""

    name: str
    output: str
    call_id: str | None = None
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
