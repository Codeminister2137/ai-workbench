from __future__ import annotations

import pytest
from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    ModelPerformanceEstimate,
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
    estimate: ModelPerformanceEstimate | None = None,
) -> ModelCatalogEntry:
    access_method = (
        AccessMethod.LOCAL_RUNTIME
        if location is BackendLocation.LOCAL
        else AccessMethod.PROVIDER_API
    )
    auth_method = AuthMethod.NONE if location is BackendLocation.LOCAL else AuthMethod.API_KEY
    if location is BackendLocation.LOCAL:
        billing_source = BillingSource.LOCAL_FREE
        cost_policy_tier = CostPolicyTier.LOCAL_ONLY
    elif provider == "requesty":
        billing_source = BillingSource.REQUESTY_BILLING
        cost_policy_tier = CostPolicyTier.ALLOWANCES_ALLOWED
    else:
        billing_source = BillingSource.OPENAI_API_BILLING
        cost_policy_tier = CostPolicyTier.BILLING_ALLOWED
    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=f"{provider}-{model}",
                provider=provider,
                product=provider,
                model=model,
                location=location,
                access_method=access_method,
                auth_method=auth_method,
                billing_source=billing_source,
                cost_policy_tier=cost_policy_tier,
            ),
            capabilities=capabilities or ModelCapabilities(),
            estimate=estimate or ModelPerformanceEstimate(),
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
            route=AccessRoute(
                route_id="ollama-background",
                provider="ollama",
                product="ollama",
                model="background",
                location=BackendLocation.LOCAL,
                access_method=AccessMethod.LOCAL_RUNTIME,
                auth_method=AuthMethod.NONE,
                billing_source=BillingSource.LOCAL_FREE,
                cost_policy_tier=CostPolicyTier.LOCAL_ONLY,
            ),
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


def test_recommender_includes_numeric_estimates_when_available() -> None:
    candidate = _candidate(
        "ollama",
        "llama3.2",
        BackendLocation.LOCAL,
        estimate=ModelPerformanceEstimate(
            typical_latency_seconds=12,
            input_cost_per_million_tokens=0,
            output_cost_per_million_tokens=0,
            source="local benchmark",
        ),
    )

    recommendation = recommend_model(TaskProfile(), (candidate,))

    assert any("typical latency 12s" in reason for reason in recommendation.reasons)
    assert any("input $0/1M tokens" in reason for reason in recommendation.reasons)
    assert any("Source: local benchmark" in reason for reason in recommendation.reasons)


def test_recommender_filters_by_max_expected_latency_seconds() -> None:
    slow = _candidate(
        "ollama",
        "slow",
        BackendLocation.LOCAL,
        estimate=ModelPerformanceEstimate(typical_latency_seconds=120),
    )
    fast = _candidate(
        "ollama",
        "fast",
        BackendLocation.LOCAL,
        estimate=ModelPerformanceEstimate(typical_latency_seconds=20),
    )

    recommendation = recommend_model(
        TaskProfile(max_expected_latency_seconds=60),
        (slow, fast),
    )

    assert recommendation.selected is fast
    assert "120s" in recommendation.rejected[0].reason
    assert "60s" in recommendation.rejected[0].reason


def test_recommender_rejects_missing_latency_for_hard_latency_constraint() -> None:
    candidate = _candidate("ollama", "unknown", BackendLocation.LOCAL)

    with pytest.raises(ValueError, match="no latency estimate"):
        recommend_model(TaskProfile(max_expected_latency_seconds=60), (candidate,))


def test_recommender_rejects_routes_above_task_cost_policy() -> None:
    paid = _candidate("openai", "gpt-5.1", BackendLocation.EXTERNAL)
    allowance = _candidate("requesty", "openai/gpt-5.1", BackendLocation.EXTERNAL)

    recommendation = recommend_model(
        TaskProfile(
            privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
            cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        ),
        (paid, allowance),
    )

    assert recommendation.selected is allowance
    assert recommendation.rejected[0].candidate is paid
    assert "billing_allowed" in recommendation.rejected[0].reason


def test_recommender_applies_route_override_as_hard_constraint() -> None:
    first = _candidate("ollama", "first", BackendLocation.LOCAL)
    second = _candidate("ollama", "second", BackendLocation.LOCAL)

    recommendation = recommend_model(
        TaskProfile(user_route_id_override="ollama-second"),
        (first, second),
    )

    assert recommendation.selected is second
    assert recommendation.rejected[0].candidate is first
