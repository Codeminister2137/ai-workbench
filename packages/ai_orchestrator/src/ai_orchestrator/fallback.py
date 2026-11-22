"""Default usage-limit fallback policy, independent of executor implementations."""

import logging
from collections.abc import Mapping
from dataclasses import replace
from enum import StrEnum

from ai_orchestrator.deliberation import DeliberationPort, request_verdict
from ai_orchestrator.models import (
    ModelCatalogEntry,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
    cost_policy_allows,
)
from ai_orchestrator.planner import ExecutionTarget
from ai_orchestrator.recommender import _allowance_rank, recommend_model


class FallbackQualityPolicy(StrEnum):
    """Declared quality floor for continuation, never an evaluation of actual output."""

    PRESERVE_QUALITY = "preserve_quality"
    TASK_MINIMUM = "task_minimum"
    EMERGENCY_PRESERVE = "emergency_preserve"
    PREFER_QUALITY = "prefer_quality"


logger = logging.getLogger(__name__)


def _verdict_priority_routes(
    port: DeliberationPort,
    question: str,
    known_route_ids: frozenset[str],
) -> tuple[str, ...]:
    """Route ids a council verdict steers toward (exact matches only).

    Only ``next_actions`` entries that exactly name a known route steer;
    prose agreement never invents routes. Consensus ``none``, port errors
    and malformed verdicts yield nothing and the caller keeps current
    behavior. Steering is logged with the fields that caused it.
    """
    try:
        verdict = request_verdict(port, question)
    except Exception as exc:  # noqa: BLE001 - verdict failure keeps current ranking
        logger.debug("council verdict unavailable, keeping fallback ranking: %s", exc)
        return ()
    consensus = verdict.get("consensus")
    if consensus not in ("full", "partial"):
        logger.debug("council verdict consensus %r steers nothing", consensus)
        return ()
    steered = tuple(
        action
        for action in verdict.get("next_actions", [])
        if isinstance(action, str) and action in known_route_ids
    )
    logger.info(
        "council verdict steers fallback priority: consensus=%s routes=%s",
        consensus,
        ",".join(steered) if steered else "(no exact route matches)",
    )
    return steered


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


def _accepts(
    profile: TaskProfile,
    entry: ModelCatalogEntry,
    cost_exemptions: frozenset[str] = frozenset(),
) -> bool:
    """Reuse the recommender's acceptance rules so ordering cannot relax them."""
    try:
        recommend_model(profile, (entry,), cost_exemptions=cost_exemptions)
    except ValueError:
        return False
    return True


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
    priority: tuple[str, ...] = (),
    excluded_route_ids: frozenset[str] = frozenset(),
    allow_cost_escalation: bool = False,
    cost_exemptions: frozenset[str] = frozenset(),
    allowance_remaining: Mapping[str, float] | None = None,
    deliberation_port: DeliberationPort | None = None,
    deliberation_question: str | None = None,
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

    ``priority`` is a caller-supplied ordered route list, typically derived from
    observed account allowance, reliability and task quality. Listed routes are
    returned first in that order within each allowance band; unlisted eligible
    routes keep the existing recommender ranking behind them. Priority never relaxes privacy, capability
    or quality filters, so it orders candidates rather than admitting new ones.

    ``excluded_route_ids`` drops routes unconditionally, for example a source
    already serving a concurrent session.

    ``allow_cost_escalation`` permits a listed priority route to sit in a higher
    cost tier than the initial route. It is off by default so that a local-only
    or free-only run cannot silently continue on billed inference; the caller
    must opt in explicitly. Lower tiers than the initial route are always
    admissible: continuing on a cheaper source is a downgrade in spend, and the
    task cost policy still has to allow that tier.

    ``deliberation_port`` plus ``deliberation_question`` opt into council
    steering: verdict ``next_actions`` naming known routes join the priority
    order behind caller-supplied entries. Without both, or on consensus
    ``none`` / port error, ranking is exactly as before.
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
        and (
            cost_policy_allows(entry.backend.cost_policy_tier, initial.cost_policy_tier)
            or (allow_cost_escalation and entry.backend.route_id in priority)
            or entry.backend.billing_source.value in cost_exemptions
        )
        and entry.backend.route_id not in excluded_route_ids
        and entry.backend.billing_source.value not in exhausted_billing_sources
        and entry.backend.route_id not in unavailable_route_ids
        and (
            normal_profile is None
            or quality_rank[entry.quality] < quality_rank[normal_profile.quality_threshold]
        )
    )
    if deliberation_port is not None and deliberation_question:
        known = frozenset(entry.backend.route_id for entry in catalog)
        steered = _verdict_priority_routes(deliberation_port, deliberation_question, known)
        priority = tuple(priority) + tuple(route for route in steered if route not in priority)
    if priority:
        listed = frozenset(priority)
        by_route = {entry.backend.route_id: entry for entry in eligible}
        ranked = [
            entry
            for route_id in priority
            if (entry := by_route.get(route_id)) is not None
            and _accepts(candidate_profile, entry, cost_exemptions)
        ]
        remaining = tuple(entry for entry in eligible if entry.backend.route_id not in listed)
    else:
        ranked = []
        remaining = eligible
    while remaining:
        try:
            chosen = recommend_model(
                candidate_profile,
                remaining,
                cost_exemptions=cost_exemptions,
                allowance_remaining=allowance_remaining,
            ).selected
        except ValueError:
            break
        ranked.append(chosen)
        remaining = tuple(entry for entry in remaining if entry is not chosen)
    # Stable demotion also applies to caller/council priority within each band.
    ranked.sort(
        key=lambda entry: _allowance_rank(entry.backend.route_id, allowance_remaining),
        reverse=True,
    )
    return tuple(ranked)
