"""OpenAI-compatible Chat Completions provider adapter.

This adapter intentionally targets the Chat Completions protocol because it is
the shared hosted protocol for the initial OpenAI and Requesty coding MVP. The
protocol choice is recorded in ADR-020 so it can be revisited when richer
OpenAI-specific Responses API features are needed.
"""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_provider.config import BackendConfig, ProviderKind, _provider_api_key
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamDelta,
    AIStreamEvent,
    AIStreamFinal,
    AIToolCall,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    ModelCapabilities,
    UsageMetadata,
    UsageSource,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.privacy import enforce_privacy_policy

_DEFAULT_BASE_URLS = {
    ProviderKind.OPENAI: "https://api.openai.com/v1",
    ProviderKind.REQUESTY: "https://router.requesty.ai/v1",
    ProviderKind.GOOGLE: "https://generativelanguage.googleapis.com/v1beta/openai",
}


@dataclass(slots=True)
class OpenAICompatibleChatClient:
    """Chat client for OpenAI-compatible hosted Chat Completions APIs."""

    config: BackendConfig

    @property
    def backend(self) -> BackendInfo:
        """Return hosted backend identity and capabilities."""

        return BackendInfo(
            provider=self.config.provider.value,
            model=self.config.model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        )

    @property
    def base_url(self) -> str:
        """Return the configured hosted API base URL without a trailing slash."""

        return (self.config.base_url or _DEFAULT_BASE_URLS[self.config.provider]).rstrip("/")

    @property
    def api_key(self) -> str:
        """Return the configured API key or raise a configuration error."""

        if self.config.api_key and self.config.api_key.strip():
            return self.config.api_key.strip()
        provider_key = _provider_api_key(self.config.provider)
        if provider_key and provider_key.strip():
            return provider_key.strip()
        raise ProviderError(
            f"{self.config.provider.value} API key is required.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider=self.config.provider.value,
        )

    def complete(self, request: AIRequest) -> AIResponse:
        """Execute a non-streaming Chat Completions request."""

        enforce_privacy_policy(self.backend, request.privacy_class)

        model = request.model or self.config.model
        payload = self._chat_payload(request, stream=False)
        started = time.perf_counter()
        raw_response = self._post_chat(payload)
        latency_ms = (time.perf_counter() - started) * 1000

        return self._response_from_raw(raw_response, model=model, latency_ms=latency_ms)

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        """Execute a streaming Chat Completions request and yield neutral events."""

        enforce_privacy_policy(self.backend, request.privacy_class)

        model = request.model or self.config.model
        payload = self._chat_payload(request, stream=True)
        started = time.perf_counter()
        content_parts: list[str] = []
        final_raw: dict[str, Any] | None = None

        for raw_chunk in self._stream_chat(payload):
            final_raw = raw_chunk
            choice = _first_choice(raw_chunk, provider=self.config.provider.value)
            delta = choice.get("delta")
            if not isinstance(delta, dict):
                delta = {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                content_parts.append(content)
                yield AIStreamDelta(content=content, raw_metadata=raw_chunk)

            if choice.get("finish_reason") is not None:
                latency_ms = (time.perf_counter() - started) * 1000
                final_response = AIResponse(
                    message=AIMessage(
                        role=MessageRole.ASSISTANT,
                        content="".join(content_parts),
                    ),
                    backend=self._backend_for_model(model),
                    usage=self._usage_from_response(raw_chunk),
                    finish_reason=self._finish_reason(choice.get("finish_reason")),
                    latency_ms=latency_ms,
                    raw_metadata=raw_chunk,
                )
                yield AIStreamFinal(response=final_response)
                return

        raise ProviderError(
            "Chat Completions stream ended without a final response object.",
            category=ProviderErrorCategory.RETRYABLE,
            retryable=True,
            provider=self.config.provider.value,
            raw_error=final_raw,
        )

    def _chat_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        if self.config.require_free_model:
            self._verify_free_model(request.model or self.config.model)
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "messages": [_message_to_payload(message) for message in request.messages],
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.tools:
            payload["tools"] = [tool.to_json_schema() for tool in request.tools]
        return payload

    def _verify_free_model(self, model: str) -> None:
        """Fail closed if the exact Requesty model is absent or no longer zero-priced.

        Refresh before every completion/stream, including agent-loop turns. Never
        resolve routing policies or fall back to paid models. This verifies current
        published prices; service account restrictions remain the billing backstop.
        """

        request = Request(f"{self.base_url}/models", headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                catalog = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "Could not verify Requesty free-model prices; inference was not sent.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            ) from exc
        rows = catalog.get("data") if isinstance(catalog, dict) else None
        match = (
            next((row for row in rows if isinstance(row, dict) and row.get("id") == model), None)
            if isinstance(rows, list)
            else None
        )
        if not isinstance(match, dict) or not _zero_price_row(match):
            raise ProviderError(
                f"Requesty model {model!r} is not verified free; inference was not sent.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )

    def _response_from_raw(
        self,
        raw_response: dict[str, Any],
        *,
        model: str,
        latency_ms: float,
    ) -> AIResponse:
        choice = _first_choice(raw_response, provider=self.config.provider.value)
        raw_message = choice.get("message")
        if not isinstance(raw_message, dict):
            raise ProviderError(
                "Chat Completions response did not include a message object.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=raw_response,
            )

        content = raw_message.get("content", "") or ""
        tool_calls = _tool_calls_from_raw(raw_message.get("tool_calls"))
        return AIResponse(
            message=AIMessage(
                role=MessageRole.ASSISTANT, content=str(content), tool_calls=tool_calls
            ),
            backend=self._backend_for_model(model),
            usage=self._usage_from_response(raw_response),
            finish_reason=self._finish_reason(choice.get("finish_reason")),
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw_metadata=raw_response,
        )

    def _backend_for_model(self, model: str) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        )

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Chat Completions response returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Chat Completions request timed out.",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError(
                    "Chat Completions request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider=self.config.provider.value,
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                "Could not connect to Chat Completions provider.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc

    def _stream_chat(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers=self._headers(),
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for line in response:
                    raw_line = line.strip()
                    if not raw_line or raw_line == b"data: [DONE]":
                        continue
                    if raw_line.startswith(b"data: "):
                        raw_line = raw_line.removeprefix(b"data: ")
                    yield json.loads(raw_line.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "Chat Completions stream returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Chat Completions request timed out.",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError(
                    "Chat Completions request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider=self.config.provider.value,
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                "Could not connect to Chat Completions provider.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _http_error(self, exc: HTTPError) -> ProviderError:
        if exc.code in {401, 403}:
            category = ProviderErrorCategory.AUTHENTICATION
        elif exc.code == 429:
            category = ProviderErrorCategory.RATE_LIMIT
        elif 500 <= exc.code < 600:
            category = ProviderErrorCategory.RETRYABLE
        else:
            category = ProviderErrorCategory.NON_RETRYABLE

        return ProviderError(
            f"Chat Completions provider returned HTTP {exc.code}.",
            category=category,
            retryable=category
            in {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.RETRYABLE},
            provider=self.config.provider.value,
            raw_error=exc,
        )

    @staticmethod
    def _usage_from_response(raw_response: dict[str, Any]) -> UsageMetadata:
        raw_usage = raw_response.get("usage")
        if not isinstance(raw_usage, dict):
            return UsageMetadata(source=UsageSource.UNAVAILABLE)

        input_tokens = raw_usage.get("prompt_tokens")
        output_tokens = raw_usage.get("completion_tokens")
        total_tokens = raw_usage.get("total_tokens")
        return UsageMetadata(
            source=UsageSource.PROVIDER_REPORTED,
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) else None,
            total_tokens=total_tokens if isinstance(total_tokens, int) else None,
        )

    @staticmethod
    def _finish_reason(raw_reason: object) -> FinishReason:
        if raw_reason == "stop":
            return FinishReason.STOP
        if raw_reason == "length":
            return FinishReason.LENGTH
        if raw_reason in {"content_filter", "tool_calls", "function_call"}:
            return FinishReason.UNKNOWN
        return FinishReason.UNKNOWN


def _message_to_payload(message: AIMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.name is not None:
        payload["name"] = message.name
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return payload


def _tool_calls_from_raw(raw_calls: object) -> tuple[AIToolCall, ...]:
    if not isinstance(raw_calls, list):
        return ()
    calls: list[AIToolCall] = []
    for index, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function")
        if not isinstance(function, dict):
            continue
        raw_arguments = function.get("arguments", "{}")
        try:
            arguments = (
                json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            )
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            AIToolCall(
                id=str(raw_call.get("id") or f"tool-call-{index}"),
                name=str(function.get("name", "")),
                arguments=arguments,
            )
        )
    return tuple(calls)


def _zero_price_row(row: dict[str, Any]) -> bool:
    """Validate all published token-price tiers without treating missing data as zero."""

    def zero(value: object) -> bool:
        if value is None or isinstance(value, bool):
            return False
        try:
            return Decimal(str(value)) == 0
        except InvalidOperation:
            return False

    tiers = row.get("pricing", [])
    if not isinstance(tiers, list) or row.get("api") != "chat":
        return False
    for prices in [row, *tiers]:
        if not isinstance(prices, dict):
            return False
        if not zero(prices.get("input_price")) or not zero(prices.get("output_price")):
            return False
        if "cached_price" in prices and not zero(prices["cached_price"]):
            return False
    return True


def _first_choice(raw_response: dict[str, Any], *, provider: str) -> dict[str, Any]:
    choices = raw_response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ProviderError(
            "Chat Completions response did not include a choice object.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider=provider,
            raw_error=raw_response,
        )
    return choices[0]
