from __future__ import annotations

import pytest
from ai_orchestrator import (
    BackendLocation,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    recommend_model,
)


def _candidate(
    provider: str,
    model: str,
    location: BackendLocation,
    *,
    quality: QualityThreshold = QualityThreshold.STANDARD,
    capabilities: ModelCapabilities | None = None,
) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        backend=ModelBackend(
            provider=provider,
            model=model,
            location=location,
            capabilities=capabilities or ModelCapabilities(),
        ),
        quality=quality,
        latency=LatencyTarget.INTERACTIVE,
    )


def test_recommender_filters_external_candidates_for_local_only_tasks() -> None:
    local = _candidate("ollama", "llama3.2", BackendLocation.LOCAL)
    external = _candidate("requesty", "hosted-model", BackendLocation.EXTERNAL)

    recommendation = recommend_model(
        TaskProfile(privacy_class=PrivacyClass.LOCAL_ONLY),
        (external, local),
    )

    assert recommendation.selected is local
    assert recommendation.rejected[0].candidate is external
    assert "local-only" in recommendation.rejected[0].reason


def test_recommender_filters_by_required_capability() -> None:
    chat_only = _candidate("ollama", "llama3.2", BackendLocation.LOCAL)
    structured = _candidate(
        "local",
        "structured-model",
        BackendLocation.LOCAL,
        capabilities=ModelCapabilities(structured_output=True),
    )

    recommendation = recommend_model(
        TaskProfile(
            required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.STRUCTURED_OUTPUT})
        ),
        (chat_only, structured),
    )

    assert recommendation.selected is structured
    assert recommendation.rejected[0].candidate is chat_only


def test_recommender_applies_user_override_as_hard_constraint() -> None:
    first = _candidate("ollama", "first", BackendLocation.LOCAL)
    second = _candidate("ollama", "second", BackendLocation.LOCAL)

    recommendation = recommend_model(
        TaskProfile(user_model_override="second"),
        (first, second),
    )

    assert recommendation.selected is second
    assert recommendation.rejected[0].candidate is first


def test_recommender_explains_when_no_candidate_matches() -> None:
    external = _candidate("requesty", "hosted-model", BackendLocation.EXTERNAL)

    with pytest.raises(ValueError, match="No model candidate"):
        recommend_model(TaskProfile(privacy_class=PrivacyClass.LOCAL_ONLY), (external,))


def test_recommender_filters_by_quality_threshold() -> None:
    low = _candidate(
        "ollama",
        "small",
        BackendLocation.LOCAL,
        quality=QualityThreshold.LOW,
    )
    high = _candidate(
        "ollama",
        "large",
        BackendLocation.LOCAL,
        quality=QualityThreshold.HIGH,
    )

    recommendation = recommend_model(
        TaskProfile(quality_threshold=QualityThreshold.HIGH),
        (low, high),
    )

    assert recommendation.selected is high
    assert "quality threshold" in recommendation.rejected[0].reason


def test_recommender_prefers_matching_latency_when_quality_is_equal() -> None:
    background = ModelCatalogEntry(
        backend=ModelBackend(
            provider="ollama",
            model="background",
            location=BackendLocation.LOCAL,
            capabilities=ModelCapabilities(),
        ),
        quality=QualityThreshold.STANDARD,
        latency=LatencyTarget.BACKGROUND,
    )
    interactive = _candidate("ollama", "interactive", BackendLocation.LOCAL)

    recommendation = recommend_model(
        TaskProfile(latency_target=LatencyTarget.INTERACTIVE),
        (background, interactive),
    )

    assert recommendation.selected is interactive


def test_recommender_rejects_sensitive_review_external_candidate() -> None:
    local = _candidate("ollama", "local", BackendLocation.LOCAL)
    external = _candidate("requesty", "hosted", BackendLocation.EXTERNAL)

    recommendation = recommend_model(
        TaskProfile(privacy_class=PrivacyClass.SENSITIVE_REVIEW_REQUIRED),
        (external, local),
    )

    assert recommendation.selected is local
    assert "sensitive external processing" in recommendation.rejected[0].reason
