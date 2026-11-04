"""W4 reliability pins: session escalation flag and production preservation sanitization."""

import argparse
from types import SimpleNamespace

import pytest
from ai_agent import repo_coding_assistant as cli
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
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.execution_fallback import FallbackSession, external_usage_limit
from ai_provider.external_agents import (
    ExternalAgentEventSummary,
    ExternalAgentResult,
)


def _w4_entry(route, method, billing, quality, tier):
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
                cost_policy_tier=tier,
            ),
            capabilities=ModelCapabilities(chat=True, tools=True),
        ),
        quality=quality,
    )


def _w4_profile():
    return TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        quality_threshold=QualityThreshold.HIGH,
        user_route_id_override="codex",
    )


def _w4_catalog():
    return (
        _w4_entry(
            "codex",
            AccessMethod.CODEX_CLI,
            BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
            QualityThreshold.HIGH,
            CostPolicyTier.ALLOWANCES_ALLOWED,
        ),
        _w4_entry(
            "billed",
            AccessMethod.COPILOT_CLI,
            BillingSource.OPENAI_API_BILLING,
            QualityThreshold.HIGH,
            CostPolicyTier.BILLING_ALLOWED,
        ),
    )


def _sensitive_limited_result():
    events = ExternalAgentEventSummary(
        final_answer="FINAL_ANSWER_SECRET_alpha",
        command_events=({"command": "rm -rf /", "output": "COMMAND_SECRET_beta"},),
        tool_events=(
            {
                "tool": "exec",
                "arguments": "TOOL_ARG_SECRET_gamma",
                "output": "TOOL_OUT_SECRET_delta",
            },
            {
                "tool": "read",
                "arguments": "TOOL_ARG_SECRET_epsilon",
                "output": "TOOL_OUT_SECRET_zeta",
            },
        ),
        web_search_events=(),
        file_change_events=({"path": "/secret", "diff": "FILE_DIFF_SECRET_eta"},),
        usage=None,
        failure_reason="usage_limit_reached",
        parse_errors=(),
    )
    return ExternalAgentResult(
        command=(),
        returncode=1,
        stdout="STDOUT_SECRET_theta",
        stderr="usage_limit_reached\nSTDERR_SECRET_iota",
        last_message="LAST_MESSAGE_SECRET_kappa",
        events=events,
    )


_SECRETS = (
    "FINAL_ANSWER_SECRET_alpha",
    "COMMAND_SECRET_beta",
    "TOOL_ARG_SECRET_gamma",
    "TOOL_OUT_SECRET_delta",
    "TOOL_ARG_SECRET_epsilon",
    "TOOL_OUT_SECRET_zeta",
    "FILE_DIFF_SECRET_eta",
    "STDOUT_SECRET_theta",
    "STDERR_SECRET_iota",
    "LAST_MESSAGE_SECRET_kappa",
)


def test_session_honors_allow_cost_escalation_at_session_scope(monkeypatch):
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "authenticated"),
    )
    catalog = _w4_catalog()
    profile = _w4_profile()
    plan = prepare_execution("Fix source", profile, catalog, review_prompt=False).execution_plan
    assert plan is not None
    initial = plan.target
    assert initial.route_id == "codex"

    blocked = FallbackSession(
        profile,
        catalog,
        initial,
        compatible=lambda target: True,
        priority=("billed",),
        allow_cost_escalation=False,
        progress=lambda message: None,
    )
    assert "billed" not in blocked.ready

    blocked_calls = []

    def execute_blocked(target, prompt):
        blocked_calls.append(target.route_id)
        return ExternalAgentResult((), 1, "", "usage_limit_reached")

    blocked_result = blocked.run(
        "Work",
        execute_blocked,
        lambda value: isinstance(value, ExternalAgentResult) and external_usage_limit(value),
        observe=str,
    )
    assert blocked_calls == ["codex"]
    assert blocked.handoff is not None
    assert isinstance(blocked_result, ExternalAgentResult)

    allowed = FallbackSession(
        profile,
        catalog,
        initial,
        compatible=lambda target: True,
        priority=("billed",),
        allow_cost_escalation=True,
        progress=lambda message: None,
    )
    assert "billed" in allowed.ready

    allowed_calls = []

    def execute_allowed(target, prompt):
        allowed_calls.append(target.route_id)
        if target.route_id == "codex":
            return ExternalAgentResult((), 1, "", "usage_limit_reached")
        return "continued"

    assert (
        allowed.run(
            "Work",
            execute_allowed,
            lambda value: isinstance(value, ExternalAgentResult) and external_usage_limit(value),
            observe=str,
        )
        == "continued"
    )
    assert allowed_calls == ["codex", "billed"]

    unlisted = FallbackSession(
        profile,
        catalog,
        initial,
        compatible=lambda target: True,
        priority=("strong",),
        allow_cost_escalation=True,
        progress=lambda message: None,
    )
    assert "billed" not in unlisted.ready


