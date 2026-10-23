"""OpenCode Go Anthropic Messages API adapter.

Wraps the generic Anthropic Messages adapter with Go's endpoint, User-Agent and
per-request session header.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ai_provider.adapters.anthropic_messages import AnthropicMessagesChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIRequest
from ai_provider.errors import ProviderError, ProviderErrorCategory

GO_MESSAGES_BASE_URL = "https://opencode.ai/inference/go/v1"
GO_USER_AGENT = "ai_projects/0.1.0"


@dataclass(slots=True)
class OpenCodeGoMessagesClient(AnthropicMessagesChatClient):
    """Chat client for OpenCode Go models that use the Anthropic Messages protocol."""

    config: BackendConfig
    _session_id: str | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.config.provider is not ProviderKind.OPENCODE_GO:
            raise ProviderError(
                "OpenCode Go messages client requires ProviderKind.OPENCODE_GO.",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )

    @property
    def base_url(self) -> str:
        return (self.config.base_url or GO_MESSAGES_BASE_URL).rstrip("/")

    def _session_id_for(self, request: AIRequest) -> str:
        """Return the caller-supplied session id or a fresh UUID."""
        session_id = request.metadata.get("opencode_session")
        if isinstance(session_id, str) and session_id:
            return session_id
        return uuid4().hex

    def complete(self, request: AIRequest) -> Any:
        self._session_id = self._session_id_for(request)
        try:
            return super().complete(request)
        finally:
            self._session_id = None

    def stream(self, request: AIRequest) -> Any:
        self._session_id = self._session_id_for(request)
        try:
            yield from super().stream(request)
        finally:
            self._session_id = None

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["User-Agent"] = GO_USER_AGENT
        session_id = self._session_id
        if isinstance(session_id, str) and session_id:
            headers["x-opencode-session"] = session_id
        return headers
