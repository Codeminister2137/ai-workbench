"""Convert model recommendations into neutral execution plans."""

from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.models import (
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    LatencyTarget,
    ModelCatalogEntry,
    ModelRecommendation,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
)
from ai_orchestrator.recommender import recommend_model


@dataclass(frozen=True, slots=True)
class ExecutionTarget:
    """Neutral execution target that callers adapt to their chosen executor."""

    route_id: str
    provider: str
    product: str
    model: str
    access_method: AccessMethod
    auth_method: AuthMethod
    billing_source: BillingSource
    cost_policy_tier: CostPolicyTier
    base_url: str | None = None
    timeout_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Prepared execution target and human-readable planning reasons."""

    target: ExecutionTarget
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DelegatedSubtaskPlan:
    """Prepared plan for a subtask delegated from a parent task."""

    subtask_id: str
    profile: TaskProfile
    execution_plan: ExecutionPlan
    description: str = ""


def plan_execution(
    profile: TaskProfile,
    recommendation: ModelRecommendation,
    *,
    timeout_seconds: float = 60.0,
) -> ExecutionPlan:
    """Create a neutral execution plan from a selected model recommendation."""

    selected = recommendation.selected.backend
    model = profile.user_model_override or selected.model
    target = ExecutionTarget(
        route_id=selected.route_id,
        provider=selected.provider,
        product=selected.product,
        model=model,
        access_method=selected.access_method,
        auth_method=selected.auth_method,
        billing_source=selected.billing_source,
        cost_policy_tier=selected.cost_policy_tier,
        base_url=selected.base_url,
        timeout_seconds=timeout_seconds,
    )
    return ExecutionPlan(
        target=target,
        reasons=recommendation.reasons,
    )


def derive_subtask_profile(
    parent: TaskProfile,
    task_type: TaskType = TaskType.GENERAL,
    *,
    required_capabilities: frozenset[TaskCapability] | None = None,
    quality_threshold: QualityThreshold = QualityThreshold.STANDARD,
    latency_target: LatencyTarget = LatencyTarget.INTERACTIVE,
    max_expected_latency_seconds: float | None = None,
    cost_policy_tier: CostPolicyTier = CostPolicyTier.LOCAL_ONLY,
    privacy_class: PrivacyClass | None = None,
    user_route_id_override: str | None = None,
    user_access_method_override: AccessMethod | None = None,
    user_backend_override: str | None = None,
    user_model_override: str | None = None,
) -> TaskProfile:
    """Derive a child task profile from a parent task profile.

    By default:
    - `privacy_class` inherits from the parent profile unless overridden.
    - `cost_policy_tier` defaults to `LOCAL_ONLY` to prefer offloading subtasks to
      cost-free local compute, but can be set explicitly to any tier.
    - User overrides on the parent profile do not cascade to the child subtask unless
      explicitly provided.
    """
    return TaskProfile(
        task_type=task_type,
        privacy_class=parent.privacy_class if privacy_class is None else privacy_class,
        required_capabilities=(
            required_capabilities
            if required_capabilities is not None
            else frozenset({TaskCapability.CHAT})
        ),
        quality_threshold=quality_threshold,
        latency_target=latency_target,
        max_expected_latency_seconds=max_expected_latency_seconds,
        cost_policy_tier=cost_policy_tier,
        user_route_id_override=user_route_id_override,
        user_access_method_override=user_access_method_override,
        user_backend_override=user_backend_override,
        user_model_override=user_model_override,
    )


def plan_delegated_subtask(
    parent_profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    task_type: TaskType = TaskType.GENERAL,
    *,
    subtask_id: str = "subtask",
    description: str = "",
    required_capabilities: frozenset[TaskCapability] | None = None,
    quality_threshold: QualityThreshold = QualityThreshold.STANDARD,
    latency_target: LatencyTarget = LatencyTarget.INTERACTIVE,
    max_expected_latency_seconds: float | None = None,
    cost_policy_tier: CostPolicyTier = CostPolicyTier.LOCAL_ONLY,
    privacy_class: PrivacyClass | None = None,
    timeout_seconds: float = 60.0,
    user_route_id_override: str | None = None,
    user_access_method_override: AccessMethod | None = None,
    user_backend_override: str | None = None,
    user_model_override: str | None = None,
) -> DelegatedSubtaskPlan:
    """Derive a subtask profile, recommend a model candidate, and plan execution."""
    subtask_profile = derive_subtask_profile(
        parent=parent_profile,
        task_type=task_type,
        required_capabilities=required_capabilities,
        quality_threshold=quality_threshold,
        latency_target=latency_target,
        max_expected_latency_seconds=max_expected_latency_seconds,
        cost_policy_tier=cost_policy_tier,
        privacy_class=privacy_class,
        user_route_id_override=user_route_id_override,
        user_access_method_override=user_access_method_override,
        user_backend_override=user_backend_override,
        user_model_override=user_model_override,
    )
    recommendation = recommend_model(subtask_profile, catalog)
    plan = plan_execution(subtask_profile, recommendation, timeout_seconds=timeout_seconds)
    return DelegatedSubtaskPlan(
        subtask_id=subtask_id,
        profile=subtask_profile,
        execution_plan=plan,
        description=description,
    )
