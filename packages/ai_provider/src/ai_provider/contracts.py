from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class PrivacyClass(StrEnum):
    """Prototype request privacy classes.

    These labels are provisional until external provider routing is implemented
    and validated against real workflows.
    """

    LOCAL_ONLY = "local_only"
    EXTERNAL_ALLOWED = "external_allowed"
    SENSITIVE_REVIEW_REQUIRED = "sensitive_review_required"
    PUBLIC_OR_LOW_RISK = "public_or_low_risk"


class BackendLocation(StrEnum):
    LOCAL = "local"
    EXTERNAL = "external"


class UsageSource(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class FinishReason(StrEnum):
    STOP = "stop"
    LENGTH = "length"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AIMessage:
    role: MessageRole
    content: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    chat: bool = True
    streaming: bool = False
    tools: bool = False
    structured_output: bool = False
    multimodal_input: bool = False
    embeddings: bool = False


@dataclass(frozen=True, slots=True)
class BackendInfo:
    provider: str
    model: str
    location: BackendLocation
    base_url: str | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    source: UsageSource = UsageSource.UNAVAILABLE
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class AIRequest:
    messages: tuple[AIMessage, ...]
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIResponse:
    message: AIMessage
    backend: BackendInfo
    usage: UsageMetadata = field(default_factory=UsageMetadata)
    finish_reason: FinishReason = FinishReason.UNKNOWN
    latency_ms: float | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


class ChatClient(Protocol):
    @property
    def backend(self) -> BackendInfo:
        """Return backend identity and capabilities."""
        ...

    def complete(self, request: AIRequest) -> AIResponse:
        """Execute a chat-style completion request."""
        ...
