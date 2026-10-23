"""OpenCode Go Chat Completions adapter.

Go exposes an OpenAI-compatible Chat Completions endpoint. This adapter keeps
Go's distinct billing/route identity while reusing the shared Chat Completions
protocol implementation.

Session continuity: callers may pass a stable conversation session id in
``request.metadata["opencode_session"]``. The adapter sends it as
``x-opencode-session`` and a project-specific User-Agent, as required by Go's
coding-agent identification guidance. If the caller does not supply a session
id, the adapter generates a fresh one so the request is always valid.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamEvent,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ModelCapabilities,
    ProviderContinuation,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory

GO_CHAT_BASE_URL = "https://opencode.ai/inference/go/openai/v1"
GO_USER_AGENT = "ai_projects/0.1.0"


@dataclass(slots=True)
class OpenCodeGoChatClient(OpenAICompatibleChatClient):
    """Chat client for OpenCode Go's OpenAI-compatible inference endpoint."""

    config: BackendConfig
    _session_id: str | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.config.provider is not ProviderKind.OPENCODE_GO:
            raise ProviderError(
                "OpenCode Go client requires ProviderKind.OPENCODE_GO.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )

    @property
    def base_url(self) -> str:
        return (self.config.base_url or GO_CHAT_BASE_URL).rstrip("/")

    @property
    def backend(self) -> BackendInfo:
        return BackendInfo(
            provider=self.config.provider.value,
            model=self.config.model,
            location=BackendLocation.EXTERNAL,
            base_url=self.base_url,
            capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        )

    def _session_id_for(self, request: AIRequest) -> str:
        """Return the caller-supplied session id or a fresh UUID."""
        session_id = request.metadata.get("opencode_session")
        if isinstance(session_id, str) and session_id:
            return session_id
        return uuid4().hex

    def complete(self, request: AIRequest) -> AIResponse:
        self._session_id = self._session_id_for(request)
        try:
            return super().complete(request)
        finally:
            self._session_id = None

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        self._session_id = self._session_id_for(request)
        try:
            yield from super().stream(request)
        finally:
            self._session_id = None

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["User-Agent"] = GO_USER_AGENT
        session_id = getattr(self, "_session_id", None)
        if isinstance(session_id, str) and session_id:
            headers["x-opencode-session"] = session_id
        return headers

    def _continuation(self, message: dict[str, Any], model: str) -> ProviderContinuation | None:
        reasoning = message.get("reasoning_content")
        if model == "kimi-k2.7-code" and isinstance(reasoning, str) and reasoning:
            return ProviderContinuation(
                self.backend.provider, model, self.base_url, {"reasoning_content": reasoning}
            )
        return None

    def _message_payload(self, message: AIMessage, model: str) -> dict[str, Any]:
        payload = super()._message_payload(message, model)
        state = message.continuation
        if (
            model == "kimi-k2.7-code"
            and message.role is MessageRole.ASSISTANT
            and state is not None
            and (state.provider, state.model, state.base_url)
            == (self.backend.provider, model, self.base_url)
            and isinstance(state.payload.get("reasoning_content"), str)
        ):
            payload["reasoning_content"] = state.payload["reasoning_content"]
        return payload

    def _collect_continuation(self, state: dict[str, Any], delta: dict[str, Any]) -> None:
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str):
            state["reasoning_content"] = state.get("reasoning_content", "") + reasoning

    def _safe_metadata(self, raw: dict[str, Any]) -> dict[str, Any]:
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
