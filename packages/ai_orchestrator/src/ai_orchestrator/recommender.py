"""Capability, privacy, and preference based model recommendation."""

from __future__ import annotations

from ai_orchestrator.models import (
    CandidateRejection,
    ModelCatalogEntry,
    ModelPerformanceEstimate,
    ModelRecommendation,
    PrivacyClass,
    QualityThreshold,
    TaskProfile,
    is_external_backend,
    supports_capability,
)

_QUALITY_RANK = {
    QualityThreshold.LOW: 0,
    QualityThreshold.STANDARD: 1,
    QualityThreshold.HIGH: 2,
}


def recommend_model(
    profile: TaskProfile,
    catalog: tuple[ModelCatalogEntry, ...],
) -> ModelRecommendation:
    """Select the best catalog candidate for a task profile."""

    if not catalog:
        raise ValueError("Model catalog must not be empty.")

    accepted: list[ModelCatalogEntry] = []
    rejected: list[CandidateRejection] = []

    for candidate in catalog:
        reason = _rejection_reason(profile, candidate)
        if reason:
            rejected.append(CandidateRejection(candidate=candidate, reason=reason))
        else:
            accepted.append(candidate)

    if not accepted:
        reasons = tuple(rejection.reason for rejection in rejected)
        raise ValueError(f"No model candidate satisfied the task profile: {reasons}")

    accepted.sort(key=lambda candidate: _candidate_score(profile, candidate), reverse=True)
    selected = accepted[0]
    alternatives = tuple(accepted[1:4])

    reasons = [
        f"Selected {selected.backend.provider}/{selected.backend.model}.",
        "Candidates were filtered by privacy before capability and quality.",
    ]
    estimate_reason = _estimate_reason(selected.backend.estimate)
    if estimate_reason:
        reasons.append(estimate_reason)
    if profile.user_backend_override or profile.user_model_override:
        reasons.append("User override was applied as a hard constraint.")

    return ModelRecommendation(
        selected=selected,
        alternatives=alternatives,
        rejected=tuple(rejected),
        reasons=tuple(reasons),
    )


def _rejection_reason(profile: TaskProfile, candidate: ModelCatalogEntry) -> str | None:
    if (
        profile.user_backend_override
        and candidate.backend.provider != profile.user_backend_override
    ):
        return "Rejected by user backend override."

    if profile.user_model_override and candidate.backend.model != profile.user_model_override:
        return "Rejected by user model override."

    if profile.privacy_class is PrivacyClass.LOCAL_ONLY and is_external_backend(candidate):
        return "Rejected because task is local-only and candidate is external."

    if profile.privacy_class is PrivacyClass.SENSITIVE_REVIEW_REQUIRED and is_external_backend(
        candidate
    ):
        return "Rejected because sensitive external processing requires review."

    for capability in profile.required_capabilities:
        if not supports_capability(candidate.backend.capabilities, capability):
            return f"Rejected because candidate lacks required capability: {capability.value}."

    if _QUALITY_RANK[candidate.quality] < _QUALITY_RANK[profile.quality_threshold]:
        return "Rejected because candidate does not meet the quality threshold."

    if profile.max_expected_latency_seconds is not None:
        estimate = candidate.backend.estimate
        if estimate.typical_latency_seconds is None:
            return "Rejected because no latency estimate is available for the time constraint."
        if estimate.typical_latency_seconds > profile.max_expected_latency_seconds:
            return (
                "Rejected because estimated latency "
                f"({estimate.typical_latency_seconds:g}s) exceeds the time constraint "
                f"({profile.max_expected_latency_seconds:g}s)."
            )

    return None


def _candidate_score(profile: TaskProfile, candidate: ModelCatalogEntry) -> tuple[int, int, int]:
    quality = _QUALITY_RANK[candidate.quality]
    latency = 1 if candidate.latency is profile.latency_target else 0
    locality = 1 if not is_external_backend(candidate) else 0
    return quality, latency, locality


def _estimate_reason(estimate: ModelPerformanceEstimate) -> str | None:
    parts: list[str] = []
    if estimate.typical_latency_seconds is not None:
        parts.append(f"typical latency {estimate.typical_latency_seconds:g}s")
    if estimate.input_cost_per_million_tokens is not None:
        parts.append(f"input ${estimate.input_cost_per_million_tokens:g}/1M tokens")
    if estimate.output_cost_per_million_tokens is not None:
        parts.append(f"output ${estimate.output_cost_per_million_tokens:g}/1M tokens")
    if not parts:
        return None

    source = f" Source: {estimate.source}." if estimate.source else ""
    return f"Selected model estimates: {', '.join(parts)}.{source}"
