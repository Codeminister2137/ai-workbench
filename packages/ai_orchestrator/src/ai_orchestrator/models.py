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


class AccessMethod(StrEnum):
    """How a model/backend is reached at execution time."""

    LOCAL_RUNTIME = "local_runtime"
    PROVIDER_API = "provider_api"
    CODEX_CLI = "codex_cli"
    ANTIGRAVITY_CLI = "antigravity_cli"


class AuthMethod(StrEnum):
    """Credential or session mechanism required for one backend route."""

    NONE = "none"
    API_KEY = "api_key"
    CHATGPT_SIGN_IN = "chatgpt_sign_in"
    CODEX_ACCESS_TOKEN = "codex_access_token"
    GOOGLE_ACCOUNT_SIGN_IN = "google_account_sign_in"


class BillingSource(StrEnum):
    """Where usage cost, quota, or allowance is consumed."""

    LOCAL_FREE = "local_free"
    OPENAI_API_BILLING = "openai_api_billing"
    REQUESTY_BILLING = "requesty_billing"
    CHATGPT_SUBSCRIPTION_ALLOWANCE = "chatgpt_subscription_allowance"
    CHATGPT_WORKSPACE_CREDITS = "chatgpt_workspace_credits"
    GOOGLE_AI_STUDIO_FREE = "google_ai_studio_free"
    GOOGLE_API_BILLING = "google_api_billing"
    ANTIGRAVITY_SUBSCRIPTION_ALLOWANCE = "antigravity_subscription_allowance"


class CostPolicyTier(StrEnum):
    """Maximum cost boundary a task permits for route selection."""

    LOCAL_ONLY = "local_only"
    FREE_ONLY = "free_only"
    ALLOWANCES_ALLOWED = "allowances_allowed"
    PREPAID_CREDITS_ALLOWED = "prepaid_credits_allowed"
    BILLING_ALLOWED = "billing_allowed"


_COST_POLICY_RANK = {
    CostPolicyTier.LOCAL_ONLY: 0,
    CostPolicyTier.FREE_ONLY: 1,
    CostPolicyTier.ALLOWANCES_ALLOWED: 2,
    CostPolicyTier.PREPAID_CREDITS_ALLOWED: 3,
    CostPolicyTier.BILLING_ALLOWED: 4,
}


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
    cost_policy_tier: CostPolicyTier = CostPolicyTier.ALLOWANCES_ALLOWED
    user_route_id_override: str | None = None
    user_access_method_override: AccessMethod | None = None
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
class AccessRoute:
    """Single official route through which a model can be reached."""

    route_id: str
    provider: str
    product: str
    model: str
    location: BackendLocation
    access_method: AccessMethod
    auth_method: AuthMethod
    billing_source: BillingSource
    cost_policy_tier: CostPolicyTier
    base_url: str | None = None


@dataclass(frozen=True, slots=True)
class ModelBackend:
    """Model identity and route metadata known to the orchestrator."""

    route: AccessRoute
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    estimate: ModelPerformanceEstimate = field(default_factory=ModelPerformanceEstimate)

    @property
    def route_id(self) -> str:
        """Return the selected route identifier."""

        return self.route.route_id

    @property
    def provider(self) -> str:
        """Return the model provider for compatibility with existing callers."""

        return self.route.provider

    @property
    def product(self) -> str:
        """Return the product or service that owns the access route."""

        return self.route.product

    @property
    def model(self) -> str:
        """Return the model identifier exposed by this route."""

        return self.route.model

    @property
    def location(self) -> BackendLocation:
        """Return where this route processes requests."""

        return self.route.location

    @property
    def access_method(self) -> AccessMethod:
        """Return how this route is executed."""

        return self.route.access_method

    @property
    def auth_method(self) -> AuthMethod:
        """Return the authentication method required by this route."""

        return self.route.auth_method

    @property
    def billing_source(self) -> BillingSource:
        """Return the allowance, credit, or billing source consumed by this route."""

        return self.route.billing_source

    @property
    def cost_policy_tier(self) -> CostPolicyTier:
        """Return the minimum task cost policy needed to use this route."""

        return self.route.cost_policy_tier

    @property
    def base_url(self) -> str | None:
        """Return the route base URL when one exists."""

        return self.route.base_url


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


def cost_policy_allows(route_tier: CostPolicyTier, allowed_tier: CostPolicyTier) -> bool:
    """Return whether a task cost policy permits a route's required tier."""

    return _COST_POLICY_RANK[route_tier] <= _COST_POLICY_RANK[allowed_tier]
