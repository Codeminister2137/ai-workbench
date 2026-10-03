"""Default usage-limit fallback policy, independent of executor implementations."""

from dataclasses import replace

from ai_orchestrator.models import ModelCatalogEntry, TaskProfile
from ai_orchestrator.planner import ExecutionTarget
from ai_orchestrator.recommender import recommend_model


def fallback_candidates(
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    initial: ExecutionTarget,
    *,
    exhausted_billing_sources: frozenset[str] = frozenset(),
) -> tuple[ModelCatalogEntry, ...]:
    """Rank same-tier alternatives meeting the original task constraints.

    Explicit route/model overrides choose the first attempt. After exhaustion,
    alternatives may differ, but privacy, capabilities, task quality and latency
    remain hard constraints. Quality preference comes from the recommender;
    matching the original route's higher grade is not a hard requirement.
    """

    fallback_profile = replace(
        profile,
        user_route_id_override=None,
        user_access_method_override=None,
        user_backend_override=None,
        user_model_override=None,
    )
    eligible = tuple(
        entry
        for entry in catalog
        if entry.backend.route_id != initial.route_id
        and entry.backend.billing_source is not initial.billing_source
        and entry.backend.cost_policy_tier is initial.cost_policy_tier
        and entry.backend.billing_source.value not in exhausted_billing_sources
    )
    ranked = []
    while eligible:
        try:
            chosen = recommend_model(fallback_profile, eligible).selected
        except ValueError:
            break
        ranked.append(chosen)
        eligible = tuple(entry for entry in eligible if entry is not chosen)
    return tuple(ranked)
