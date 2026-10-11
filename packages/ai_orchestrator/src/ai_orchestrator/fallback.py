"""Default usage-limit fallback policy, independent of executor implementations."""

from dataclasses import replace
from enum import StrEnum

from ai_orchestrator.models import (
    ModelCatalogEntry,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
)
from ai_orchestrator.planner import ExecutionTarget
from ai_orchestrator.recommender import recommend_model


class FallbackQualityPolicy(StrEnum):
    """Declared quality floor for continuation, never an evaluation of actual output."""

    PRESERVE_QUALITY = "preserve_quality"
    TASK_MINIMUM = "task_minimum"
    EMERGENCY_PRESERVE = "emergency_preserve"
    PREFER_QUALITY = "prefer_quality"


def fallback_profile(
    profile: TaskProfile,
    initial: ExecutionTarget,
    catalog: tuple[ModelCatalogEntry, ...],
    *,
    quality_policy: FallbackQualityPolicy,
    preservation_only: bool = False,
) -> TaskProfile | None:
    """Derive fallback constraints, refusing an unknown original quality grade.

    Preservation permits inspection and handoff capabilities only. Callers must
    also restrict the executor's tools; a profile does not grant tool authority.
    """

    quality_policy = FallbackQualityPolicy(quality_policy)
    if preservation_only and quality_policy is not FallbackQualityPolicy.EMERGENCY_PRESERVE:
        return None
    quality_rank = {QualityThreshold.LOW: 0, QualityThreshold.STANDARD: 1, QualityThreshold.HIGH: 2}
    minimum_quality = profile.quality_threshold
    if quality_policy is not FallbackQualityPolicy.TASK_MINIMUM:
        original = next(
            (entry for entry in catalog if entry.backend.route_id == initial.route_id), None
        )
        if original is None or original.backend.model != initial.model:
            return None
        minimum_quality = max(
            profile.quality_threshold, original.quality, key=lambda quality: quality_rank[quality]
        )
    if preservation_only or quality_policy is FallbackQualityPolicy.PREFER_QUALITY:
        minimum_quality = QualityThreshold.LOW
    return replace(
        profile,
        task_type=TaskType.SUMMARIZATION if preservation_only else profile.task_type,
        required_capabilities=(
            frozenset({TaskCapability.CHAT, TaskCapability.TOOLS})
            if preservation_only
            else profile.required_capabilities
        ),
        quality_threshold=minimum_quality,
        user_route_id_override=None,
        user_access_method_override=None,
        user_backend_override=None,
        user_model_override=None,
    )


def fallback_candidates(
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    initial: ExecutionTarget,
    *,
    exhausted_billing_sources: frozenset[str] = frozenset(),
    unavailable_route_ids: frozenset[str] = frozenset(),
    allow_initial_billing_source: bool = False,
    quality_policy: FallbackQualityPolicy = FallbackQualityPolicy.PRESERVE_QUALITY,
    preservation_only: bool = False,
) -> tuple[ModelCatalogEntry, ...]:
    """Rank same-tier alternatives meeting the original task constraints.

    Explicit route/model overrides choose the first attempt. After exhaustion,
    privacy, cost tier and latency remain hard constraints. Emergency preservation
    keeps normal continuation at the original/task quality floor; a separate
    preservation-only query selects weaker models for inspection and handoff.
    The executor must enforce that restricted scope. Explicit prefer-quality
    continuation admits weaker models after higher-quality candidates. Unknown
    original quality refuses either new policy. Availability failures can exclude
    a route without excluding its entire billing bucket.
    """

    quality_policy = FallbackQualityPolicy(quality_policy)
    candidate_profile = fallback_profile(
        profile,
        initial,
        catalog,
        quality_policy=quality_policy,
        preservation_only=preservation_only,
    )
    if candidate_profile is None:
        return ()
    normal_profile = (
        fallback_profile(
            profile, initial, catalog, quality_policy=FallbackQualityPolicy.EMERGENCY_PRESERVE
        )
        if preservation_only
        else None
    )
    quality_rank = {QualityThreshold.LOW: 0, QualityThreshold.STANDARD: 1, QualityThreshold.HIGH: 2}
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
        and (
            normal_profile is None
            or quality_rank[entry.quality] < quality_rank[normal_profile.quality_threshold]
        )
    )
    ranked = []
    while eligible:
        try:
            chosen = recommend_model(candidate_profile, eligible).selected
        except ValueError:
            break
        ranked.append(chosen)
        eligible = tuple(entry for entry in eligible if entry is not chosen)
    return tuple(ranked)
