"""Shared Responses-protocol base for POST + SSE adapters.

Centralises ``complete``/``_post_protocol``/``_stream_protocol`` so
Anthropic-style adapters only provide payload/response mapping.
"""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from urllib.request import Request

from ai_provider.config import BackendConfig
from ai_provider.contracts import AIMessage, AIRequest, AIResponse, UsageMetadata
from ai_provider.errors import (
    ProviderError,
    ProviderErrorCategory,
    http_error_to_provider_error,
)
from ai_provider.http_transport import read_bounded, urlopen
from ai_provider.privacy import enforce_privacy_policy
from ai_provider.turn_usage import observe_completion, observe_usage


@dataclass(slots=True)
class _ResponsesProtocolBase:
    """Shared base for Responses-protocol adapters (POST + SSE)."""

    config: BackendConfig

    _api_label: ClassVar[str] = ""
    _endpoint_path: ClassVar[str] = ""
    _stream_label: ClassVar[str] = ""

    @property
    def base_url(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    @observe_completion
    def complete(self, request: AIRequest) -> AIResponse:
        enforce_privacy_policy(self.backend, request.privacy_class)
        model = request.model or self.config.model
        payload = self._protocol_payload(request, stream=False)
        started = time.perf_counter()
        raw = self._post_protocol(payload)
        if isinstance(raw, dict):
            observe_usage(self._usage_from_response(raw))
        latency_ms = (time.perf_counter() - started) * 1000
        return self._response_from_raw(raw, model=model, latency_ms=latency_ms)

    def _post_protocol(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{self._endpoint_path}",
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(
                    read_bounded(response, provider=self.config.provider.value).decode("utf-8")
                )
        except ProviderError:
            raise
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                f"{self._api_label} returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                f"{self._api_label} request timed out.",
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
                    f"{self._api_label} request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider=self.config.provider.value,
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                f"Could not connect to {self._api_label} provider.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc

    def _stream_protocol(self, payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{self._endpoint_path}",
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
                            f"{self._stream_label} stream chunk must be a JSON object.",
                            category=ProviderErrorCategory.NON_RETRYABLE,
                            provider=self.config.provider.value,
                            raw_error=chunk,
                        )
                    yield chunk
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                f"{self._stream_label} stream returned invalid JSON.",
                category=ProviderErrorCategory.NON_RETRYABLE,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc
        except TimeoutError as exc:
            raise ProviderError(
                f"{self._api_label} request timed out.",
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
                    f"{self._api_label} request timed out.",
                    category=ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    provider=self.config.provider.value,
                    raw_error=exc,
                ) from exc
            raise ProviderError(
                f"Could not connect to {self._api_label} provider.",
                category=ProviderErrorCategory.RETRYABLE,
                retryable=True,
                provider=self.config.provider.value,
                raw_error=exc,
            ) from exc

    def _http_error(self, exc: HTTPError) -> ProviderError:
        return http_error_to_provider_error(
            exc, provider=self.config.provider.value, api_label=self._api_label
        )

    def _message_payload(self, message: AIMessage) -> dict[str, Any]:
        return {"role": message.role.value, "content": message.content}

    def _protocol_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        raise NotImplementedError

    def _response_from_raw(
        self, raw: dict[str, Any], *, model: str, latency_ms: float
    ) -> AIResponse:
        raise NotImplementedError

    def _usage_from_response(self, raw: dict[str, Any]) -> UsageMetadata:
        raise NotImplementedError
