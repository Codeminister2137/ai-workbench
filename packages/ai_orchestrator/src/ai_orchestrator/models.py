"""Neutral orchestration data models and policy labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TaskType(StrEnum):
    """Broad task category used as orchestration input."""

    GENERAL = "general"
    CODING = "coding"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    CREATIVE = "creative"


class TaskCapability(StrEnum):
    """Capabilities a task may require from a model/backend."""

    CHAT = "chat"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    MULTIMODAL_INPUT = "multimodal_input"
    EMBEDDINGS = "embeddings"


class QualityThreshold(StrEnum):
    """Minimum acceptable model quality tier for a task."""

    LOW = "low"
    STANDARD = "standard"
    HIGH = "high"


class LatencyTarget(StrEnum):
    """Preferred response-time profile for model selection."""

    INTERACTIVE = "interactive"
    BACKGROUND = "background"


class PrivacyClass(StrEnum):
    """Prototype request privacy classes owned by orchestration policy."""

    LOCAL_ONLY = "local_only"
    EXTERNAL_ALLOWED = "external_allowed"
    SENSITIVE_REVIEW_REQUIRED = "sensitive_review_required"
    PUBLIC_OR_LOW_RISK = "public_or_low_risk"


class BackendLocation(StrEnum):
    """Where an orchestration backend is expected to process requests."""

    LOCAL = "local"
    EXTERNAL = "external"


class PromptIssueSeverity(StrEnum):
    """Severity levels produced by prompt judging."""

    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class TaskProfile:
    """Caller-provided constraints used for prompt review and model selection."""

    task_type: TaskType = TaskType.GENERAL
    privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY
    required_capabilities: frozenset[TaskCapability] = field(
        default_factory=lambda: frozenset({TaskCapability.CHAT})
    )
    quality_threshold: QualityThreshold = QualityThreshold.STANDARD
    latency_target: LatencyTarget = LatencyTarget.INTERACTIVE
    max_expected_latency_seconds: float | None = None
    user_backend_override: str | None = None
    user_model_override: str | None = None


@dataclass(frozen=True, slots=True)
class PromptIssue:
    """Single prompt-quality issue reported by the prompt judge."""

    code: str
    message: str
    severity: PromptIssueSeverity
    confidence: float


@dataclass(frozen=True, slots=True)
class PromptJudgeResult:
    """Result of deterministic prompt review before model selection."""

    original_prompt: str
    issues: tuple[PromptIssue, ...]
    should_refine: bool
    refined_prompt: str | None = None
    change_summary: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Capabilities advertised by an orchestration model catalog entry."""

    chat: bool = True
    streaming: bool = False
    tools: bool = False
    structured_output: bool = False
    multimodal_input: bool = False
    embeddings: bool = False


@dataclass(frozen=True, slots=True)
class ModelPerformanceEstimate:
    """Optional source-labelled model performance and cost estimates."""

    typical_latency_seconds: float | None = None
    input_cost_per_million_tokens: float | None = None
    output_cost_per_million_tokens: float | None = None
    source: str | None = None
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class ModelBackend:
    """Backend and model identity known to the orchestrator."""

    provider: str
    model: str
    location: BackendLocation
    base_url: str | None = None
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    estimate: ModelPerformanceEstimate = field(default_factory=ModelPerformanceEstimate)


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    """Single selectable model entry in an orchestration catalog."""

    backend: ModelBackend
    quality: QualityThreshold = QualityThreshold.STANDARD
    latency: LatencyTarget = LatencyTarget.INTERACTIVE
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    """Rejected model candidate with an explanation for observability."""

    candidate: ModelCatalogEntry
    reason: str


@dataclass(frozen=True, slots=True)
class ModelRecommendation:
    """Selected model plus alternatives, rejections, and selection reasons."""

    selected: ModelCatalogEntry
    alternatives: tuple[ModelCatalogEntry, ...]
    rejected: tuple[CandidateRejection, ...]
    reasons: tuple[str, ...]


def supports_capability(capabilities: ModelCapabilities, capability: TaskCapability) -> bool:
    """Return whether a capability set satisfies one required task capability."""

    match capability:
        case TaskCapability.CHAT:
            return capabilities.chat
        case TaskCapability.TOOLS:
            return capabilities.tools
        case TaskCapability.STRUCTURED_OUTPUT:
            return capabilities.structured_output
        case TaskCapability.MULTIMODAL_INPUT:
            return capabilities.multimodal_input
        case TaskCapability.EMBEDDINGS:
            return capabilities.embeddings


def is_external_backend(entry: ModelCatalogEntry) -> bool:
    """Return whether a catalog entry points at an external backend."""

    return entry.backend.location is BackendLocation.EXTERNAL
