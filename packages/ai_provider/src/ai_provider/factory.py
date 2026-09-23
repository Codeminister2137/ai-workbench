"""Factory helpers for creating provider chat clients."""

from __future__ import annotations

from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import ChatClient


def create_chat_client(config: BackendConfig) -> ChatClient:
    """Create a chat client for the configured provider."""

    if config.provider is ProviderKind.OLLAMA:
        return OllamaChatClient(config)

    if config.provider in {ProviderKind.OPENAI, ProviderKind.REQUESTY, ProviderKind.GOOGLE}:
        return OpenAICompatibleChatClient(config)

    msg = f"Unsupported provider kind: {config.provider.value}."
    raise ValueError(msg)
