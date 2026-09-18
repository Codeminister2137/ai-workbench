from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_provider.config import BackendConfig
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
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


@dataclass(slots=True)
class OllamaChatClient:
    config: BackendConfig

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider="ollama",
            model=self.config.model,
            location=BackendLocation.LOCAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=False),
        )

    @property
    def base_url(self) -> str:
        return (self.config.base_url or "http://localhost:11434").rstrip("/")

    def complete(self, request: AIRequest) -> AIResponse:
        enforce_privacy_policy(self.backend, request.privacy_class)

        model = request.model or self.config.model
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
        }
        options: dict[str, Any] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            options["num_predict"] = request.max_output_tokens
        if options:
            payload["options"] = options

        started = time.perf_counter()
        raw_response = self._post_chat(payload)
        latency_ms = (time.perf_counter() - started) * 1000

        content = raw_response.get("message", {}).get("content", "")
        done_reason = raw_response.get("done_reason")
        return AIResponse(
            message=AIMessage(role=MessageRole.ASSISTANT, content=str(content)),
            backend=BackendInfo(
                provider="ollama",
                model=model,
                location=BackendLocation.LOCAL,
                base_url=self.base_url,
                capabilities=ModelCapabilities(chat=True, streaming=False),
            ),
            usage=self._usage_from_response(raw_response),
            finish_reason=self._finish_reason(done_reason),
            latency_ms=latency_ms,
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
        total_tokens = (
            input_tokens + output_tokens
            if isinstance(input_tokens, int) and isinstance(output_tokens, int)
            else None
        )
        if input_tokens is None and output_tokens is None:
            return UsageMetadata(source=UsageSource.UNAVAILABLE)
        return UsageMetadata(
            source=UsageSource.PROVIDER_REPORTED,
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) else None,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _finish_reason(done_reason: object) -> FinishReason:
        if done_reason in {"stop", "unload"}:
            return FinishReason.STOP
        if done_reason == "length":
            return FinishReason.LENGTH
        return FinishReason.UNKNOWN
