from __future__ import annotations

from ai_orchestrator.models import (
    CandidateRejection,
    ModelCatalogEntry,
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

    return None


def _candidate_score(profile: TaskProfile, candidate: ModelCatalogEntry) -> tuple[int, int, int]:
    quality = _QUALITY_RANK[candidate.quality]
    latency = 1 if candidate.latency is profile.latency_target else 0
    locality = 1 if not is_external_backend(candidate) else 0
    return quality, latency, locality
