"""Provider-agnostic AI infrastructure."""

from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
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
from ai_provider.ollama_models import (
    LocalOllamaModel,
    OllamaPullConstraints,
    OllamaPullLogStatus,
    OllamaPullProgress,
    OllamaPullResult,
    list_local_ollama_models,
    pull_ollama_model,
    show_ollama_model,
    stream_ollama_model_pull,
    summarize_ollama_pull_logs,
)
from ai_provider.ollama_runtime import ensure_ollama_server, is_ollama_server_available

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
    "LocalOllamaModel",
    "MessageRole",
    "ModelCapabilities",
    "OllamaChatClient",
    "OllamaPullConstraints",
    "OllamaPullLogStatus",
    "OllamaPullProgress",
    "OllamaPullResult",
    "OpenAICompatibleChatClient",
    "PrivacyClass",
    "ProviderError",
    "ProviderErrorCategory",
    "ProviderKind",
    "UsageMetadata",
    "UsageSource",
    "create_chat_client",
    "ensure_ollama_server",
    "is_ollama_server_available",
    "list_local_ollama_models",
    "pull_ollama_model",
    "show_ollama_model",
    "stream_ollama_model_pull",
    "summarize_ollama_pull_logs",
]
