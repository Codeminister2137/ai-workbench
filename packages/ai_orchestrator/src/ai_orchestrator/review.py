"""Explainable reviewer selection and resource admission, independent of providers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from ai_orchestrator.models import ModelCatalogEntry, TaskProfile
from ai_orchestrator.recommender import recommend_model


class ReviewMode(StrEnum):
    DEFAULT = "default"
    DIRECT = "direct"
    DELIBERATIVE = "deliberative"


@dataclass(frozen=True, slots=True)
class ReviewWorkload:
    """Declared review needs; short inputs alone never establish simplicity."""

    purpose: str = "final_grounding"
    complexity: str = "unknown"
    coverage_complete: bool = False
    prior_failures: int = 0
    direct_evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.purpose.strip():
            raise ValueError("Review purpose must not be empty")
        if self.complexity not in {"unknown", "simple", "complex"}:
            raise ValueError("Review complexity must be unknown, simple, or complex")
        if (
            isinstance(self.prior_failures, bool)
            or not isinstance(self.prior_failures, int)
            or self.prior_failures < 0
        ):
            raise ValueError("Prior failures must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    candidate: ModelCatalogEntry
    mode: ReviewMode
    reasons: tuple[str, ...]


def select_review_plan(
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
    workload: ReviewWorkload,
    *,
    mode_override: ReviewMode | None = None,
    primary_model: str | None = None,
) -> ReviewPlan:
    """Apply hard route constraints before selecting a supported review preset.

    Catalog review_deliberative/review_direct booleans declare preset support.
    Absence never implies support. Direct evidence is scoped to this workload by
    the caller; no fictional comparison is promoted into general review evidence.
    """
    direct_supported = (
        workload.complexity == "simple"
        and workload.coverage_complete
        and workload.prior_failures == 0
        and bool(workload.direct_evidence_reference and workload.direct_evidence_reference.strip())
    )
    mode = mode_override or (ReviewMode.DIRECT if direct_supported else ReviewMode.DELIBERATIVE)
    supported = tuple(
        entry
        for entry in catalog
        if mode is ReviewMode.DEFAULT or entry.metadata.get(f"review_{mode.value}") is True
    )
    if not supported:
        raise ValueError(f"No catalog model declares support for review mode {mode.value}")
    recommendation = recommend_model(profile, supported)
    selected = recommendation.selected
    reasons = list(recommendation.reasons)
    # Prefer variety only among eligible peers at the same quality tier, without
    # using generic latency estimates as research-quality evidence.
    if primary_model == selected.backend.model:
        peers = tuple(
            entry
            for entry in supported
            if entry.backend.model != primary_model and entry.quality == selected.quality
        )
        if peers:
            try:
                alternative = recommend_model(profile, peers)
            except ValueError:
                pass  # Hard overrides may deliberately select the primary model.
            else:
                selected = alternative.selected
                reasons = list(alternative.reasons)
                reasons.append("Preferred a different eligible reviewer at the same quality tier.")
    reasons.append(f"Review purpose: {workload.purpose}.")
    if mode_override is not None:
        reasons.append(f"Explicit review mode override: {mode.value}.")
    elif direct_supported:
        reasons.append(
            f"Direct review supported by workload evidence: {workload.direct_evidence_reference}."
        )
    else:
        reasons.append(
            "Deliberative review: unknown/complex needs, incomplete coverage, "
            "or no direct evidence."
        )
    if selected.backend.model == primary_model:
        reasons.append("Same-model review is not independent verification.")
    return ReviewPlan(selected, mode, tuple(reasons))


@dataclass(frozen=True, slots=True)
class ReviewSettings:
    """Approved experimental bounds, rather than a claim of optimal settings."""

    max_output_tokens: int = 4096
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 2048 <= self.max_output_tokens <= 8192
        ):
            raise ValueError("Review output allowance must be an integer from 2048 to 8192")
        if (
            isinstance(self.timeout_seconds, bool)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 300
        ):
            raise ValueError("Review timeout must be positive, finite, and at most 300 seconds")


@dataclass(frozen=True, slots=True)
class ReviewAllocation:
    max_output_tokens: int
    timeout_seconds: float


def allocate_review(
    settings: ReviewSettings,
    *,
    context_tokens: int,
    input_token_upper_bound: int,
    remaining_seconds: float,
    prior_output_tokens: int | None = None,
) -> ReviewAllocation:
    """Admit a full-evidence request, or one stronger length retry, within bounds.

    Leave 256 context tokens for runtime framing. The caller supplies a conservative
    input bound; source/report evidence must never be trimmed to force admission.
    """
    if (
        isinstance(context_tokens, bool)
        or not isinstance(context_tokens, int)
        or context_tokens <= 0
        or isinstance(input_token_upper_bound, bool)
        or not isinstance(input_token_upper_bound, int)
        or input_token_upper_bound < 0
    ):
        raise ValueError("Context and input token bounds must be valid integers")
    if not math.isfinite(remaining_seconds) or remaining_seconds <= 0:
        raise ValueError("No finite review time remains")
    headroom = context_tokens - input_token_upper_bound - 256
    output = min(settings.max_output_tokens, headroom)
    if prior_output_tokens is not None:
        if (
            isinstance(prior_output_tokens, bool)
            or not isinstance(prior_output_tokens, int)
            or not 2048 <= prior_output_tokens <= 8192
        ):
            raise ValueError("Invalid prior review output allowance")
        output = min(8192, prior_output_tokens * 2, headroom)
        if output <= prior_output_tokens:
            raise ValueError("No context headroom for a stronger truncation retry")
    if output < 2048:
        raise ValueError("Insufficient context headroom for review; evidence was preserved")
    return ReviewAllocation(output, min(settings.timeout_seconds, remaining_seconds))


def research_review_reserve_seconds(budget_seconds: float, *, enabled: bool) -> float:
    """Keep the legacy reserve until the research policy is explicitly selected."""
    from ai_orchestrator.repair import review_reserve_seconds

    return review_reserve_seconds(budget_seconds, cap_seconds=300.0 if enabled else 120.0)
