"""Neutral research selection, mode capability, and resource-envelope contracts."""

from dataclasses import replace
from pathlib import Path

import pytest
from ai_orchestrator.catalog import load_model_catalog
from ai_orchestrator.models import (
    BackendLocation,
    CostPolicyTier,
    PrivacyClass,
    TaskCapability,
    TaskProfile,
)
from ai_orchestrator.review import (
    ReviewMode,
    ReviewSettings,
    ReviewWorkload,
    allocate_review,
    research_review_reserve_seconds,
    select_review_plan,
)


@pytest.fixture
def catalog():
    return load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))


@pytest.fixture
def profile():
    return TaskProfile(
        privacy_class=PrivacyClass.LOCAL_ONLY, cost_policy_tier=CostPolicyTier.LOCAL_ONLY
    )


def test_unknown_final_review_prefers_supported_deliberation_and_variety(profile, catalog):
    plan = select_review_plan(profile, catalog, ReviewWorkload(), primary_model="gpt-oss:20b")
    assert plan.mode is ReviewMode.DELIBERATIVE
    assert plan.candidate.backend.model == "qwen3:14b"
    assert any("different eligible reviewer" in reason for reason in plan.reasons)
    assert any("no direct evidence" in reason for reason in plan.reasons)
    assert "Review purpose: final_grounding." in plan.reasons


def test_review_purpose_and_prior_failure_inputs_are_validated():
    with pytest.raises(ValueError, match="purpose"):
        ReviewWorkload(purpose=" ")
    with pytest.raises(ValueError, match="Prior failures"):
        ReviewWorkload(prior_failures=-1)


@pytest.mark.parametrize(
    "workload",
    [
        ReviewWorkload(complexity="simple"),
        ReviewWorkload(complexity="simple", coverage_complete=True),
        ReviewWorkload(
            complexity="unknown", coverage_complete=True, direct_evidence_reference="study"
        ),
        ReviewWorkload(
            complexity="complex", coverage_complete=True, direct_evidence_reference="study"
        ),
        ReviewWorkload(
            complexity="simple",
            coverage_complete=True,
            prior_failures=1,
            direct_evidence_reference="study",
        ),
        ReviewWorkload(complexity="simple", coverage_complete=True, direct_evidence_reference="  "),
    ],
)
def test_direct_requires_complete_workload_evidence_without_failures(profile, catalog, workload):
    assert select_review_plan(profile, catalog, workload).mode is ReviewMode.DELIBERATIVE


def test_direct_evidence_is_explicit_and_explained(profile, catalog):
    workload = ReviewWorkload(
        complexity="simple", coverage_complete=True, direct_evidence_reference="heldout/example"
    )
    plan = select_review_plan(profile, catalog, workload)
    assert plan.mode is ReviewMode.DIRECT
    assert plan.candidate.backend.model == "qwen3:14b"
    assert "heldout/example" in plan.reasons[-1]


def test_manual_model_and_mode_overrides_are_hard_constraints(profile, catalog):
    profile = replace(profile, user_model_override="gpt-oss:20b")
    plan = select_review_plan(profile, catalog, ReviewWorkload(), primary_model="gpt-oss:20b")
    assert plan.candidate.backend.model == "gpt-oss:20b"
    assert any("not independent" in reason for reason in plan.reasons)
    with pytest.raises(ValueError, match="No model candidate"):
        select_review_plan(profile, catalog, ReviewWorkload(), mode_override=ReviewMode.DIRECT)
    profile = replace(profile, user_model_override="qwen3:14b")
    assert (
        select_review_plan(profile, catalog, ReviewWorkload(), mode_override=ReviewMode.DIRECT).mode
        is ReviewMode.DIRECT
    )


def test_missing_metadata_does_not_invent_support_and_default_is_an_explicit_bypass(
    profile, catalog
):
    legacy = tuple(replace(entry, metadata={}) for entry in catalog)
    with pytest.raises(ValueError, match="declares support"):
        select_review_plan(profile, legacy, ReviewWorkload())
    plan = select_review_plan(profile, legacy, ReviewWorkload(), mode_override=ReviewMode.DEFAULT)
    assert plan.candidate.backend.model == "deepseek-coder-v2:16b"
    assert plan.mode is ReviewMode.DEFAULT


