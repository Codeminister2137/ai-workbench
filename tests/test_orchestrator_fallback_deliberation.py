"""Council verdicts steer fallback priority behind caller-supplied entries."""

from __future__ import annotations

from typing import Any

from ai_orchestrator import (
    AccessMethod,
    AccessRoute,
    AuthMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    ModelBackend,
    ModelCapabilities,
    ModelCatalogEntry,
    PrivacyClass,
    QualityThreshold,
    TaskCapability,
    TaskProfile,
    TaskType,
    prepare_execution,
)
from ai_orchestrator.fallback import FallbackQualityPolicy, fallback_candidates


def _entry(route: str, quality: QualityThreshold, billing: BillingSource) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=route,
                provider="test",
                product="test",
                model=route,
                location=BackendLocation.EXTERNAL,
                access_method=AccessMethod.CODEX_CLI,
                auth_method=AuthMethod.CHATGPT_SIGN_IN,
                billing_source=billing,
                cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
            ),
            capabilities=ModelCapabilities(chat=True, tools=True),
        ),
        quality=quality,
    )


def _task_and_routes():
    task = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        quality_threshold=QualityThreshold.LOW,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        user_route_id_override="primary",
    )
    catalog = (
        _entry("primary", QualityThreshold.HIGH, BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE),
        _entry("weak", QualityThreshold.LOW, BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE),
        _entry("standard", QualityThreshold.STANDARD, BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE),
        _entry(
            "strong", QualityThreshold.HIGH, BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE
        ),
    )
    prepared = prepare_execution("Implement a fix", task, catalog, review_prompt=False)
    assert prepared.execution_plan is not None
    return task, catalog, prepared.execution_plan.target


class _FakePort:
    def __init__(self, verdict: dict[str, Any] | Exception) -> None:
        self._verdict = verdict
        self.calls = 0

    def deliberate(self, question: str, members: list[dict[str, Any]], *, rounds: int = 3) -> Any:
        self.calls += 1
        if isinstance(self._verdict, Exception):
            raise self._verdict
        return self._verdict


def _verdict(consensus: str, next_actions: list[str]) -> dict[str, Any]:
    return {
        "agreed": ["fallback needed"],
        "disagreements": [],
        "next_actions": next_actions,
        "consensus": consensus,
        "parse_ok": True,
    }


def _routes(entries) -> list[str]:
    return [entry.backend.route_id for entry in entries]


def test_verdict_routes_join_priority_behind_caller_entries() -> None:
    task, catalog, initial = _task_and_routes()
    port = _FakePort(_verdict("partial", ["standard", "ghost-route"]))
    ranked = fallback_candidates(
        task,
        catalog,
        initial,
        quality_policy=FallbackQualityPolicy.TASK_MINIMUM,
        priority=("weak",),
        deliberation_port=port,
        deliberation_question="Which fallback first?",
    )
    assert port.calls == 1
    assert _routes(ranked)[:2] == ["weak", "standard"]


def test_verdict_alone_orders_before_recommender_ranking() -> None:
    task, catalog, initial = _task_and_routes()
    plain = fallback_candidates(
        task, catalog, initial, quality_policy=FallbackQualityPolicy.TASK_MINIMUM
    )
    port = _FakePort(_verdict("full", ["weak"]))
    steered = fallback_candidates(
        task,
        catalog,
        initial,
        quality_policy=FallbackQualityPolicy.TASK_MINIMUM,
        deliberation_port=port,
        deliberation_question="Q?",
    )
    assert port.calls == 1
    assert _routes(steered)[0] == "weak"
    assert steered != plain or _routes(plain)[0] == "weak"


def test_consensus_none_keeps_current_ranking() -> None:
    task, catalog, initial = _task_and_routes()
    plain = fallback_candidates(
        task, catalog, initial, quality_policy=FallbackQualityPolicy.TASK_MINIMUM
    )
    port = _FakePort(_verdict("none", ["weak"]))
    assert (
        fallback_candidates(
            task,
            catalog,
            initial,
            quality_policy=FallbackQualityPolicy.TASK_MINIMUM,
            deliberation_port=port,
            deliberation_question="Q?",
        )
        == plain
    )


def test_port_error_keeps_current_ranking() -> None:
    task, catalog, initial = _task_and_routes()
    plain = fallback_candidates(
        task, catalog, initial, quality_policy=FallbackQualityPolicy.TASK_MINIMUM
    )
    port = _FakePort(RuntimeError("council down"))
    assert (
        fallback_candidates(
            task,
            catalog,
            initial,
            quality_policy=FallbackQualityPolicy.TASK_MINIMUM,
            deliberation_port=port,
            deliberation_question="Q?",
        )
        == plain
    )


def test_flag_off_never_calls_port() -> None:
    task, catalog, initial = _task_and_routes()
    plain = fallback_candidates(
        task, catalog, initial, quality_policy=FallbackQualityPolicy.TASK_MINIMUM
    )
    port = _FakePort(_verdict("full", ["weak"]))
    assert (
        fallback_candidates(
            task,
            catalog,
            initial,
            quality_policy=FallbackQualityPolicy.TASK_MINIMUM,
            deliberation_port=port,
        )
        == plain
    )
    assert (
        fallback_candidates(
            task,
            catalog,
            initial,
            quality_policy=FallbackQualityPolicy.TASK_MINIMUM,
            deliberation_question="Q?",
        )
        == plain
    )
    assert port.calls == 0
