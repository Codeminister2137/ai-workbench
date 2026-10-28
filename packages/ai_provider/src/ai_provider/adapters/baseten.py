"""Baseten Model APIs over the shared Chat Completions protocol.

This adapter provides protocol support, not credit/billing admission. The event
configuration helper deliberately requires its own credential and exact model;
it never substitutes an ordinary personal key or enables automatic routing.
"""

from __future__ import annotations

import os
from typing import Any

from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIRequest
from ai_provider.errors import ProviderError, ProviderErrorCategory

BASETEN_BASE_URL = "https://inference.baseten.co/v1"
BASETEN_HACKATHON_MODEL = "meta-models/muse-spark-open-1026"


def baseten_hackathon_config(*, timeout_seconds: float = 60.0) -> BackendConfig:
    """Select the event key explicitly, failing before any network operation."""
    key = os.getenv("BASETEN_HACKATHON_API_KEY")
    if not key or not key.strip():
        raise ProviderError(
            "BASETEN_HACKATHON_API_KEY is required; no personal-key fallback is allowed.",
            category=ProviderErrorCategory.CONFIGURATION,
            provider=ProviderKind.BASETEN.value,
        )
    return BackendConfig(
        provider=ProviderKind.BASETEN,
        model=BASETEN_HACKATHON_MODEL,
        api_key=key.strip(),
        timeout_seconds=timeout_seconds,
    )


class BasetenChatClient(OpenAICompatibleChatClient):
    """Baseten identity and safe metadata around the shared protocol client."""

    def __post_init__(self) -> None:
        if self.config.provider is not ProviderKind.BASETEN:
            raise ProviderError(
                "Baseten client requires ProviderKind.BASETEN.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )

    @property
    def base_url(self) -> str:
        return (self.config.base_url or BASETEN_BASE_URL).rstrip("/")

    def _chat_payload(self, request: AIRequest, *, stream: bool) -> dict[str, Any]:
        payload = super()._chat_payload(request, stream=stream)
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _verify_request_model(self, request: AIRequest) -> None:
        super()._verify_request_model(request)
        if (
            self.config.model == BASETEN_HACKATHON_MODEL
            and request.model is not None
            and request.model != BASETEN_HACKATHON_MODEL
        ):
            raise ProviderError(
                "The Baseten hackathon configuration requires its exact event model.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )

    def _safe_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Remove reasoning text recursively while retaining provider usage totals."""

        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: clean(item)
                    for key, item in value.items()
                    if key not in {"reasoning_content", "reasoning", "reasoning_details"}
                }
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        return clean(raw)
