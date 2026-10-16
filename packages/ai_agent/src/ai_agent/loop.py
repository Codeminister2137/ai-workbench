"""Provider-neutral multi-turn tool execution loop."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from ai_provider import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIToolDefinition,
    AIToolParameter,
    ChatClient,
    MessageRole,
    PrivacyClass,
    ProviderError,
    ProviderErrorCategory,
)

from ai_agent.contracts import ToolCall, ToolResult
from ai_agent.permissions import PermissionManager
from ai_agent.tools.base import ToolContext, ToolRegistry


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Final response and tool execution history from an agent run."""

    response: AIResponse
    tool_results: tuple[ToolResult, ...] = ()
    iterations: int = 1
    # Transient only, like ProviderError.partial_messages; never log/persist raw continuation.
    messages: tuple[AIMessage, ...] = field(default=(), repr=False, compare=False)


class AgentLoop:
    """Run model responses and authorized tool calls until the model finishes."""

    def __init__(
        self,
        client: ChatClient,
        registry: ToolRegistry,
        context: ToolContext,
        *,
        permissions: PermissionManager | None = None,
        max_iterations: int = 10,
        deadline: float | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if deadline is not None and not math.isfinite(deadline):
            raise ValueError("deadline must be finite")
        self.client = client
        self.registry = registry
        self.context = context
        self.permissions = permissions or PermissionManager()
        self.max_iterations = max_iterations
        self.deadline = deadline
        self.temperature = temperature
        self.top_p = top_p

    def _check_deadline(self, messages: list[AIMessage]) -> None:
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            error = ProviderError(
                "Agent deadline expired; earlier effects remain and must be inspected.",
                category=ProviderErrorCategory.TIMEOUT,
                provider=self.client.backend.provider,
            )
            error.partial_messages = tuple(messages)
            raise error

    def run(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY,
    ) -> AgentResult:
        """Execute a prompt and any requested tools until a final answer is returned."""
        messages: list[AIMessage] = []
        if system_prompt:
            messages.append(AIMessage(MessageRole.SYSTEM, system_prompt))
        messages.append(AIMessage(MessageRole.USER, prompt))
        tool_results: list[ToolResult] = []

        for iteration in range(1, self.max_iterations + 1):
            self._check_deadline(messages)
            try:
                response = self.client.complete(
                    AIRequest(
                        messages=tuple(messages),
                        model=model,
                        temperature=self.temperature,
                        top_p=self.top_p,
                        privacy_class=privacy_class,
                        tools=tuple(
                            _tool_definition(tool) for tool in self.registry.list_definitions()
                        ),
                    )
                )
            except ProviderError as exc:
                exc.partial_messages = tuple(messages)
                raise
            messages.append(response.message)
            self._check_deadline(messages)
            tool_calls = response.tool_calls or response.message.tool_calls
            if not tool_calls:
                return AgentResult(
                    response=response,
                    tool_results=tuple(tool_results),
                    iterations=iteration,
                    messages=tuple(messages),
                )

            for call in tool_calls:
                self._check_deadline(messages)
                agent_call = ToolCall(name=call.name, arguments=call.arguments, call_id=call.id)
                tool = self.registry.get(call.name)
                if tool is None:
                    registered_names = sorted(t.name for t in self.registry.list_definitions())
                    names_str = ", ".join(repr(name) for name in registered_names)
                    registry_detail = (
                        f"Registered tool names: {names_str}."
                        if registered_names
                        else "No tools are registered in this run."
                    )
                    result = ToolResult(
                        name=call.name,
                        output=(
                            f"Error: unknown tool {call.name!r}. {registry_detail} "
                            "No operation was attempted."
                        ),
                        call_id=call.id,
                        is_error=True,
                    )
                elif not self.permissions.check_and_authorize(tool, agent_call):
                    try:
                        tool.validate_arguments(agent_call.arguments)
                    except (ValueError, OverflowError):
                        # Schema metadata is safe feedback; argument values and exception
                        # text may contain private data and must not be echoed here.
                        schema = ", ".join(
                            f"{parameter.name}: {parameter.type_name}"
                            + (" (required)" if parameter.required else "")
                            for parameter in tool.definition.parameters
                        )
                        refusal = (
                            f"Error: invalid arguments for tool {call.name!r}. "
                            f"Expected schema: {schema}. No operation attempted."
                        )
                    else:
                        refusal = (
                            f"Error: tool call {call.name!r} was not authorized. "
                            "No operation attempted."
                        )
                    result = ToolResult(
                        name=call.name,
                        output=refusal,
                        call_id=call.id,
                        is_error=True,
                    )
                else:
                    self._check_deadline(messages)
                    result = tool.run(agent_call, self.context)
                tool_results.append(result)
                messages.append(
                    AIMessage(
                        role=MessageRole.TOOL,
                        content=result.output,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
                self._check_deadline(messages)

        error = ProviderError(
            f"Agent loop exceeded max_iterations={self.max_iterations}; "
            "earlier tool effects remain and must be inspected before continuing.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=self.client.backend.provider,
        )
        error.partial_messages = tuple(messages)
        raise error


def _tool_definition(definition: Any) -> AIToolDefinition:
    return AIToolDefinition(
        name=definition.name,
        description=definition.description,
        parameters=tuple(
            AIToolParameter(
                name=parameter.name,
                type_name=parameter.type_name,
                description=parameter.description,
                required=parameter.required,
                default=parameter.default,
                enum_values=parameter.enum_values,
                item_type_name=getattr(parameter, "item_type_name", None),
            )
            for parameter in definition.parameters
        ),
    )
