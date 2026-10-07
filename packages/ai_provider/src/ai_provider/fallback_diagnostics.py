"""Offline fallback diagnostics; support declarations are not execution readiness."""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ai_orchestrator import ExecutionTarget, ModelCatalogEntry, TaskProfile, prepare_execution
from ai_orchestrator.fallback import FallbackQualityPolicy, fallback_candidates


def fallback_readiness_report(
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    primary: ExecutionTarget,
    *,
    incompatibility: Callable[[ExecutionTarget], str | None],
    executable_status: Callable[[ExecutionTarget], str],
    enabled: bool = True,
    quality_policy: FallbackQualityPolicy = FallbackQualityPolicy.PRESERVE_QUALITY,
) -> dict[str, Any]:
    """Explain policy/adapter exclusions without performing runtime or account probes.

    The caller supplies a static inspector. An eligible route may still lack
    authentication, connected tools or allowance; none is asserted by this report.
    """
    eligible = fallback_candidates(profile, catalog, primary, quality_policy=quality_policy)
    candidates = []
    for entry in eligible:
        plan = prepare_execution(
            "Fallback readiness",
            replace(
                profile,
                user_route_id_override=entry.backend.route_id,
                user_access_method_override=None,
                user_backend_override=None,
                user_model_override=None,
            ),
            (entry,),
            review_prompt=False,
            timeout_seconds=primary.timeout_seconds,
        ).execution_plan
        assert plan is not None
        reason = incompatibility(plan.target)
        candidates.append(
            {
                "route_id": plan.target.route_id,
                "executor_compatible": reason is None,
                "reason": reason,
                "executable_status": executable_status(plan.target),
                "authentication": "not_checked",
                "tool_connection": "not_checked",
                "allowance": "unknown",
                "execution_ready": False,
            }
        )
    eligible_ids = {entry.backend.route_id for entry in eligible}
    excluded = []
    for entry in catalog:
        backend = entry.backend
        if backend.route_id == primary.route_id or backend.route_id in eligible_ids:
            continue
        if backend.cost_policy_tier is not primary.cost_policy_tier:
            reason = "different cost tier"
        elif backend.billing_source is primary.billing_source:
            reason = "shared billing source"
        else:
            reason = "task privacy, capability, quality or latency constraints"
        excluded.append({"route_id": backend.route_id, "reason": reason})
    return {
        "status": "offline",
        "fallback_enabled": enabled,
        "fallback_quality_policy": quality_policy.value,
        "primary_route": primary.route_id,
        "cost_policy_tier": primary.cost_policy_tier.value,
        "authentication": "not_checked",
        "tool_connection": "not_checked",
        "allowance": "unknown",
        "fallback_candidates": candidates,
        "policy_exclusions": excluded,
    }
