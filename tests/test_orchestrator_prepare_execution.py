from __future__ import annotations

from ai_orchestrator import (
    BackendLocation,
    LatencyTarget,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    OrchestrationStatus,
    PrivacyClass,
    QualityThreshold,
    TaskProfile,
    prepare_execution,
)


def _candidate(
    provider: str = "ollama",
    model: str = "llama3.2",
    location: BackendLocation = BackendLocation.LOCAL,
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


def test_prepare_execution_returns_plan_for_specific_prompt() -> None:
    catalog = (_candidate(),)

    result = prepare_execution(
        "Explain how to run the provider tests as a numbered list with short commands.",
        TaskProfile(),
        catalog,
        timeout_seconds=15,
    )

    assert result.status is OrchestrationStatus.READY
    assert result.is_ready is True
    assert result.prompt_judge is not None
    assert result.prompt_judge.should_refine is False
    assert result.recommendation is not None
    assert result.execution_plan is not None
    assert result.execution_plan.target.model == "llama3.2"
    assert result.execution_plan.target.timeout_seconds == 15


def test_prepare_execution_stops_for_prompt_review_when_context_is_missing() -> None:
    catalog = (_candidate(),)

    result = prepare_execution("Fix this", TaskProfile(), catalog)

    assert result.status is OrchestrationStatus.NEEDS_PROMPT_REVIEW
    assert result.is_ready is False
    assert result.prompt_judge is not None
    assert result.prompt_judge.should_refine is True
    assert result.recommendation is None
    assert result.execution_plan is None


def test_prepare_execution_stops_for_prompt_review_when_prompt_is_blocking() -> None:
    catalog = (_candidate(),)

    result = prepare_execution("   ", TaskProfile(), catalog)

    assert result.status is OrchestrationStatus.NEEDS_PROMPT_REVIEW
    assert result.prompt_judge is not None
    assert result.recommendation is None
    assert result.execution_plan is None


def test_prepare_execution_keeps_sensitive_review_on_local_backend() -> None:
    local = _candidate()
    external = _candidate("requesty", "hosted-model", BackendLocation.EXTERNAL)

    result = prepare_execution(
        "Summarize these private notes as a bullet list.",
        TaskProfile(privacy_class=PrivacyClass.SENSITIVE_REVIEW_REQUIRED),
        (external, local),
    )

    assert result.status is OrchestrationStatus.READY
    assert result.recommendation is not None
    assert result.recommendation.selected is local
    assert result.recommendation.rejected[0].candidate is external


def test_prepare_execution_applies_user_override_to_plan() -> None:
    first = _candidate(model="first")
    second = _candidate(model="second")

    result = prepare_execution(
        "Explain the test command as a short numbered list.",
        TaskProfile(user_model_override="second"),
        (first, second),
    )

    assert result.status is OrchestrationStatus.READY
    assert result.recommendation is not None
    assert result.recommendation.selected is second
    assert result.execution_plan is not None
    assert result.execution_plan.target.model == "second"


def test_prepare_execution_can_bypass_prompt_review() -> None:
    catalog = (_candidate(),)

    result = prepare_execution("Fix this", TaskProfile(), catalog, review_prompt=False)

    assert result.status is OrchestrationStatus.READY
    assert result.prompt_judge is None
    assert result.execution_plan is not None


def test_prepare_execution_returns_failure_when_no_model_matches() -> None:
    external = _candidate("requesty", "hosted-model", BackendLocation.EXTERNAL)

    result = prepare_execution(
        "Explain the test command as a numbered list.",
        TaskProfile(privacy_class=PrivacyClass.LOCAL_ONLY),
        (external,),
    )

    assert result.status is OrchestrationStatus.MODEL_SELECTION_FAILED
    assert result.is_ready is False
    assert result.recommendation is None
    assert result.execution_plan is None
    assert result.failure_reason is not None
    assert "No model candidate" in result.failure_reason


def test_prepare_execution_returns_failure_when_catalog_is_empty() -> None:
    result = prepare_execution(
        "Explain the test command as a numbered list.",
        TaskProfile(),
        (),
    )

    assert result.status is OrchestrationStatus.MODEL_SELECTION_FAILED
    assert result.failure_reason == "Model catalog must not be empty."
