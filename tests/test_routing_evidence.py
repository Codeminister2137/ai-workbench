"""Routing evidence: outcomes, demotions, cheap-first simple tasks."""

from __future__ import annotations

from argparse import Namespace

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
    TaskProfile,
    prepare_execution,
    recommend_model,
)
from ai_orchestrator.route_outcomes import (
    RouteOutcome,
    append_outcome,
    load_outcomes,
    quality_adjustments,
)


def _candidate(
    provider: str,
    model: str,
    location: BackendLocation,
    *,
    quality: QualityThreshold = QualityThreshold.STANDARD,
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
            capabilities=ModelCapabilities(),
            estimate=ModelPerformanceEstimate(),
        ),
        quality=quality,
        latency=LatencyTarget.INTERACTIVE,
    )


def _outcome(route_id: str, success: bool, *, at: float = 9_999_999_999.0) -> RouteOutcome:
    return RouteOutcome(
        route_id=route_id,
        mode="implement",
        success=success,
        tool_calls=2,
        iterations=3,
        finished_at=at,
    )


def test_outcomes_round_trip_newest_first(tmp_path) -> None:
    path = tmp_path / "route-outcomes.jsonl"
    append_outcome(path, _outcome("a", True, at=100.0))
    append_outcome(path, _outcome("b", False, at=200.0))
    loaded = load_outcomes(path, window_hours=9_999_999.0)
    assert [item.route_id for item in loaded] == ["b", "a"]


def test_outcomes_skip_missing_corrupt_and_stale(tmp_path) -> None:
    assert load_outcomes(tmp_path / "absent.jsonl") == ()
    path = tmp_path / "route-outcomes.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    append_outcome(path, _outcome("stale", True, at=1.0))
    assert load_outcomes(path) == ()


def test_adjustments_demote_only_repeated_failures() -> None:
    failed = tuple(_outcome("flaky", False) for _ in range(3))
    assert quality_adjustments(failed) == {"flaky": -1}
    mixed = tuple(_outcome("mixed", ok) for ok in (False, False, True))
    assert quality_adjustments(mixed) == {}
    thin = tuple(_outcome("thin", False) for _ in range(2))
    assert quality_adjustments(thin) == {}
    assert all(value <= 0 for value in quality_adjustments(failed).values())


def test_demotion_flips_selection_to_healthy_route() -> None:
    strong = _candidate("openai", "strong", BackendLocation.EXTERNAL, quality=QualityThreshold.HIGH)
    steady = _candidate("ollama", "steady", BackendLocation.LOCAL)
    profile = TaskProfile(
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )
    catalog = (strong, steady)
    assert recommend_model(profile, catalog).selected is strong
    demoted = recommend_model(profile, catalog, quality_adjustments={"openai-strong": -1})
    assert demoted.selected is steady
    assert any("demoted" in reason for reason in demoted.reasons)


def test_simple_tasks_prefer_cheaper_sufficient_route() -> None:
    pricey = _candidate("openai", "pricey", BackendLocation.EXTERNAL)
    thrifty = _candidate("requesty", "thrifty", BackendLocation.EXTERNAL)
    profile = TaskProfile(privacy_class=PrivacyClass.EXTERNAL_ALLOWED, complexity="simple")
    selected = recommend_model(profile, (pricey, thrifty)).selected
    assert selected is thrifty
    assert any(
        "cheapest" in reason for reason in recommend_model(profile, (pricey, thrifty)).reasons
    )


def test_unknown_complexity_keeps_quality_first() -> None:
    strong = _candidate("openai", "strong", BackendLocation.EXTERNAL, quality=QualityThreshold.HIGH)
    thrifty = _candidate("requesty", "thrifty", BackendLocation.EXTERNAL)
    profile = TaskProfile(
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )
    assert recommend_model(profile, (thrifty, strong)).selected is strong


def test_invalid_complexity_rejected() -> None:
    candidate = _candidate("ollama", "x", BackendLocation.LOCAL)
    with pytest.raises(ValueError, match="complexity"):
        recommend_model(TaskProfile(complexity="trivial"), (candidate,))


def test_prepare_execution_threads_adjustments() -> None:
    strong = _candidate("openai", "strong", BackendLocation.EXTERNAL, quality=QualityThreshold.HIGH)
    steady = _candidate("ollama", "steady", BackendLocation.LOCAL)
    profile = TaskProfile(
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
    )
    result = prepare_execution(
        "do it",
        profile,
        (strong, steady),
        review_prompt=False,
        quality_adjustments={"openai-strong": -1},
    )
    assert result.recommendation is not None
    assert result.recommendation.selected is steady


def test_resolve_complexity_auto_and_explicit() -> None:
    from ai_agent.repo_coding_assistant import _resolve_complexity

    assert _resolve_complexity(Namespace(complexity="simple", mode="x", prompt="")) == "simple"
    assert _resolve_complexity(Namespace(complexity="complex", mode="x", prompt="")) == "complex"
    assert (
        _resolve_complexity(Namespace(complexity="auto", mode="ask", prompt="short?")) == "simple"
    )
    assert (
        _resolve_complexity(Namespace(complexity="auto", mode="ask", prompt="x" * 500)) == "unknown"
    )
    assert (
        _resolve_complexity(Namespace(complexity="auto", mode="implement", prompt="short"))
        == "unknown"
    )


def test_record_outcome_appends_and_skips(tmp_path) -> None:
    from ai_agent.repo_coding_assistant import _record_route_outcome

    args = Namespace(
        mode="implement",
        route_outcomes_path=str(tmp_path / "artifacts" / "route-outcomes.jsonl"),
    )
    _record_route_outcome(args=args, route_id="ollama/x", execution_status="completed")
    lines = (tmp_path / "artifacts" / "route-outcomes.jsonl").read_text(encoding="utf-8")
    assert '"route_id": "ollama/x"' in lines and '"success": true' in lines
    # Planned dry runs and missing routes record nothing.
    _record_route_outcome(args=args, route_id="ollama/x", execution_status="planned")
    _record_route_outcome(args=args, route_id=None, execution_status="completed")
    assert len(lines.splitlines()) == 1
