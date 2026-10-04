"""Default usage-limit fallback policy, independent of executor implementations."""

from dataclasses import replace
from enum import StrEnum

from ai_orchestrator.models import ModelCatalogEntry, QualityThreshold, TaskProfile
from ai_orchestrator.planner import ExecutionTarget
from ai_orchestrator.recommender import recommend_model


class FallbackQualityPolicy(StrEnum):
    """Declared quality floor for continuation, never an evaluation of actual output."""

    PRESERVE_QUALITY = "preserve_quality"
    TASK_MINIMUM = "task_minimum"


def fallback_candidates(
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    initial: ExecutionTarget,
    *,
    exhausted_billing_sources: frozenset[str] = frozenset(),
    unavailable_route_ids: frozenset[str] = frozenset(),
    allow_initial_billing_source: bool = False,
    quality_policy: FallbackQualityPolicy = FallbackQualityPolicy.PRESERVE_QUALITY,
) -> tuple[ModelCatalogEntry, ...]:
    """Rank same-tier alternatives meeting the original task constraints.

    Explicit route/model overrides choose the first attempt. After exhaustion,
    alternatives may differ, but privacy, capabilities, task quality and latency
    remain hard constraints. Quality preference comes from the recommender;
    the original route's grade is also a hard minimum for continued work.
    Unknown original quality refuses continuation. Availability failures can
    exclude a route without excluding its entire billing bucket.
    """

    quality_policy = FallbackQualityPolicy(quality_policy)
    original = next(
        (entry for entry in catalog if entry.backend.route_id == initial.route_id), None
    )
    quality_rank = {QualityThreshold.LOW: 0, QualityThreshold.STANDARD: 1, QualityThreshold.HIGH: 2}
    minimum_quality = profile.quality_threshold
    if quality_policy is FallbackQualityPolicy.PRESERVE_QUALITY:
        if original is None or original.backend.model != initial.model:
            return ()
        minimum_quality = max(
            profile.quality_threshold, original.quality, key=lambda quality: quality_rank[quality]
        )
    fallback_profile = replace(
        profile,
        quality_threshold=minimum_quality,
        user_route_id_override=None,
        user_access_method_override=None,
        user_backend_override=None,
        user_model_override=None,
    )
    eligible = tuple(
        entry
        for entry in catalog
        if entry.backend.route_id != initial.route_id
        and (
            allow_initial_billing_source
            or entry.backend.billing_source is not initial.billing_source
        )
        and entry.backend.cost_policy_tier is initial.cost_policy_tier
        and entry.backend.billing_source.value not in exhausted_billing_sources
        and entry.backend.route_id not in unavailable_route_ids
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
