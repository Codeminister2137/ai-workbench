"""Provider-agnostic AI infrastructure."""

from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIResponse,
    AIStreamDelta,
    AIStreamEvent,
    AIStreamFinal,
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
from ai_provider.factory import create_chat_client

__all__ = [
    "AIMessage",
    "AIRequest",
    "AIResponse",
    "AIStreamDelta",
    "AIStreamEvent",
    "AIStreamFinal",
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
    "create_chat_client",
]
