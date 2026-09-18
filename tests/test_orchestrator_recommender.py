from __future__ import annotations

import pytest
from ai_orchestrator import (
    LatencyTarget,
    ModelCatalogEntry,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    recommend_model,
)
from ai_provider import BackendInfo, BackendLocation, ModelCapabilities, PrivacyClass


def _candidate(
    provider: str,
    model: str,
    location: BackendLocation,
    *,
    quality: QualityThreshold = QualityThreshold.STANDARD,
    capabilities: ModelCapabilities | None = None,
) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        backend=BackendInfo(
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
