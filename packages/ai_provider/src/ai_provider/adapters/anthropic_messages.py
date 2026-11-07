"""Anthropic Messages API provider adapter.

This is a reusable base for any provider that exposes the Anthropic Messages
protocol. Subclasses typically override ``base_url`` and ``_headers`` to inject
provider-specific endpoint identity, authentication and routing headers.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar

from ai_provider.adapters._responses_base import _ResponsesProtocolBase
from ai_provider.config import _provider_api_key
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
from ai_provider.turn_usage import observe_stream


@dataclass(slots=True)
class AnthropicMessagesChatClient(_ResponsesProtocolBase):
    """Chat client for providers that expose the Anthropic Messages API."""

    _api_version: str = "2023-06-01"

    _api_label: ClassVar[str] = "Messages API"
    _endpoint_path: ClassVar[str] = "/messages"
    _stream_label: ClassVar[str] = "Messages"

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=self.config.model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=False),
        )

    @property
    def base_url(self) -> str:
        return (self.config.base_url or "https://api.anthropic.com/v1").rstrip("/")

    @property
    def api_key(self) -> str:
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

    def _protocol_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        return self._messages_payload(request, stream=stream)

    def _post_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_protocol(payload)

    def _stream_messages(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield from self._stream_protocol(payload)

    @observe_stream
    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        enforce_privacy_policy(self.backend, request.privacy_class)
        model = request.model or self.config.model
        payload = self._messages_payload(request, stream=True)
        started = time.perf_counter()
        content_parts: list[str] = []
        final_raw: dict[str, Any] | None = None
        usage_chunk: dict[str, Any] | None = None
        stop_reason: str | None = None

        for raw_chunk in self._stream_messages(payload):
            event_type = raw_chunk.get("type")
            if event_type == "message_stop":
                continue
            if event_type == "message_start":
                message = raw_chunk.get("message")
                if isinstance(message, dict) and final_raw is None:
                    final_raw = message
                    if isinstance(message.get("usage"), dict):
                        usage_chunk = {"usage": dict(message["usage"])}
                continue
            if event_type == "message_delta":
                usage = raw_chunk.get("usage")
                if isinstance(usage, dict):
                    prior_usage = (usage_chunk or {}).get("usage", {})
                    usage_chunk = {"usage": {**prior_usage, **usage}}
                delta = raw_chunk.get("delta")
                if isinstance(delta, dict):
                    reason = delta.get("stop_reason")
                    if isinstance(reason, str) and reason:
                        stop_reason = reason
                        final_raw = raw_chunk
                elif final_raw is None:
                    final_raw = raw_chunk
                continue
            if event_type == "content_block_delta":
                delta = raw_chunk.get("delta", {})
                if isinstance(delta, dict):
                    text = delta.get("text")
                    if isinstance(text, str) and text:
                        content_parts.append(text)
                        yield AIStreamDelta(
                            content=text, raw_metadata=self._safe_metadata(raw_chunk)
                        )
            if event_type == "message":
                final_raw = raw_chunk

        final_response = AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content="".join(content_parts)),
            backend=self._backend_for_model(model),
            usage=self._usage_from_response(usage_chunk or final_raw or {}),
            finish_reason=(
                self._finish_reason(stop_reason) if stop_reason is not None else FinishReason.STOP
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
            raw_metadata=self._safe_metadata(final_raw or {}),
        )
        yield AIStreamFinal(response=final_response)

    def _messages_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        from ai_provider.credential_guard import enforce_credential_policy

        enforce_credential_policy(
            request, extra=(self.config.api_key, _provider_api_key(self.config.provider))
        )
        # The Messages API accepts only user/assistant roles inside ``messages``;
        # the system prompt must be carried by the top-level ``system`` parameter.
        system_parts = [
            message.content
            for message in request.messages
            if message.role is MessageRole.SYSTEM and message.content
        ]
        messages = [
            self._message_payload(message)
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "messages": messages,
            "max_tokens": (
                request.max_output_tokens if request.max_output_tokens is not None else 4096
            ),
            "stream": stream,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        return payload

    def _response_from_raw(
        self, raw_response: dict[str, Any], *, model: str, latency_ms: float
    ) -> AIResponse:
        content = raw_response.get("content")
        if not isinstance(content, list):
            raise ProviderError(
                "Messages API response did not include a content list.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=raw_response,
            )

        content_parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    content_parts.append(text)

        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content="".join(content_parts)),
            backend=self._backend_for_model(model),
            usage=self._usage_from_response(raw_response),
            finish_reason=self._finish_reason(raw_response.get("stop_reason")),
            latency_ms=latency_ms,
            raw_metadata=self._safe_metadata(raw_response),
        )

    def _backend_for_model(self, model: str) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=False),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": self._api_version,
        }

    def _safe_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw

    @staticmethod
    def _usage_from_response(raw_response: dict[str, Any]) -> UsageMetadata:
        raw_usage = raw_response.get("usage")
        if not isinstance(raw_usage, dict):
            return UsageMetadata(source=UsageSource.UNAVAILABLE)
        input_tokens = raw_usage.get("input_tokens")
        output_tokens = raw_usage.get("output_tokens")
        return UsageMetadata(
            source=UsageSource.PROVIDER_REPORTED,
            input_tokens=input_tokens if type(input_tokens) is int and input_tokens >= 0 else None,
            output_tokens=output_tokens
            if type(output_tokens) is int and output_tokens >= 0
            else None,
            total_tokens=None,
        )

    @staticmethod
    def _finish_reason(raw_reason: object) -> FinishReason:
        if raw_reason in ("end_turn", "stop_sequence"):
            return FinishReason.STOP
        if raw_reason == "max_tokens":
            return FinishReason.LENGTH
        return FinishReason.UNKNOWN
