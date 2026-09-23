"""Convert model recommendations into neutral execution plans."""

from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.models import (
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    ModelRecommendation,
    TaskProfile,
)


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
