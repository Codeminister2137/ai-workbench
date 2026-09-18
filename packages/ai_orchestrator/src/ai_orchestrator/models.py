from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ai_provider import BackendInfo, BackendLocation, ModelCapabilities, PrivacyClass


class TaskType(StrEnum):
    GENERAL = "general"
    CODING = "coding"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    CREATIVE = "creative"


class TaskCapability(StrEnum):
    CHAT = "chat"
    TOOLS = "tools"
    STRUCTURED_OUTPUT = "structured_output"
    MULTIMODAL_INPUT = "multimodal_input"
    EMBEDDINGS = "embeddings"


class QualityThreshold(StrEnum):
    LOW = "low"
    STANDARD = "standard"
    HIGH = "high"


class LatencyTarget(StrEnum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"


class PromptIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class TaskProfile:
    task_type: TaskType = TaskType.GENERAL
    privacy_class: PrivacyClass = PrivacyClass.LOCAL_ONLY
    required_capabilities: frozenset[TaskCapability] = field(
        default_factory=lambda: frozenset({TaskCapability.CHAT})
    )
    quality_threshold: QualityThreshold = QualityThreshold.STANDARD
    latency_target: LatencyTarget = LatencyTarget.INTERACTIVE
    user_backend_override: str | None = None
    user_model_override: str | None = None


@dataclass(frozen=True, slots=True)
class PromptIssue:
    code: str
    message: str
    severity: PromptIssueSeverity
    confidence: float


@dataclass(frozen=True, slots=True)
class PromptJudgeResult:
    original_prompt: str
    issues: tuple[PromptIssue, ...]
    should_refine: bool
    refined_prompt: str | None = None
    change_summary: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogEntry:
    backend: BackendInfo
    quality: QualityThreshold = QualityThreshold.STANDARD
    latency: LatencyTarget = LatencyTarget.INTERACTIVE
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    candidate: ModelCatalogEntry
    reason: str


@dataclass(frozen=True, slots=True)
class ModelRecommendation:
    selected: ModelCatalogEntry
    alternatives: tuple[ModelCatalogEntry, ...]
    rejected: tuple[CandidateRejection, ...]
    reasons: tuple[str, ...]


def supports_capability(capabilities: ModelCapabilities, capability: TaskCapability) -> bool:
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
    return entry.backend.location is BackendLocation.EXTERNAL