def test_capability_metadata_never_bypasses_cost_privacy_or_required_tools(profile, catalog):
    qwen = next(entry for entry in catalog if entry.backend.model == "qwen3:14b")
    route = replace(qwen.backend.route, location=BackendLocation.EXTERNAL)
    with pytest.raises(ValueError, match="local-only"):
        select_review_plan(
            profile, (replace(qwen, backend=replace(qwen.backend, route=route)),), ReviewWorkload()
        )
    route = replace(qwen.backend.route, cost_policy_tier=CostPolicyTier.BILLING_ALLOWED)
    with pytest.raises(ValueError, match="cost policy"):
        select_review_plan(
            profile, (replace(qwen, backend=replace(qwen.backend, route=route)),), ReviewWorkload()
        )
    backend = replace(qwen.backend, capabilities=replace(qwen.backend.capabilities, tools=False))
    profile = replace(profile, required_capabilities=frozenset({TaskCapability.TOOLS}))
    with pytest.raises(ValueError, match="required capability"):
        select_review_plan(profile, (replace(qwen, backend=backend),), ReviewWorkload())


@pytest.mark.parametrize("value", [1200, 2047, 8193, True, 4096.5])
def test_invalid_generation_settings(value):
    with pytest.raises(ValueError):
        ReviewSettings(max_output_tokens=value)


@pytest.mark.parametrize("value", [0, -1, 301, True, float("nan"), float("inf")])
def test_invalid_timeout_settings(value):
    with pytest.raises(ValueError):
        ReviewSettings(timeout_seconds=value)


def test_generation_and_timeout_clamp_without_reducing_input():
    allocation = allocate_review(
        ReviewSettings(), context_tokens=8192, input_token_upper_bound=5500, remaining_seconds=17
    )
    assert allocation.max_output_tokens == 2436
    assert allocation.timeout_seconds == 17
    with pytest.raises(ValueError, match="evidence was preserved"):
        allocate_review(
            ReviewSettings(),
            context_tokens=8192,
            input_token_upper_bound=6000,
            remaining_seconds=17,
        )


def test_stronger_retry_requires_headroom_and_remaining_deadline():
    assert (
        allocate_review(
            ReviewSettings(),
            context_tokens=32768,
            input_token_upper_bound=4000,
            remaining_seconds=300,
            prior_output_tokens=4096,
        ).max_output_tokens
        == 8192
    )
    for prior in (8192,):
        with pytest.raises(ValueError, match="stronger truncation"):
            allocate_review(
                ReviewSettings(),
                context_tokens=32768,
                input_token_upper_bound=4000,
                remaining_seconds=5,
                prior_output_tokens=prior,
            )
    with pytest.raises(ValueError, match="stronger truncation"):
        allocate_review(
            ReviewSettings(),
            context_tokens=8192,
            input_token_upper_bound=5000,
            remaining_seconds=5,
            prior_output_tokens=2936,
        )
    for remaining in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="review time"):
            allocate_review(
                ReviewSettings(),
                context_tokens=32768,
                input_token_upper_bound=1000,
                remaining_seconds=remaining,
            )


def test_research_reserve_is_opt_in_and_has_approved_cap():
    assert research_review_reserve_seconds(6600, enabled=True) == 300
    assert research_review_reserve_seconds(600, enabled=True) == 60
    assert research_review_reserve_seconds(6600, enabled=False) == 120


@pytest.mark.parametrize("value", [True, 1.5, float("nan"), float("inf")])
def test_failure_count_requires_an_integer(value):
    with pytest.raises(ValueError, match="Prior failures"):
        ReviewWorkload(prior_failures=value)


@pytest.mark.parametrize("value", [True, 4096.5, "4096", 0, 8193])
def test_retry_never_produces_a_fractional_or_invalid_output_allowance(value):
    with pytest.raises(ValueError, match="prior review output"):
        allocate_review(
            ReviewSettings(),
            context_tokens=32768,
            input_token_upper_bound=4000,
            remaining_seconds=300,
            prior_output_tokens=value,
        )
