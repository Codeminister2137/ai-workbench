from __future__ import annotations

from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import ChatClient
from ai_provider.errors import ProviderError, ProviderErrorCategory


def create_chat_client(config: BackendConfig) -> ChatClient:
    if config.provider is ProviderKind.OLLAMA:
        return OllamaChatClient(config)

    raise ProviderError(
        f"Provider is not implemented yet: {config.provider.value}.",
        category=ProviderErrorCategory.CONFIGURATION,
        provider=config.provider.value,
    )
