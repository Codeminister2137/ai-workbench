"""Ollama implementation of the provider-neutral chat client contract."""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_provider.config import BackendConfig
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
from ai_provider.privacy import enforce_privacy_policy
from ai_provider.turn_usage import observe_completion, observe_stream, observe_usage


def _known_tool_argument_failure(error: HTTPError) -> bool:
    """Recognize a bounded Harmony JSON-decoder error without retaining its body."""
    try:
        body = error.read(65537)
        if error.code != 500 or len(body) > 65536:
            return False
        payload = json.loads(body)
        message = payload.get("error") if isinstance(payload, dict) else None
        prefix = "error parsing tool call: raw='"
        if not isinstance(message, str) or not message.startswith(prefix):
            return False
        _, separator, cause = message[len(prefix) :].rpartition("', err=")
        if not separator:
            return False
        # Never scan the quoted model arguments for diagnostic keywords.
        return cause == "unexpected end of JSON input" or (
            cause.startswith("invalid character ")
            and cause.endswith(
                (
                    "looking for beginning of value",
                    "looking for object key string",
                    "looking for beginning of object key string",
                    "after top-level value",
                    "after object key:value pair",
                    "after array element",
                    "after object key",
                    "in string literal",
                    "in string escape code",
                )
            )
        )
    except (OSError, ValueError, RecursionError):
        return False
    finally:
        error.close()


def _tool_calls_from_raw(raw_calls: object) -> tuple[AIToolCall, ...]:
    if raw_calls is None:
        return ()
    if not isinstance(raw_calls, list):
        raise ProviderError(
            "Ollama tool calls must be an array.",
            category=ProviderErrorCategory.NON_RETRYABLE,
            provider="ollama",
        )
    calls: list[AIToolCall] = []
    for index, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            raise ProviderError(
                "Ollama tool call must be an object.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
            )
        function = raw_call.get("function", raw_call)
        if not isinstance(function, dict):
            raise ProviderError(
                "Ollama tool function must be an object.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
            )
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProviderError(
                "Ollama tool function requires a nonempty name.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
            )
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as error:
                raise ToolCallFormatError(provider="ollama") from error
        if not isinstance(arguments, dict):
            raise ToolCallFormatError(provider="ollama")
        calls.append(
            AIToolCall(
                id=str(raw_call.get("id") or f"tool-call-{index}"),
                name=name,
                arguments=arguments,
            )
        )
    return tuple(calls)


