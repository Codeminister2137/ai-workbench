"""Mai's non-streaming chat client over relay R; no provider access in the worker.

The mailbox transport is injected (``WorkerClient`` from the read-only boundary
mount). Only neutral observable history crosses it. Provider continuation and
raw provider metadata remain host-side; routing and admission are host decisions.
"""

from collections.abc import Iterator
from dataclasses import asdict
from typing import Any, Protocol

from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamEvent,
    AIStreamFinal,
    AIToolCall,
    AIToolDefinition,
    AIToolParameter,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    ModelCapabilities,
    PrivacyClass,
    UsageMetadata,
    UsageSource,
)


class RequestTransport(Protocol):
    def complete_request(self, request: dict[str, Any], *, timeout_s: float) -> dict[str, Any]: ...


def message_payload(message: AIMessage) -> dict[str, Any]:
    """Exclude opaque continuation explicitly rather than serializing secrets."""
    return {
        "role": message.role.value,
        "content": message.content,
        "name": message.name,
        "tool_call_id": message.tool_call_id,
        "tool_calls": [asdict(call) for call in message.tool_calls],
    }


def _message(data: dict[str, Any]) -> AIMessage:
    if not isinstance(data, dict) or set(data) != {
        "role",
        "content",
        "name",
        "tool_call_id",
        "tool_calls",
    }:
        raise ValueError("invalid relay message fields")
    if not isinstance(data["content"], str) or any(
        data[key] is not None and not isinstance(data[key], str) for key in ("name", "tool_call_id")
    ):
        raise ValueError("invalid relay message text")
    if not isinstance(data["tool_calls"], list):
        raise ValueError("invalid relay tool calls")
    calls = []
    for call in data["tool_calls"]:
        if (
            not isinstance(call, dict)
            or set(call) != {"id", "name", "arguments"}
            or not isinstance(call["id"], str)
            or not isinstance(call["name"], str)
            or not isinstance(call["arguments"], dict)
        ):
            raise ValueError("invalid relay tool call")
        calls.append(AIToolCall(**call))
    return AIMessage(
        MessageRole(data["role"]), data["content"], data["name"], data["tool_call_id"], tuple(calls)
    )


def request_payload(request: AIRequest) -> dict[str, Any]:
    if request.model is not None or request.metadata:
        raise ValueError("relay routing and metadata belong to the host")
    return {
        "messages": [message_payload(message) for message in request.messages],
        "tools": [asdict(tool) for tool in request.tools],
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_output_tokens": request.max_output_tokens,
        "privacy_class": request.privacy_class.value,
    }


def decode_request(data: dict[str, Any], *, privacy: PrivacyClass) -> AIRequest:
    """Strict worker-input boundary; privacy is fixed by host scope, never relaxed."""
    if (
        set(data)
        != {"messages", "tools", "temperature", "top_p", "max_output_tokens", "privacy_class"}
        or data["privacy_class"] != privacy.value
    ):
        raise ValueError("invalid relay request fields or privacy scope")
    if not isinstance(data["messages"], list) or not 1 <= len(data["messages"]) <= 128:
        raise ValueError("relay needs 1-128 messages")
    if not isinstance(data["tools"], list) or len(data["tools"]) > 128:
        raise ValueError("invalid relay tools")
    for key, maximum in (("temperature", 2), ("top_p", 1)):
        value = data[key]
        if value is not None and (type(value) not in (float, int) or not 0 <= value <= maximum):
            raise ValueError("invalid relay sampling setting")
    tokens = data["max_output_tokens"]
    if tokens is not None and (type(tokens) is not int or tokens <= 0):
        raise ValueError("invalid relay output bound")
    tools = []
    for tool in data["tools"]:
        if not isinstance(tool, dict) or set(tool) != {"name", "description", "parameters"}:
            raise ValueError("invalid relay tool definition")
        if not isinstance(tool["name"], str) or not isinstance(tool["description"], str):
            raise ValueError("invalid relay tool name")
        if not isinstance(tool["parameters"], list):
            raise ValueError("invalid relay tool parameters")
        parameters = []
        for parameter in tool["parameters"]:
            if not isinstance(parameter, dict):
                raise ValueError("invalid relay tool parameter")
            # Dataclass constructor refuses unknown fields; validate scalar types too.
            parsed = AIToolParameter(**parameter)
            if (
                not all(
                    isinstance(v, str) for v in (parsed.name, parsed.type_name, parsed.description)
                )
                or type(parsed.required) is not bool
                or parsed.item_type_name is not None
                and not isinstance(parsed.item_type_name, str)
                or parsed.enum_values is not None
                and (
                    not isinstance(parsed.enum_values, (list, tuple))
                    or not all(isinstance(v, str) for v in parsed.enum_values)
                )
            ):
                raise ValueError("invalid relay tool parameter")
            parameters.append(parsed)
        tools.append(AIToolDefinition(tool["name"], tool["description"], tuple(parameters)))
    return AIRequest(
        messages=tuple(_message(message) for message in data["messages"]),
        tools=tuple(tools),
        privacy_class=privacy,
        temperature=data["temperature"],
        top_p=data["top_p"],
        max_output_tokens=tokens,
    )


def response_payload(response: AIResponse) -> dict[str, Any]:
    """Return neutral results without endpoint, continuation or raw metadata."""
    return {
        "message": message_payload(response.message),
        "provider": response.backend.provider,
        "model": response.backend.model,
        "location": response.backend.location.value,
        "usage": asdict(response.usage),
        "finish_reason": response.finish_reason.value,
        "latency_ms": response.latency_ms,
        "tool_calls": [asdict(call) for call in response.tool_calls],
    }


class RelayChatClient:
    """Inject into Mai's AgentLoop in the worker; tools execute only there."""

    def __init__(self, transport: RequestTransport, *, timeout_s: float = 300) -> None:
        self.transport = transport
        self.timeout_s = timeout_s
        self._backend = BackendInfo(
            "relay",
            "host-selected",
            BackendLocation.EXTERNAL,
            capabilities=ModelCapabilities(tools=True),
        )

    @property
    def backend(self) -> BackendInfo:
        return self._backend

    def complete(self, request: AIRequest) -> AIResponse:
        result = self.transport.complete_request(request_payload(request), timeout_s=self.timeout_s)
        self._backend = BackendInfo(
            result["provider"],
            result["model"],
            BackendLocation(result["location"]),
            capabilities=ModelCapabilities(tools=True),
        )
        usage = dict(result["usage"])
        usage["source"] = UsageSource(usage["source"])
        return AIResponse(
            message=_message(result["message"]),
            backend=self.backend,
            usage=UsageMetadata(**usage),
            finish_reason=FinishReason(result["finish_reason"]),
            latency_ms=result["latency_ms"],
            tool_calls=tuple(AIToolCall(**call) for call in result["tool_calls"]),
        )

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        yield AIStreamFinal(self.complete(request))
