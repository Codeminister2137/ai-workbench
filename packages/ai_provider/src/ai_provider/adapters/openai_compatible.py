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
            capabilities=ModelCapabilities(chat=True, streaming=True),
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
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        return payload

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

        content = raw_message.get("content", "")
        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content=str(content)),
            backend=self._backend_for_model(model),
            usage=self._usage_from_response(raw_response),
            finish_reason=self._finish_reason(choice.get("finish_reason")),
            latency_ms=latency_ms,
            raw_metadata=raw_response,
        )

    def _backend_for_model(self, model: str) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True),
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