def test_production_observe_sanitizes_preservation_payload_end_to_end(monkeypatch):
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "authenticated"),
    )
    primary = _w4_entry(
        "codex",
        AccessMethod.CODEX_CLI,
        BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
        QualityThreshold.HIGH,
        CostPolicyTier.ALLOWANCES_ALLOWED,
    )
    weaker = _w4_entry(
        "copilot",
        AccessMethod.COPILOT_CLI,
        BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE,
        QualityThreshold.LOW,
        CostPolicyTier.ALLOWANCES_ALLOWED,
    )
    catalog = (primary, weaker)
    profile = TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        quality_threshold=QualityThreshold.HIGH,
        user_route_id_override="codex",
    )
    plan = prepare_execution("Fix source", profile, catalog, review_prompt=False).execution_plan
    assert plan is not None
    saved = []
    run = FallbackSession(
        profile,
        catalog,
        plan.target,
        compatible=lambda target: True,
        preservation_compatible=lambda target: True,
        save_handoff=lambda receipt: saved.append(dict(receipt)),
        progress=lambda message: None,
    )
    sensitive = _sensitive_limited_result()
    assert external_usage_limit(sensitive)

    observed = cli._fallback_observed(sensitive)
    assert "2 tool events" in observed
    assert "1 file-change events" in observed
    assert "1 command events" in observed
    assert "Raw arguments and outputs are omitted" in observed
    for secret in _SECRETS:
        assert secret not in observed

    payloads = []

    def preserve(target, payload):
        payloads.append(payload)
        return "handoff report"

    result = run.run(
        "PRIVATE ORIGINAL OBJECTIVE",
        lambda *args: sensitive,
        external_usage_limit,
        observe=cli._fallback_observed,
        preserve=preserve,
    )
    assert result is sensitive
    assert len(payloads) == 1
    assert "Do not edit" in payloads[0]
    assert "PRIVATE ORIGINAL OBJECTIVE" not in payloads[0]
    for secret in _SECRETS:
        assert secret not in payloads[0]
    assert "2 tool events" in payloads[0]
    assert run.handoff is not None
    handoff_text = str(run.handoff.get("observed", []))
    for secret in _SECRETS:
        assert secret not in handoff_text
    assert saved
    saved_text = str(saved)
    for secret in _SECRETS:
        assert secret not in saved_text


def _wrapper_args():
    return argparse.Namespace(
        approval_policy="trusted_local",
        shared_tools="coding",
        codex_persist_session=False,
        codex_resume=None,
        codex_output_last_message=None,
        codex_output_schema=None,
        codex_search=False,
        codex_image=[],
        codex_mcp_tools=False,
        shared_task_id="owner-task",
        system="SYSTEM",
        prompt="PROMPT",
        fallback_session=None,
    )


@pytest.mark.parametrize("wrapper", ["coding", "external", "native"])
def test_production_wrappers_supply_sanitizing_observe(tmp_path, monkeypatch, wrapper):
    route = SimpleNamespace(route_id="primary")
    namespace = _wrapper_args()
    captured = {}
    original = (
        ExternalAgentResult((), 1, "", "limit")
        if wrapper == "external"
        else SimpleNamespace(orchestration="original", response="original")
    )

    def run(prompt, execute, limited, *, observe, preserve):
        captured["observe"] = observe
        assert preserve(route, "preservation metadata") == "safe handoff"
        return original

    session = SimpleNamespace(initial=route, current=route, enabled=True, deadline=None)
    session.run = run
    namespace.fallback_session = session
    monkeypatch.setattr(cli, "_preserve_fallback_work", lambda *args, **kwargs: "safe handoff")

    if wrapper == "coding":
        result = cli._run_coding_prompt_with_fallback(
            "original objective", None, (), args=namespace, repo_root=tmp_path, execute=True
        )
    elif wrapper == "external":
        from ai_provider.external_agents import ExternalAgentConfig

        config = ExternalAgentConfig(AccessMethod.CODEX_CLI, "test", "test", tmp_path, 30)
        result = cli._run_external_agent_with_fallback(
            "original objective", config, args=namespace, profile=None, repo_root=tmp_path
        )
    else:
        from ai_provider.config import BackendConfig, ProviderKind

        result = cli._run_native_agent_with_fallback(
            "original objective",
            BackendConfig(ProviderKind.OLLAMA, "test"),
            None,
            namespace,
            tmp_path,
        )
    assert result is original
    assert captured["observe"] is cli._fallback_observed
    sanitized = captured["observe"](_sensitive_limited_result())
    for secret in _SECRETS:
        assert secret not in sanitized
    assert "Raw arguments and outputs are omitted" in sanitized
