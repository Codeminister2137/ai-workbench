"""Scope C single fallback executor: verdict reuse, ledger contract, switching."""

from __future__ import annotations

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
    prepare_execution,
)
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.execution_fallback import external_usage_limit
from ai_provider.external_agents import ExternalAgentResult
from ai_provider.fallback_executor import FallbackExecutor, Readiness


def entry(route, method, billing, quality=QualityThreshold.HIGH):
    return ModelCatalogEntry(
        backend=ModelBackend(
            route=AccessRoute(
                route_id=route,
                provider="test",
                product=route,
                model="auto",
                location=BackendLocation.EXTERNAL,
                access_method=method,
                auth_method=AuthMethod.CHATGPT_SIGN_IN,
                billing_source=billing,
                cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
            ),
            capabilities=ModelCapabilities(chat=True, tools=True),
        ),
        quality=quality,
    )


def catalog():
    return (
        entry(
            "codex",
            AccessMethod.CODEX_CLI,
            BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
            QualityThreshold.HIGH,
        ),
        entry(
            "copilot",
            AccessMethod.COPILOT_CLI,
            BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE,
            QualityThreshold.HIGH,
        ),
        entry(
            "kiro",
            AccessMethod.KIRO_CLI,
            BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE,
            QualityThreshold.HIGH,
        ),
    )


def profile(**changes):
    return TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        user_route_id_override="codex",
        **changes,
    )


def initial(routes):
    plan = prepare_execution("Fix source", profile(), routes, review_prompt=False).execution_plan
    assert plan is not None
    return plan.target


def make_executor(routes, **kwargs):
    kwargs.setdefault("execute", lambda target, prompt: ExternalAgentResult((), 0, "ok", ""))
    kwargs.setdefault("observe", str)
    kwargs.setdefault("is_limited", external_usage_limit)
    kwargs.setdefault("check_ready", lambda target: Readiness(True))
    kwargs.setdefault("progress", lambda message: None)
    return FallbackExecutor(profile(), routes, initial(routes), **kwargs)


def test_finish_first_try_returns_result_with_finished_ledger():
    result = ExternalAgentResult((), 0, "done", "")
    outcome = make_executor(catalog(), execute=lambda target, prompt: result).run("Do it")
    assert outcome.status == "finished"
    assert outcome.route_id == "codex"
    assert outcome.result is result
    assert outcome.attempts == [{"route_id": "codex", "status": "finished"}]


def test_usage_limit_switches_and_retires_billing_bucket():
    seen = []

    def execute(target, prompt):
        seen.append(target.route_id)
        if target.route_id == "codex":
            return ExternalAgentResult((), 1, "", "usage limit reached")
        return ExternalAgentResult((), 0, "done", "")

    run = make_executor(catalog(), execute=execute)
    outcome = run.run("Do it")
    assert outcome.status == "finished"
    assert outcome.route_id != "codex"
    assert outcome.attempts == [
        {"route_id": "codex", "status": "usage_limit"},
        {"route_id": outcome.route_id, "status": "finished"},
    ]
    assert BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE.value in run.exhausted
    assert seen[0] == "codex"


def test_route_failure_retires_route_not_bucket():
    seen = []

    def execute(target, prompt):
        seen.append(target.route_id)
        if target.route_id == "codex":
            return ExternalAgentResult((), 1, "", "")  # silent death: no events, no answer
        return ExternalAgentResult((), 0, "done", "")

    run = make_executor(catalog(), execute=execute)
    outcome = run.run("Do it")
    assert outcome.status == "finished"
    assert outcome.attempts[0] == {"route_id": "codex", "status": "route_failure"}
    assert "codex" in run.failed_routes
    assert BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE.value not in run.exhausted


def test_allowance_observation_skips_without_executing():
    seen = []

    def observe_allowance(target):
        return {
            "status": "available",
            "source": "kiro_isolated_v2_usage",
            "windows": [
                {"bucket_id": "plan_credits", "covered_credits": 100.0, "plan_credits": 100.0}
            ],
        }

    def execute(target, prompt):
        seen.append(target.route_id)
        return ExternalAgentResult((), 0, "done", "")

    run = make_executor(catalog(), execute=execute, observe_allowance=observe_allowance)
    # Every route reports the same exhausted bucket: nothing executes, then raise.
    with pytest.raises(ProviderError) as raised:
        run.run("Do it")
    assert raised.value.category == ProviderErrorCategory.USAGE_LIMIT
    assert seen == []
    assert run.attempts[0]["status"] == "allowance_exhausted"