@dataclass(slots=True)
class OllamaChatClient:
    """Chat client that translates neutral requests to Ollama's local API."""

    config: BackendConfig

    @property
    def backend(self) -> BackendInfo:
        """Return local Ollama backend identity and capabilities."""

        return BackendInfo(
            provider="ollama",
            model=self.config.model,
            location=BackendLocation.LOCAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        )

    @property
    def base_url(self) -> str:
        """Return the configured Ollama base URL without a trailing slash."""

        return (self.config.base_url or "http://localhost:11434").rstrip("/")

    @observe_completion
    def complete(self, request: AIRequest) -> AIResponse:
        """Execute a non-streaming Ollama chat request."""

        enforce_privacy_policy(self.backend, request.privacy_class)

        model = request.model or self.config.model
        payload = self._chat_payload(request, stream=False)

        started = time.perf_counter()
        raw_response = self._post_chat(payload)
        if isinstance(raw_response, dict):
            observe_usage(self._usage_from_response(raw_response))
        latency_ms = (time.perf_counter() - started) * 1000

        return self._response_from_raw(raw_response, model=model, latency_ms=latency_ms)

    @observe_stream
    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        """Execute a streaming Ollama chat request and yield neutral events."""

        enforce_privacy_policy(self.backend, request.privacy_class)

        model = request.model or self.config.model
        payload = self._chat_payload(request, stream=True)
        started = time.perf_counter()
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        raw_tool_calls: list[Any] = []
        final_response: AIResponse | None = None

        for raw_chunk in self._stream_chat(payload):
            if raw_chunk.get("done") is True:
                observe_usage(self._usage_from_response(raw_chunk))
            raw_message = raw_chunk.get("message")
            is_done = raw_chunk.get("done") is True
            if raw_message is None and is_done:
                raw_message = {}
            if not isinstance(raw_message, dict):
                raise ProviderError(
                    "Ollama stream chunk did not include a message object.",
                    category=ProviderErrorCategory.NON_RETRYABLE,
                    provider="ollama",
                    raw_error=raw_chunk,
                )

            content = str(raw_message.get("content", ""))
            thinking = raw_message.get("thinking")
            if thinking is not None and not isinstance(thinking, str):
                raise ProviderError(
                    "Ollama thinking must be a string.",
                    category=ProviderErrorCategory.NON_RETRYABLE,
                    provider="ollama",
                )
            if thinking:
                thinking_parts.append(thinking)
            chunk_calls = raw_message.get("tool_calls")
            _tool_calls_from_raw(chunk_calls)
            if isinstance(chunk_calls, list):
                raw_tool_calls.extend(chunk_calls)
            if content:
                content_parts.append(content)
                yield AIStreamDelta(content=content, raw_metadata=raw_chunk)

            if is_done:
                latency_ms = (time.perf_counter() - started) * 1000
                final_raw = dict(raw_chunk)
                final_raw["message"] = {
                    **raw_message,
                    "content": "".join(content_parts),
                    "thinking": "".join(thinking_parts),
                    "tool_calls": raw_tool_calls,
                }
                final_response = self._response_from_raw(
                    final_raw,
                    model=model,
                    latency_ms=latency_ms,
                )
                yield AIStreamFinal(response=final_response)
                return

        if final_response is None:
            raise ProviderError(
                "Ollama stream ended without a final response object.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider="ollama",
            )

    def _chat_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        from ai_provider.credential_guard import enforce_credential_policy

        enforce_credential_policy(request, extra=(self.config.api_key,))
        payload: dict[str, Any] = {
            "model": request.model or self.config.model,
            "messages": [
                {
                    "role": message.role.value,
                    "content": message.content,
                    **self._continuation_payload(message, request.model or self.config.model),
                    **(
                        {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": call.arguments,
                                    },
                                }
                                for call in message.tool_calls
                            ]
                        }
                        if message.tool_calls
                        else {}
                    ),
                    **(
                        {"tool_name": message.name}
                        if message.role.value == "tool" and message.name
                        else {}
                    ),
                }
                for message in request.messages
            ],
            "stream": stream,
        }
        options: dict[str, Any] = {}
        if request.metadata.get("ollama_preserve_context") is True:
            # Opt-in admission prototype: overflow must not discard instructions.
            payload["truncate"] = False
            payload["shift"] = False
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        context_length = request.metadata.get("ollama_context_length")
        if context_length is not None:
            if (
                not isinstance(context_length, int)
                or isinstance(context_length, bool)
                or context_length < 1
            ):
                raise ValueError("ollama_context_length must be a positive integer")
            options["num_ctx"] = context_length
        thinking = request.metadata.get("ollama_thinking")
        if thinking is not None:
            if not isinstance(thinking, (bool, str)):
                raise ValueError("ollama_thinking must be a boolean or supported level")
            payload["think"] = thinking
        if options:
            payload["options"] = options
        if request.tools:
            payload["tools"] = [tool.to_json_schema() for tool in request.tools]
        return payload

    def _continuation_payload(self, message: AIMessage, model: str | None) -> dict[str, str]:
        state = message.continuation
        if (
            message.role is not MessageRole.ASSISTANT
            or state is None
            or state.provider != "ollama"
            or state.model != model
            or state.base_url != self.base_url
        ):
            return {}
        thinking = state.payload.get("thinking")
        if thinking is None:
            return {}
        if not isinstance(thinking, str):
            raise ProviderError(
                "Ollama thinking must be a string.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
            )
        return {"thinking": thinking}

    def _response_from_raw(
        self,
        raw_response: dict[str, Any],
        *,
        model: str,
        latency_ms: float,
    ) -> AIResponse:
        if not isinstance(raw_response, dict):
            raise ProviderError(
                "Ollama response must be a JSON object.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
                raw_error=raw_response,
            )
        raw_message = raw_response.get("message")
        if not isinstance(raw_message, dict):
            raise ProviderError(
                "Ollama response did not include a message object.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
                raw_error=raw_response,
            )

        content = raw_message.get("content", "")
        thinking = raw_message.get("thinking")
        if thinking is not None and not isinstance(thinking, str):
            raise ProviderError(
                "Ollama thinking must be a string.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
            )
        continuation = (
            ProviderContinuation("ollama", model, self.base_url, {"thinking": thinking})
            if thinking
            else None
        )
        tool_calls = _tool_calls_from_raw(raw_message.get("tool_calls"))
        done_reason = raw_response.get("done_reason")
        return AIResponse(
            message=AIMessage(
                role=MessageRole.ASSISTANT,
                content=str(content),
                tool_calls=tool_calls,
                continuation=continuation,
            ),
            backend=BackendInfo(
                provider="ollama",
                model=model,
                location=BackendLocation.LOCAL,
                base_url=self.base_url,
                capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
            ),
            usage=self._usage_from_response(raw_response),
            finish_reason=self._finish_reason(done_reason),
            latency_ms=latency_ms,
            tool_calls=tool_calls,
            raw_metadata=raw_response,
        )

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                "Ollama response returned invalid JSON or UTF-8.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Ollama request timed out.",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                provider="ollama",
                raw_error=exc,
            ) from exc
        except HTTPError as exc:
            if payload.get("tools") and _known_tool_argument_failure(exc):
                raise ToolCallFormatError(provider="ollama") from exc
            category = (
                ProviderErrorCategory.RETRYABLE
                if 500 <= exc.code < 600
                else ProviderErrorCategory.NON_RETRYABLE
            )
            raise ProviderError(
                f"Ollama returned HTTP {exc.code}.",
                category=category,
                retryable=category is ProviderErrorCategory.RETRYABLE,
                provider="ollama",
                raw_error=exc,
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError(
                    "Ollama request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider="ollama",
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                "Could not connect to Ollama.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider="ollama",
                raw_error=exc,
            ) from exc

    def _stream_chat(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                for line in response:
                    raw_line = line.strip()
                    if not raw_line:
                        continue
                    chunk = json.loads(raw_line.decode("utf-8"))
                    if not isinstance(chunk, dict):
                        raise ProviderError(
                            "Ollama stream chunk must be a JSON object.",
                            category=ProviderErrorCategory.NON_RETRYABLE,
                            provider="ollama",
                            raw_error=chunk,
                        )
                    yield chunk
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                "Ollama stream returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider="ollama",
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Ollama request timed out.",
                category=ProviderErrorCategory.TIMEOUT,
                retryable=True,
                provider="ollama",
                raw_error=exc,
            ) from exc
        except HTTPError as exc:
            category = (
                ProviderErrorCategory.RETRYABLE
                if 500 <= exc.code < 600
                else ProviderErrorCategory.NON_RETRYABLE
            )
            raise ProviderError(
                f"Ollama returned HTTP {exc.code}.",
                category=category,
                retryable=category is ProviderErrorCategory.RETRYABLE,
                provider="ollama",
                raw_error=exc,
            ) from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError(
                    "Ollama request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider="ollama",
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                "Could not connect to Ollama.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider="ollama",
                raw_error=exc,
            ) from exc

    @staticmethod
    def _usage_from_response(raw_response: dict[str, Any]) -> UsageMetadata:
        input_tokens = raw_response.get("prompt_eval_count")
        output_tokens = raw_response.get("eval_count")
        input_tokens = input_tokens if type(input_tokens) is int and input_tokens >= 0 else None
        output_tokens = output_tokens if type(output_tokens) is int and output_tokens >= 0 else None
        total_tokens = (
            input_tokens + output_tokens
            if isinstance(input_tokens, int) and isinstance(output_tokens, int)
            else None
        )
        if input_tokens is None and output_tokens is None:
            return UsageMetadata(source=UsageSource.UNAVAILABLE)
        return UsageMetadata(
            source=UsageSource.PROVIDER_REPORTED,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _finish_reason(done_reason: object) -> FinishReason:
        if done_reason in ("stop", "unload"):
            return FinishReason.STOP
        if done_reason == "length":
            return FinishReason.LENGTH
        return FinishReason.UNKNOWN
