"""Provider-neutral chat request, response, and streaming contracts."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class MessageRole(StrEnum):
    """Supported chat message roles shared across provider adapters."""

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
    """Where a backend processes requests from the caller's privacy perspective."""

    LOCAL = "local"
    EXTERNAL = "external"


class UsageSource(StrEnum):
    """How token usage values were obtained."""

    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class FinishReason(StrEnum):
    """Normalized reason a provider stopped generating a response."""

    STOP = "stop"
    LENGTH = "length"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AIMessage:
    """Single chat message in the neutral provider contract."""

    role: MessageRole
    content: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Provider-reported capabilities used by callers and orchestration adapters."""

    chat: bool = True
    streaming: bool = False
    tools: bool = False
    structured_output: bool = False
    multimodal_input: bool = False
    embeddings: bool = False


@dataclass(frozen=True, slots=True)
class BackendInfo:
    """Identity, location, and capabilities of the backend that handled a request."""

    provider: str
    model: str
    location: BackendLocation
    base_url: str | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    """Token usage metadata normalized across providers when available."""

    source: UsageSource = UsageSource.UNAVAILABLE
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class AIRequest:
    """Provider-neutral chat completion request."""

    messages: tuple[AIMessage, ...]
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIResponse:
    """Provider-neutral chat completion response."""

    message: AIMessage
    backend: BackendInfo
    usage: UsageMetadata = field(default_factory=UsageMetadata)
    finish_reason: FinishReason = FinishReason.UNKNOWN
    latency_ms: float | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIStreamDelta:
    """Incremental text emitted by a streaming provider response."""

    content: str
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIStreamFinal:
    """Final streaming event containing the normalized completed response."""

    response: AIResponse


AIStreamEvent = AIStreamDelta | AIStreamFinal


class ChatClient(Protocol):
    """Synchronous chat client interface implemented by provider adapters."""

    @property
    def backend(self) -> BackendInfo:
        """Return backend identity and capabilities."""
        ...

    def complete(self, request: AIRequest) -> AIResponse:
        """Execute a chat-style completion request."""
        ...

    def stream(self, request: AIRequest) -> Iterator[AIStreamEvent]:
        """Execute a chat-style completion request and yield streaming events."""
        ...