def test_exhaustion_writes_handoff_and_saves():
    saved = []
    run = make_executor(
        catalog(),
        execute=lambda target, prompt: ExternalAgentResult((), 1, "", "usage limit reached"),
        save_handoff=saved.append,
    )
    # Pure verdict failures (no exception, no allowance skip) return exhausted.
    outcome = run.run("Do it")
    assert outcome.status == "exhausted"
    assert run.handoff is not None
    assert run.handoff["status"] == "continuation_stopped"
    assert saved and saved[0]["status"] == "continuation_stopped"
    ledger = [attempt for attempt in run.attempts]
    assert ledger[0] == {"route_id": "codex", "status": "usage_limit"}
    assert {row["route_id"] for row in ledger} == {"codex", "copilot", "kiro"}
    assert {row["status"] for row in ledger} == {"usage_limit"}


def test_initial_unready_skips_to_first_ready():
    def check_ready(target):
        return Readiness(target.route_id != "codex", "signed out")

    run = make_executor(catalog(), check_ready=check_ready)
    outcome = run.run("Do it")
    assert outcome.status == "finished"
    assert outcome.attempts[0] == {"route_id": "codex", "status": "initial_unready"}
    assert "codex" in run.failed_routes


def test_reorder_seam_changes_order_and_guards_set():
    routes = catalog()
    observed_sets = []

    def reorder(route_ids):
        observed_sets.append(set(route_ids))
        return sorted(route_ids, key=lambda route_id: route_id != "kiro")

    run = make_executor(
        routes,
        execute=lambda target, prompt: ExternalAgentResult(
            (),
            0 if target.route_id == "kiro" else 1,
            "done" if target.route_id == "kiro" else "",
            "" if target.route_id == "kiro" else "usage limit reached",
        ),
        reorder_candidates=reorder,
    )
    outcome = run.run("Do it")
    assert outcome.status == "finished"
    # Initial still runs first; the reorder then jumps the queue to kiro.
    assert [attempt["route_id"] for attempt in run.attempts] == ["codex", "kiro"]
    # The seam sees the remaining candidates (failed codex already excluded).
    assert observed_sets and observed_sets[0] == {"copilot", "kiro"}

    def drop_all(route_ids):
        return []

    def fail_codex(target, prompt):
        if target.route_id == "codex":
            return ExternalAgentResult((), 1, "", "usage limit reached")
        return ExternalAgentResult((), 0, "done", "")

    with pytest.raises(ValueError, match="preserve the candidate set"):
        make_executor(routes, execute=fail_codex, reorder_candidates=drop_all).run("Do it")


def test_genuine_failure_returns_result_without_switching():
    from ai_provider.external_agents import parse_external_agent_jsonl

    events = parse_external_agent_jsonl('{"type": "tool_use", "name": "bash"}\n')
    result = ExternalAgentResult((), 1, "", "weird crash", events=events)
    seen = []

    def execute(target, prompt):
        seen.append(target.route_id)
        return result

    outcome = make_executor(catalog(), execute=execute).run("Do it")
    assert outcome.result is result
    assert outcome.attempts == [{"route_id": "codex", "status": "finished"}]
    assert seen == ["codex"]


def test_disabled_runs_initial_once_without_switching():
    result = ExternalAgentResult((), 1, "", "usage limit reached")
    seen = []

    def execute(target, prompt):
        seen.append(target.route_id)
        return result

    outcome = make_executor(catalog(), execute=execute, enabled=False).run("Do it")
    assert outcome.result is result
    assert seen == ["codex"]
    assert outcome.attempts == [{"route_id": "codex", "status": "finished"}]


def test_expired_deadline_refuses_execution():
    import time

    # An already-past deadline fails preflight at construction (legacy parity).
    with pytest.raises(ProviderError) as raised:
        make_executor(catalog(), deadline=time.perf_counter() - 1.0)
    assert raised.value.category == ProviderErrorCategory.TIMEOUT


def test_emergency_preservation_reports_without_implementing():
    routes = catalog()
    weaker = replace(routes[1], quality=QualityThreshold.LOW)
    saved = []
    payloads = []

    def preserve(target, payload):
        payloads.append(payload)
        assert target.route_id == "copilot"
        return "Partial edits require owner review."

    run = make_executor(
        (routes[0], weaker),
        execute=lambda target, prompt: ExternalAgentResult((), 1, "", "usage limit reached"),
        preservation_compatible=lambda target: True,
        save_handoff=lambda receipt: saved.append(dict(receipt)),
        preserve=preserve,
    )
    outcome = run.run("PRIVATE ORIGINAL OBJECTIVE")
    assert outcome.status == "exhausted"
    assert outcome.handoff is not None
    assert outcome.handoff["preservation_route_id"] == "copilot"
    assert len(payloads) == 1
    assert "Do not edit" in payloads[0]
    assert "PRIVATE ORIGINAL OBJECTIVE" not in payloads[0]
    assert any(attempt.status == "preservation_only" for attempt in run.attempts)
