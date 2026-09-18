"""Provider-agnostic AI infrastructure."""

from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    BackendInfo,
    BackendLocation,
    ChatClient,
    FinishReason,
    MessageRole,
    ModelCapabilities,
    PrivacyClass,
    UsageMetadata,
    UsageSource,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory

__all__ = [
    "AIMessage",
    "AIRequest",
    "AIResponse",
    "BackendConfig",
    "BackendInfo",
    "BackendLocation",
    "ChatClient",
    "FinishReason",
    "MessageRole",
    "ModelCapabilities",
    "OllamaChatClient",
    "PrivacyClass",
    "ProviderError",
    "ProviderErrorCategory",
    "ProviderKind",
    "UsageMetadata",
    "UsageSource",
]
