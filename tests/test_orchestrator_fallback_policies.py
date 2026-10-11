"""Fallback policy ranking keeps downgrade scope and hard boundaries explicit."""

from dataclasses import replace

import pytest
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
from ai_orchestrator.fallback import FallbackQualityPolicy, fallback_candidates, fallback_profile


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


@pytest.fixture
def task_and_routes():
    task = TaskProfile(
        task_type=TaskType.CODING,
        privacy_class=PrivacyClass.EXTERNAL_ALLOWED,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        quality_threshold=QualityThreshold.HIGH,
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


def test_emergency_preservation_keeps_normal_floor_and_separate_weaker_routes(task_and_routes):
    task, catalog, initial = task_and_routes
    normal = fallback_candidates(
        task, catalog, initial, quality_policy=FallbackQualityPolicy.EMERGENCY_PRESERVE
    )
    preservation = fallback_candidates(
        task,
        catalog,
        initial,
        quality_policy=FallbackQualityPolicy.EMERGENCY_PRESERVE,
        preservation_only=True,
    )
    assert normal == (catalog[3],)
    assert preservation == (catalog[2], catalog[1])
    assert fallback_candidates(task, catalog, initial) == normal


def test_emergency_original_grade_floor_exceeds_task_minimum(task_and_routes):
    task, catalog, initial = task_and_routes
    standard_task = replace(task, quality_threshold=QualityThreshold.STANDARD)
    assert fallback_candidates(
        standard_task, catalog, initial, quality_policy=FallbackQualityPolicy.EMERGENCY_PRESERVE
    ) == (catalog[3],)
    assert fallback_candidates(
        standard_task, catalog, initial, quality_policy=FallbackQualityPolicy.TASK_MINIMUM
    ) == (catalog[3], catalog[2])


@pytest.mark.parametrize(
    ("policy", "preservation"),
    [
        (FallbackQualityPolicy.EMERGENCY_PRESERVE, True),
        (FallbackQualityPolicy.PREFER_QUALITY, False),
    ],
)
def test_downgrade_keeps_latency_constraint(task_and_routes, policy, preservation):
    task, catalog, initial = task_and_routes
    task = replace(task, max_expected_latency_seconds=10)
    weak = catalog[1]
    slow = replace(
        weak,
        backend=replace(
            weak.backend,
            estimate=replace(weak.backend.estimate, typical_latency_seconds=20),
        ),
    )
    fast = replace(
        weak,
        backend=replace(
            weak.backend,
            estimate=replace(weak.backend.estimate, typical_latency_seconds=5),
        ),
    )
    for forbidden in (weak, slow):
        assert (
            fallback_candidates(
                task,
                (catalog[0], forbidden),
                initial,
                quality_policy=policy,
                preservation_only=preservation,
            )
            == ()
        )
    assert fallback_candidates(
        task,
        (catalog[0], fast),
        initial,
        quality_policy=policy,
        preservation_only=preservation,
    ) == (fast,)


def test_prefer_quality_continues_below_task_floor_after_comparable_routes(task_and_routes):
    task, catalog, initial = task_and_routes
    assert fallback_candidates(
        task, catalog, initial, quality_policy=FallbackQualityPolicy.PREFER_QUALITY
    ) == (catalog[3], catalog[2], catalog[1])
    assert fallback_candidates(
        task,
        catalog,
        initial,
        quality_policy=FallbackQualityPolicy.PREFER_QUALITY,
        unavailable_route_ids=frozenset({"strong", "standard"}),
    ) == (catalog[1],)


def test_derived_profiles_are_preparable_and_distinguish_implementation_from_handoff(
    task_and_routes,
):
    task, catalog, initial = task_and_routes
    for preservation in (False, True):
        policy = (
            FallbackQualityPolicy.EMERGENCY_PRESERVE
            if preservation
            else FallbackQualityPolicy.PREFER_QUALITY
        )
        derived = fallback_profile(
            task, initial, catalog, quality_policy=policy, preservation_only=preservation
        )
        assert derived is not None
        assert derived.quality_threshold is QualityThreshold.LOW
        assert derived.privacy_class is task.privacy_class
        assert derived.cost_policy_tier is task.cost_policy_tier
        assert derived.task_type is (TaskType.SUMMARIZATION if preservation else TaskType.CODING)
        selected = replace(derived, user_route_id_override="weak")
        prepared = prepare_execution("Report existing work", selected, catalog, review_prompt=False)
        assert prepared.execution_plan is not None
        assert prepared.execution_plan.target.route_id == "weak"


@pytest.mark.parametrize(
    ("policy", "preservation"),
    [
        (FallbackQualityPolicy.EMERGENCY_PRESERVE, False),
        (FallbackQualityPolicy.EMERGENCY_PRESERVE, True),
        (FallbackQualityPolicy.PREFER_QUALITY, False),
    ],
)
def test_new_policies_refuse_unknown_original_model(task_and_routes, policy, preservation):
    task, catalog, initial = task_and_routes
    unknown = replace(initial, model="ungraded-override")
    assert (
        fallback_profile(
            task, unknown, catalog, quality_policy=policy, preservation_only=preservation
        )
        is None
    )
    assert (
        fallback_candidates(
            task, catalog, unknown, quality_policy=policy, preservation_only=preservation
        )
        == ()
    )


@pytest.mark.parametrize(
    ("policy", "preservation"),
    [
        (FallbackQualityPolicy.EMERGENCY_PRESERVE, True),
        (FallbackQualityPolicy.PREFER_QUALITY, False),
    ],
)
def test_downgrade_never_bypasses_privacy_capabilities_cost_or_billing(
    task_and_routes, policy, preservation
):
    task, catalog, initial = task_and_routes
    weak = catalog[1]
    paid = replace(
        weak,
        backend=replace(
            weak.backend,
            route=replace(weak.backend.route, cost_policy_tier=CostPolicyTier.BILLING_ALLOWED),
        ),
    )
    no_tools = replace(
        weak, backend=replace(weak.backend, capabilities=ModelCapabilities(chat=True))
    )
    sibling = replace(
        weak,
        backend=replace(
            weak.backend,
            route=replace(
                weak.backend.route, billing_source=BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE
            ),
        ),
    )
    for forbidden in (paid, no_tools, sibling):
        assert (
            fallback_candidates(
                task,
                (catalog[0], forbidden),
                initial,
                quality_policy=policy,
                preservation_only=preservation,
            )
            == ()
        )
    for privacy in (PrivacyClass.LOCAL_ONLY, PrivacyClass.SENSITIVE_REVIEW_REQUIRED):
        assert (
            fallback_candidates(
                replace(task, privacy_class=privacy),
                catalog,
                initial,
                quality_policy=policy,
                preservation_only=preservation,
            )
            == ()
        )
    assert (
        fallback_candidates(
            task,
            (catalog[0], weak),
            initial,
            quality_policy=policy,
            preservation_only=preservation,
            exhausted_billing_sources=frozenset({BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE.value}),
        )
        == ()
    )
    assert fallback_candidates(
        task,
        (catalog[0], sibling),
        initial,
        quality_policy=policy,
        preservation_only=preservation,
        allow_initial_billing_source=True,
    ) == (sibling,)


@pytest.mark.parametrize(
    "policy",
    [
        FallbackQualityPolicy.PRESERVE_QUALITY,
        FallbackQualityPolicy.TASK_MINIMUM,
        FallbackQualityPolicy.PREFER_QUALITY,
    ],
)
def test_preservation_query_cannot_enable_downgrade_for_other_policies(task_and_routes, policy):
    task, catalog, initial = task_and_routes
    assert (
        fallback_candidates(task, catalog, initial, quality_policy=policy, preservation_only=True)
        == ()
    )
