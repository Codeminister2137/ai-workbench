"""OpenCode Go Chat Completions adapter.

Go exposes an OpenAI-compatible Chat Completions endpoint. This adapter keeps
Go's distinct billing/route identity while reusing the shared Chat Completions
protocol implementation.

Session continuity: callers may pass a stable conversation session id in
``request.metadata["opencode_session"]``. The adapter sends it as
``x-opencode-session`` and a project-specific User-Agent, as required by Go's
coding-agent identification guidance.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIRequest,
    AIResponse,
    AIStreamEvent,
    BackendInfo,
    BackendLocation,
    ModelCapabilities,
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

    def complete(self, request: AIRequest) -> AIResponse:
        self._session_id = request.metadata.get("opencode_session")
        try:
            return super().complete(request)
        finally:
            self._session_id = None

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        self._session_id = request.metadata.get("opencode_session")
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
