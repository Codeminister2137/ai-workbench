"""Provider-neutral multi-turn tool execution loop."""

from __future__ import annotations

from dataclasses import dataclass
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
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        self.client = client
        self.registry = registry
        self.context = context
        self.permissions = permissions or PermissionManager()
        self.max_iterations = max_iterations

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
            try:
                response = self.client.complete(
                    AIRequest(
                        messages=tuple(messages),
                        model=model,
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
            tool_calls = response.tool_calls or response.message.tool_calls
            if not tool_calls:
                return AgentResult(
                    response=response, tool_results=tuple(tool_results), iterations=iteration
                )

            for call in tool_calls:
                agent_call = ToolCall(name=call.name, arguments=call.arguments, call_id=call.id)
                tool = self.registry.get(call.name)
                if tool is None or not self.permissions.check_and_authorize(tool, agent_call):
                    result = ToolResult(
                        name=call.name,
                        output=f"Error: tool call {call.name!r} was not authorized or is unknown.",
                        call_id=call.id,
                        is_error=True,
                    )
                else:
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

        raise RuntimeError(f"Agent loop exceeded max_iterations={self.max_iterations}")


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
            )
            for parameter in definition.parameters
        ),
    )
