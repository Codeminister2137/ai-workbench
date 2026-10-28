"""Factory helpers for creating provider chat clients."""

from __future__ import annotations

from ai_provider.adapters.meta import MetaResponsesChatClient
from ai_provider.adapters.modal import ModalRuntimeChatClient
from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.adapters.opencode_go import OpenCodeGoChatClient
from ai_provider.adapters.opencode_go_messages import OpenCodeGoMessagesClient
from ai_provider.adapters.opencode_go_responses import OpenCodeGoResponsesClient
from ai_provider.adapters.openrouter import OpenRouterFreeChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import ChatClient
from ai_provider.go_source_info import _model_protocol


def create_chat_client(config: BackendConfig) -> ChatClient:
    """Create a chat client for the configured provider."""

    if config.provider is ProviderKind.OLLAMA:
        return OllamaChatClient(config)

    if config.provider is ProviderKind.OPENROUTER:
        return OpenRouterFreeChatClient(config)

    if config.provider is ProviderKind.OPENCODE_GO:
        protocol = _model_protocol(config.model)
        if protocol == "responses":
            return OpenCodeGoResponsesClient(config)
        if protocol == "messages":
            return OpenCodeGoMessagesClient(config)
        return OpenCodeGoChatClient(config)

    if config.provider is ProviderKind.META:
        return MetaResponsesChatClient(config)

    if config.provider is ProviderKind.MODAL:
        return ModalRuntimeChatClient(config)

    if config.provider in {ProviderKind.OPENAI, ProviderKind.REQUESTY, ProviderKind.GOOGLE}:
        return OpenAICompatibleChatClient(config)

    msg = f"Unsupported provider kind: {config.provider.value}."
    raise ValueError(msg)
