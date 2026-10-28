"""Modal runtime chat client.

Modal hosts containerized inference (vLLM, SGLang, etc.) and exposes an
OpenAI-compatible Chat Completions endpoint. This adapter speaks that protocol
while marking the backend as a Modal runtime so the orchestrator can treat it
differently from a generic provider API where useful (e.g., skip the /models
readiness probe, since a dedicated Modal deployment need not implement it).
"""

from __future__ import annotations

from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.contracts import BackendInfo, BackendLocation, ModelCapabilities
from ai_provider.errors import ProviderError, ProviderErrorCategory


class ModalRuntimeChatClient(OpenAICompatibleChatClient):
    """Chat client for a Modal-hosted OpenAI-compatible inference endpoint."""

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
        if not self.config.base_url:
            raise ProviderError(
                "Modal runtime requires a deployment base_url (e.g. "
                "https://<user>--<app-name>.modal.run/v1).",
                category=ProviderErrorCategory.CONFIGURATION,
                provider=self.config.provider.value,
            )
        return self.config.base_url.rstrip("/")
