"""OpenAI Responses API provider adapter.

This is a reusable base for any provider that exposes the OpenAI Responses
protocol. Subclasses typically override ``base_url`` and ``_headers`` to inject
provider-specific endpoint identity, authentication and routing headers.
"""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from ai_provider.config import BackendConfig, _provider_api_key
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
    ProviderContinuation,
    UsageMetadata,
    UsageSource,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory, ToolCallFormatError
from ai_provider.http_transport import urlopen
from ai_provider.privacy import enforce_privacy_policy
from ai_provider.turn_usage import observe_completion, observe_stream, observe_usage


@dataclass(slots=True)
class OpenAIResponsesChatClient:
    """Chat client for providers that expose the OpenAI Responses API."""

    config: BackendConfig

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=self.config.model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        )

    @property
    def base_url(self) -> str:
        return (self.config.base_url or "https://api.openai.com/v1").rstrip("/")

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

    @observe_completion
    def complete(self, request: AIRequest) -> AIResponse:
        enforce_privacy_policy(self.backend, request.privacy_class)
        model = request.model or self.config.model
        payload = self._responses_payload(request, stream=False)
        started = time.perf_counter()
        raw_response = self._post_responses(payload)
        if isinstance(raw_response, dict):
            observe_usage(self._usage_from_response(raw_response))
        latency_ms = (time.perf_counter() - started) * 1000
        return self._response_from_raw(raw_response, model=model, latency_ms=latency_ms)

    @observe_stream
    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        enforce_privacy_policy(self.backend, request.privacy_class)
        model = request.model or self.config.model
        payload = self._responses_payload(request, stream=True)
        started = time.perf_counter()
        content_parts: list[str] = []
        final_raw: dict[str, Any] | None = None
        last_raw: dict[str, Any] | None = None
        streamed_items: dict[int, dict[str, Any]] = {}

        for raw_chunk in self._stream_responses(payload):
            last_raw = raw_chunk
            if raw_chunk.get("type") in {"error", "response.failed"}:
                raw_failure = raw_chunk.get("response", raw_chunk)
                self._raise_response_failure(raw_failure)
            if raw_chunk.get("type") == "response.output_item.done":
                item = raw_chunk.get("item")
                index = raw_chunk.get("output_index", len(streamed_items))
                if isinstance(item, dict) and type(index) is int and index >= 0:
                    streamed_items[index] = item
            if raw_chunk.get("type") in {"response.completed", "response.incomplete"}:
                final_raw = raw_chunk.get("response")
                continue
            if raw_chunk.get("type") == "response.output_text.delta":
                text = raw_chunk.get("delta", "")
                if isinstance(text, str) and text:
                    content_parts.append(text)
                    yield AIStreamDelta(content=text, raw_metadata=self._safe_metadata(raw_chunk))

        if not isinstance(final_raw, dict):
            raise ProviderError(
                "Responses stream ended without a completion event.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=last_raw,
            )

        if "output" not in final_raw:
            final_raw = {
                **final_raw,
                "output": [streamed_items[key] for key in sorted(streamed_items)],
            }
        final_response = self._response_from_raw(
            final_raw, model=model, latency_ms=(time.perf_counter() - started) * 1000
        )
        if not final_response.message.content and content_parts:
            final_response = replace(
                final_response,
                message=replace(final_response.message, content="".join(content_parts)),
            )
        yield AIStreamFinal(response=final_response)

    def _responses_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        from ai_provider.credential_guard import enforce_credential_policy

        enforce_credential_policy(
            request, extra=(self.config.api_key, _provider_api_key(self.config.provider))
        )
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "input": self._input_items(request),
            "stream": stream,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.tools:
            payload["tools"] = [
                {"type": "function", **tool.to_json_schema()["function"]} for tool in request.tools
            ]
        return payload

    def _input_items(self, request: AIRequest) -> list[dict[str, Any]]:
        """Translate neutral tool history without relying on server-side storage."""
        items: list[dict[str, Any]] = []
        pending_calls: set[str] = set()
        seen_calls: set[str] = set()
        model = request.model or self.config.model

        def remember_calls(native: list[dict[str, Any]]) -> None:
            for item in native:
                if item.get("type") == "function_call":
                    call_id = item["call_id"]
                    if not call_id or call_id in seen_calls:
                        raise ProviderError(
                            "Responses history requires unique nonempty call ids.",
                            category=ProviderErrorCategory.CONFIGURATION,
                            provider=self.config.provider.value,
                        )
                    seen_calls.add(call_id)
                    pending_calls.add(call_id)

        for message in request.messages:
            if message.role is MessageRole.TOOL:
                if not message.tool_call_id or message.tool_call_id not in pending_calls:
                    raise ProviderError(
                        "Responses tool results require an originating call id.",
                        category=ProviderErrorCategory.CONFIGURATION,
                        provider=self.config.provider.value,
                    )
                pending_calls.remove(message.tool_call_id)
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
                continue
            state = message.continuation
            if (
                message.role is MessageRole.ASSISTANT
                and state is not None
                and (state.provider, state.model, state.base_url)
                == (self.backend.provider, model, self.base_url)
            ):
                replay = state.payload.get("responses_items")
                if isinstance(replay, list):
                    native_items = self._continuation_items(replay)
                    native_text = "".join(
                        part["text"]
                        for item in native_items
                        if item["type"] == "message"
                        for part in item["content"]
                    )
                    native_calls = [
                        item for item in native_items if item["type"] == "function_call"
                    ]
                    expected_calls = [
                        {
                            "type": "function_call",
                            "call_id": call.id,
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        }
                        for call in message.tool_calls
                    ]
                    if native_text == message.content and native_calls == expected_calls:
                        remember_calls(native_items)
                        items.extend(native_items)
                        continue
            if message.content or not message.tool_calls:
                items.append(self._message_payload(message))
            if message.role is MessageRole.ASSISTANT:
                calls = [
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    }
                    for call in message.tool_calls
                ]
                remember_calls(calls)
                items.extend(calls)
        if pending_calls:
            raise ProviderError(
                "Responses history has tool calls without matching results.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )
        return items

    @staticmethod
    def _continuation_items(output: list[Any]) -> list[dict[str, Any]]:
        """Preserve native order/phase and opaque reasoning without bare remote ids."""
        items: list[dict[str, Any]] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message" and item.get("role") == "assistant":
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                parts = [
                    {"type": "output_text", "text": part.get("text", part.get("refusal"))}
                    for part in content
                    if isinstance(part, dict)
                    and part.get("type") in {"output_text", "refusal"}
                    and isinstance(part.get("text", part.get("refusal")), str)
                ]
                if parts:
                    message: dict[str, Any] = {
                        "type": "message",
                        "role": "assistant",
                        "content": parts,
                    }
                    if item.get("phase") in {"commentary", "final_answer"}:
                        message["phase"] = item["phase"]
                    items.append(message)
                continue
            if item.get("type") == "function_call":
                if all(isinstance(item.get(key), str) for key in ("call_id", "name", "arguments")):
                    try:
                        arguments = json.dumps(json.loads(item["arguments"]))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": item["call_id"],
                            "name": item["name"],
                            "arguments": arguments,
                        }
                    )
                continue
            if item.get("type") != "reasoning":
                continue
            encrypted = item.get("encrypted_content")
            if not isinstance(encrypted, str) or not encrypted:
                continue
            replay: dict[str, Any] = {
                "type": "reasoning",
                "summary": [],
                "encrypted_content": encrypted,
            }
            if isinstance(item.get("id"), str):
                replay["id"] = item["id"]
            items.append(replay)
        return items

    def _message_payload(self, message: AIMessage) -> dict[str, Any]:
        return {"role": message.role.value, "content": message.content}

    def _response_from_raw(
        self, raw_response: dict[str, Any], *, model: str, latency_ms: float
    ) -> AIResponse:
        if not isinstance(raw_response, dict):
            raise ProviderError(
                "Responses API response must be a JSON object.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=raw_response,
            )
        if raw_response.get("status") == "failed":
            self._raise_response_failure(raw_response)
        output = raw_response.get("output")
        if not isinstance(output, list):
            raise ProviderError(
                "Responses API response did not include an output list.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=raw_response,
            )

        content_parts: list[str] = []
        calls: list[AIToolCall] = []
        call_ids: set[str] = set()
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                content_list = (
                    item.get("content", []) if isinstance(item.get("content"), list) else []
                )
                for part in content_list:
                    if isinstance(part, dict) and part.get("type") in {"output_text", "refusal"}:
                        text = part.get("text", part.get("refusal"))
                        if isinstance(text, str):
                            content_parts.append(text)
            elif item.get("type") == "function_call":
                call_id, name = item.get("call_id"), item.get("name")
                if (
                    not isinstance(call_id, str)
                    or not call_id.strip()
                    or call_id in call_ids
                    or not isinstance(name, str)
                    or not name.strip()
                ):
                    raise ProviderError(
                        "Responses tool call requires a unique call id and nonempty name.",
                        category=ProviderErrorCategory.NON_RETRYABLE,
                        provider=self.config.provider.value,
                    )
                try:
                    arguments = json.loads(item.get("arguments", ""))
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ToolCallFormatError(provider=self.config.provider.value) from exc
                if not isinstance(arguments, dict):
                    raise ToolCallFormatError(provider=self.config.provider.value)
                calls.append(AIToolCall(call_id, name, arguments))
                call_ids.add(call_id)

        continuation_items = self._continuation_items(output)
        continuation = (
            ProviderContinuation(
                self.backend.provider,
                model,
                self.base_url,
                {"responses_items": continuation_items},
            )
            if continuation_items
            else None
        )

        return AIResponse(
            message=AIMessage(
                role=MessageRole.ASSISTANT,
                content="".join(content_parts),
                tool_calls=tuple(calls),
                continuation=continuation,
            ),
            backend=self._backend_for_model(model),
            usage=self._usage_from_response(raw_response),
            finish_reason=self._finish_reason(raw_response),
            latency_ms=latency_ms,
            raw_metadata=self._safe_metadata(raw_response),
            tool_calls=tuple(calls),
        )

    def _raise_response_failure(self, raw: Any) -> None:
        error = raw.get("error") if isinstance(raw, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        categories = {
            "rate_limit_exceeded": ProviderErrorCategory.RATE_LIMIT,
            "insufficient_quota": ProviderErrorCategory.USAGE_LIMIT,
            "invalid_api_key": ProviderErrorCategory.AUTHENTICATION,
            "server_error": ProviderErrorCategory.RETRYABLE,
        }
        category = (
            categories.get(code, ProviderErrorCategory.NON_RETRYABLE)
            if isinstance(code, str)
            else ProviderErrorCategory.NON_RETRYABLE
        )
        label = code if isinstance(code, str) and code in categories else "unclassified"
        raise ProviderError(
            f"Responses API returned a failed response ({label}).",
            category=category,
            retryable=category
            in {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.RETRYABLE},
            provider=self.config.provider.value,
            raw_error=self._safe_metadata(raw) if isinstance(raw, dict) else raw,
        )

    def _backend_for_model(self, model: str) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        )

    def _post_responses(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/responses",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                "Responses API returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Responses API request timed out.",
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
                    "Responses API request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider=self.config.provider.value,
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                "Could not connect to Responses API provider.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc

    def _stream_responses(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/responses",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for line in response:
                    raw_line = line.strip()
                    if not raw_line or raw_line.startswith((b":", b"event:", b"id:", b"retry:")):
                        continue
                    if raw_line.startswith(b"data:"):
                        raw_line = raw_line.removeprefix(b"data:").removeprefix(b" ")
                        if raw_line == b"[DONE]":
                            break
                    chunk = json.loads(raw_line.decode("utf-8"))
                    if not isinstance(chunk, dict):
                        raise ProviderError(
                            "Responses stream chunk must be a JSON object.",
                            category=ProviderErrorCategory.NON_RETRYABLE,
                            provider=self.config.provider.value,
                            raw_error=chunk,
                        )
                    yield chunk
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                "Responses stream returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Responses API request timed out.",
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
                    "Responses API request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider=self.config.provider.value,
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                "Could not connect to Responses API provider.",
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
            f"Responses API provider returned HTTP {exc.code}.",
            category=category,
            retryable=category
            in {ProviderErrorCategory.RATE_LIMIT, ProviderErrorCategory.RETRYABLE},
            provider=self.config.provider.value,
            raw_error=exc,
        )

    def _safe_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                if value.get("type") == "reasoning":
                    return {"type": "reasoning"}
                return {
                    key: clean(item)
                    for key, item in value.items()
                    if key
                    not in {
                        "encrypted_content",
                        "reasoning",
                        "reasoning_content",
                        "reasoning_details",
                    }
                }
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        return clean(raw)

    @staticmethod
    def _usage_from_response(raw_response: dict[str, Any]) -> UsageMetadata:
        raw_usage = raw_response.get("usage")
        if not isinstance(raw_usage, dict):
            return UsageMetadata(source=UsageSource.UNAVAILABLE)
        input_tokens = raw_usage.get("input_tokens")
        output_tokens = raw_usage.get("output_tokens")
        total_tokens = raw_usage.get("total_tokens")
        return UsageMetadata(
            source=UsageSource.PROVIDER_REPORTED,
            input_tokens=input_tokens if type(input_tokens) is int and input_tokens >= 0 else None,
            output_tokens=output_tokens
            if type(output_tokens) is int and output_tokens >= 0
            else None,
            total_tokens=total_tokens if type(total_tokens) is int and total_tokens >= 0 else None,
        )

    @staticmethod
    def _finish_reason(raw_response: dict[str, Any]) -> FinishReason:
        """Map the Responses API ``status``/``incomplete_details`` to a finish reason.

        A truncated (``max_output_tokens``) or content-filtered response reports
        ``incomplete`` rather than ``completed``; hardcoding ``STOP`` would hide
        truncation from callers. Providers that omit ``status`` keep the historical
        ``STOP`` default.
        """

        status = raw_response.get("status")
        if status in (None, "completed"):
            return FinishReason.STOP
        if status == "incomplete":
            details = raw_response.get("incomplete_details")
            reason = details.get("reason") if isinstance(details, dict) else None
            if reason == "max_output_tokens":
                return FinishReason.LENGTH
            return FinishReason.UNKNOWN
        return FinishReason.UNKNOWN
