"""Automatic fallback preserves financial/permission boundaries and partial work."""

import argparse
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

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
from ai_orchestrator.fallback import fallback_candidates
from ai_provider.agent_readiness import AgentReadiness, _copilot_authenticated
from ai_provider.errors import ProviderError, ProviderErrorCategory
from ai_provider.execution_fallback import FallbackSession, external_usage_limit
from ai_provider.external_agents import ExternalAgentResult, parse_external_agent_jsonl
from ai_provider.user_config import load_user_config


def test_overload_is_availability_not_allowance_and_ignores_successful_output():
    from ai_provider.execution_fallback import external_model_overload

    result = ExternalAgentResult(
        ("client",), 1, "", "Selected model is at capacity. Please try a different model."
    )
    assert external_model_overload(result)
    assert not external_usage_limit(result)
    assert not external_model_overload(replace(result, returncode=0))
    assert not external_model_overload(
        replace(result, stdout=result.stderr, stderr="unrelated error")
    )


def entry(
    route,
    method,
    billing,
    quality=QualityThreshold.STANDARD,
    tier=CostPolicyTier.ALLOWANCES_ALLOWED,
):
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


@pytest.fixture
def routes():
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


def initial(catalog):
    plan = prepare_execution("Fix source", profile(), catalog, review_prompt=False).execution_plan
    assert plan is not None
    return plan.target


def session(monkeypatch, routes, **kwargs):
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "authenticated"),
    )
    return FallbackSession(
        profile(), routes, initial(routes), compatible=lambda target: True, **kwargs
    )


def test_default_preserves_original_quality_and_explicit_task_minimum_allows_downgrade(routes):
    from ai_orchestrator.fallback import FallbackQualityPolicy

    weaker = replace(routes[1], quality=QualityThreshold.STANDARD)
    catalog = (routes[0], weaker, routes[2])
    assert [
        row.backend.route_id for row in fallback_candidates(profile(), catalog, initial(routes))
    ] == ["kiro"]
    candidates = fallback_candidates(
        profile(), catalog, initial(routes), quality_policy=FallbackQualityPolicy.TASK_MINIMUM
    )
    assert [row.backend.route_id for row in candidates] == ["kiro", "copilot"]


def test_overload_can_switch_same_bucket_without_exhausting_account(monkeypatch, routes):
    sibling = replace(
        routes[1],
        backend=replace(
            routes[1].backend,
            route=replace(routes[1].backend.route, billing_source=routes[0].backend.billing_source),
        ),
    )
    run = session(monkeypatch, (routes[0], sibling))
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        if target.route_id == "codex":
            return ExternalAgentResult((), 1, "", "server_overloaded")
        assert "Inspect current files" in prompt
        return "done"

    assert (
        run.run(
            "Continue work",
            execute,
            lambda value: isinstance(value, ExternalAgentResult) and external_usage_limit(value),
            observe=str,
        )
        == "done"
    )
    assert calls == ["codex", "copilot"]
    assert run.overloaded == {"codex"} and not run.exhausted


def test_native_overload_is_bounded_and_weaker_route_only_gets_handoff(
    monkeypatch, routes, tmp_path
):
    weaker = replace(routes[1], quality=QualityThreshold.STANDARD)
    saved = []
    path = tmp_path / "work.txt"
    path.write_text("partial work")
    run = session(monkeypatch, (routes[0], weaker), save_handoff=saved.append)
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        raise ProviderError("server_overloaded", category=ProviderErrorCategory.RETRYABLE)

    with pytest.raises(ProviderError, match="server_overloaded"):
        run.run("Continue", execute, lambda result: False, observe=str)
    assert calls == ["codex"] and path.read_text() == "partial work"
    assert saved[0]["status"] == "continuation_stopped"
    assert saved[0]["failure_kind"] == "model_overload"
    assert not run.exhausted


def test_every_overloaded_route_is_tried_once(monkeypatch, routes):
    run = session(monkeypatch, routes)
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        return ExternalAgentResult((), 1, "", "server_overloaded")

    run.run("Continue", execute, external_usage_limit, observe=str)
    assert calls == ["codex", "copilot", "kiro"]
    assert run.handoff is not None and not run.exhausted


def test_expired_deadline_refuses_initial_and_later_stage(monkeypatch, routes):
    clock = [1.0]
    monkeypatch.setattr("ai_provider.execution_fallback.time.perf_counter", lambda: clock[0])
    run = session(monkeypatch, routes, deadline=10.0)
    calls = []

    def execute(target, prompt):
        calls.append(target.timeout_seconds)
        return "done"

    assert run.run("First stage", execute, lambda result: False, observe=str) == "done"
    assert calls == [9.0]
    clock[0] = 11.0
    with pytest.raises(ProviderError, match="deadline expired") as error:
        run.run("Later stage", execute, lambda result: False, observe=str)
    assert error.value.category is ProviderErrorCategory.TIMEOUT
    assert calls == [9.0]
    fresh = session(monkeypatch, routes, deadline=10.0)
    with pytest.raises(ProviderError, match="no execution attempted"):
        fresh.run("Expired first stage", execute, lambda result: False, observe=str)
    assert calls == [9.0]


def test_deadline_after_partial_effect_preserves_handoff_without_fallback(
    monkeypatch, routes, tmp_path
):
    clock = [1.0]
    saved = []
    monkeypatch.setattr("ai_provider.execution_fallback.time.perf_counter", lambda: clock[0])
    run = session(monkeypatch, routes, deadline=10.0, save_handoff=saved.append)
    path = tmp_path / "effect.txt"
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        path.write_text("partial effect")
        clock[0] = 11.0
        return ExternalAgentResult((), 1, "", "usage_limit_reached")

    run.run("Continue", execute, external_usage_limit, observe=str)
    assert calls == ["codex"] and path.read_text() == "partial effect"
    assert saved[0]["status"] == "continuation_stopped"
    assert "Inspect saved edits/receipts" in saved[0]["next_action"]


def test_quality_config_is_validated_and_missing_model_evidence_refuses(routes, tmp_path):
    from ai_orchestrator.fallback import FallbackQualityPolicy

    assert (
        load_user_config(tmp_path / "missing").fallback_quality_policy
        is FallbackQualityPolicy.PRESERVE_QUALITY
    )
    config = tmp_path / "user-config.toml"
    config.write_text('[fallback]\nquality_policy = "task_minimum"\n')
    assert load_user_config(config).fallback_quality_policy is FallbackQualityPolicy.TASK_MINIMUM
    config.write_text('[fallback]\nquality_policy = "anything"\n')
    with pytest.raises(ValueError):
        load_user_config(config)
    assert (
        fallback_candidates(profile(), routes, replace(initial(routes), model="ungraded-model"))
        == ()
    )


def test_saved_fallback_handoff_preserves_work_and_omits_prompt(tmp_path):
    from ai_provider.repo_coding_assistant import _save_fallback_handoff

    source = tmp_path / "source.txt"
    source.write_text("partial effect")
    summary = {"status": "continuation_stopped", "next_action": "Inspect current files"}
    _save_fallback_handoff(tmp_path, summary)
    saved = list((tmp_path / "artifacts/fallback-handoffs").glob("*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text()) == summary
    assert source.read_text() == "partial effect"


def test_fallback_filters_tier_privacy_tools_and_exhausted_bucket(routes):
    paid = replace(
        routes[1],
        backend=replace(
            routes[1].backend,
            route=replace(
                routes[1].backend.route, cost_policy_tier=CostPolicyTier.PREPAID_CREDITS_ALLOWED
            ),
        ),
    )
    no_tools = replace(
        routes[2], backend=replace(routes[2].backend, capabilities=ModelCapabilities(tools=False))
    )
    assert fallback_candidates(profile(), (routes[0], paid, no_tools), initial(routes)) == ()
    assert (
        fallback_candidates(
            replace(profile(), privacy_class=PrivacyClass.LOCAL_ONLY), routes, initial(routes)
        )
        == ()
    )
    assert (
        fallback_candidates(
            profile(),
            routes,
            initial(routes),
            exhausted_billing_sources=frozenset(
                {routes[1].backend.billing_source.value, routes[2].backend.billing_source.value}
            ),
        )
        == ()
    )


def test_quota_continuation_retains_partial_file_edit_and_observed_context(
    monkeypatch, routes, tmp_path
):
    run = session(monkeypatch, routes)
    path = tmp_path / "source.txt"
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        if target.route_id == "codex":
            path.write_text("partial edit")
            raise ProviderError("usage limit", category=ProviderErrorCategory.USAGE_LIMIT)
        assert path.read_text() == "partial edit"
        assert "Route-failure continuation" in prompt
        assert "Fix source" in prompt
        assert "codex" in prompt
        path.write_text("completed edit")
        return "done"

    assert run.run("Fix source", execute, lambda result: False, observe=str) == "done"
    assert path.read_text() == "completed edit"
    assert calls == ["codex", "copilot"]
    # Repair/next stage continues with the route already selected, never retries Codex.
    assert (
        run.run(
            "Validate", lambda target, prompt: target.route_id, lambda result: False, observe=str
        )
        == "copilot"
    )


def test_exhaustion_is_bounded_and_informs_user(monkeypatch, routes):
    messages = []
    run = session(monkeypatch, routes, progress=messages.append)
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        raise ProviderError("quota", category=ProviderErrorCategory.RATE_LIMIT)

    with pytest.raises(ProviderError):
        run.run("task", execute, lambda result: False, observe=str)
    assert calls == ["codex", "copilot", "kiro"]
    assert any("fallback_exhausted" in message for message in messages)
    with pytest.raises(ProviderError, match="no further execution"):
        run.run("Repair", execute, lambda result: False, observe=str)
    assert calls == ["codex", "copilot", "kiro"]


@pytest.mark.parametrize(
    "category",
    [
        ProviderErrorCategory.AUTHENTICATION,
        ProviderErrorCategory.TIMEOUT,
        ProviderErrorCategory.NON_RETRYABLE,
    ],
)
def test_other_errors_do_not_switch(monkeypatch, routes, category):
    run = session(monkeypatch, routes)
    calls = []

    def execute(target, prompt):
        calls.append(target.route_id)
        raise ProviderError("not quota", category=category)

    with pytest.raises(ProviderError):
        run.run("task", execute, lambda result: False, observe=str)
    assert calls == ["codex"]


def test_noninteractive_missing_auth_is_reported_before_execution(monkeypatch, routes):
    messages = []
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(False, "missing", ("client", "login")),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO())
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("mid-run prompt"))
    run = FallbackSession(
        profile(), routes, initial(routes), compatible=lambda target: True, progress=messages.append
    )
    assert not run.ready
    assert any("fallback_sign_in_needed" in message for message in messages)


def test_interactive_sign_in_happens_before_execution(monkeypatch, routes):
    checked = {}
    order = []

    def readiness(method):
        signed_in = checked.get(method, False)
        checked[method] = True
        return AgentReadiness(signed_in, "auth", ("client", "login"))

    monkeypatch.setattr("ai_provider.execution_fallback.check_agent_readiness", readiness)
    monkeypatch.setattr("sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    monkeypatch.setattr(
        "ai_provider.execution_fallback.subprocess.run", lambda *a, **k: order.append("login")
    )
    run = FallbackSession(profile(), routes, initial(routes), compatible=lambda target: True)
    assert len(run.ready) == 2
    run.run("task", lambda *args: order.append("execute"), lambda result: False, observe=str)
    assert order == ["login", "login", "login", "execute"]


def test_unsupported_permissions_do_not_prompt_for_auth(monkeypatch, routes):
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "primary auth")
        if method is AccessMethod.CODEX_CLI
        else pytest.fail("ineligible candidate auth"),
    )
    run = FallbackSession(profile(), routes, initial(routes), compatible=lambda target: False)
    assert not run.ready


def test_disabled_fallback_has_no_preflight(monkeypatch, routes, tmp_path):
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: pytest.fail("disabled auth"),
    )
    run = FallbackSession(
        profile(), routes, initial(routes), compatible=lambda target: True, enabled=False
    )
    assert run.run("task", lambda *args: "limited", lambda result: True, observe=str) == "limited"
    config = tmp_path / "user-config.toml"
    config.write_text("[fallback]\nenabled = false\n")
    assert not load_user_config(config).fallback_enabled
    assert load_user_config(tmp_path / "missing").fallback_enabled


def test_incompatibility_explanation_never_authorizes_or_authenticates_route(monkeypatch, routes):
    checked = []
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: checked.append(method) or AgentReadiness(True, "authenticated"),
    )
    run = FallbackSession(
        profile(),
        routes,
        initial(routes),
        compatible=lambda target: False,
        incompatibility_reason=lambda target: "interactive approvals are not mapped",
    )
    assert run.ready == {}
    assert checked == [AccessMethod.CODEX_CLI]
    assert set(run.unavailable.values()) == {"interactive approvals are not mapped"}


@pytest.mark.parametrize("tier", tuple(CostPolicyTier))
def test_fallback_policy_enforces_same_tier_for_every_cost_ceiling(tier):
    # Synthetic route metadata isolates the tier/bucket policy from client entitlement.
    primary_entry = entry(
        "first", AccessMethod.PROVIDER_API, BillingSource.OPENAI_API_BILLING, tier=tier
    )
    alternative = entry(
        "second", AccessMethod.PROVIDER_API, BillingSource.REQUESTY_BILLING, tier=tier
    )
    same_bucket = replace(
        alternative,
        backend=replace(
            alternative.backend,
            route=replace(
                alternative.backend.route, billing_source=BillingSource.OPENAI_API_BILLING
            ),
        ),
    )
    task = TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=tier,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        user_route_id_override="first",
    )
    plan = prepare_execution("Inspect", task, (primary_entry,), review_prompt=False).execution_plan
    assert plan is not None
    assert fallback_candidates(task, (primary_entry, alternative), plan.target) == (alternative,)
    assert fallback_candidates(task, (primary_entry, same_bucket), plan.target) == ()
    for other_tier in CostPolicyTier:
        if other_tier is tier:
            continue
        other = replace(
            alternative,
            backend=replace(
                alternative.backend,
                route=replace(alternative.backend.route, cost_policy_tier=other_tier),
            ),
        )
        assert fallback_candidates(task, (primary_entry, other), plan.target) == ()


def test_quota_words_in_success_or_tool_output_do_not_trigger_switch():
    result = ExternalAgentResult((), 0, "Explain usage limit", "usage limit")
    assert not external_usage_limit(result)
    events = parse_external_agent_jsonl(
        json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "usage limit"}}
        )
    )
    assert not external_usage_limit(
        replace(result, returncode=1, stderr="permission denied", events=events)
    )
    assert external_usage_limit(replace(result, returncode=1, stderr="You've hit your usage limit"))


def test_copilot_auth_rpc_creates_no_model_session_and_closes_process(monkeypatch):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"isAuthenticated": True}}).encode()
    process = SimpleNamespace(
        stdin=io.BytesIO(),
        stdout=io.BytesIO(f"Content-Length: {len(body)}\r\n\r\n".encode() + body),
        poll=lambda: None,
        kill=lambda: None,
        wait=lambda **kwargs: None,
    )
    calls = []
    monkeypatch.setattr(
        "ai_provider.agent_readiness.subprocess.Popen",
        lambda command, **kwargs: calls.append(command) or process,
    )
    assert _copilot_authenticated("copilot", 1)
    assert "--stdio" in calls[0]
    assert process.stdin.closed and process.stdout.closed


def test_cli_continues_codex_partial_edit_via_copilot(monkeypatch, tmp_path, capsys):
    from ai_provider import repo_coding_assistant as cli

    catalog = tmp_path / "catalog.toml"
    catalog.write_text("""[[models]]
route_id = "codex"
provider = "openai"
product = "codex"
model = "test"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "high"
[models.capabilities]
chat = true
tools = true
[[models]]
route_id = "copilot"
provider = "github"
product = "github_copilot"
model = "auto"
location = "external"
access_method = "copilot_cli"
auth_method = "github_account_sign_in"
billing_source = "github_copilot_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "standard"
[models.capabilities]
chat = true
tools = true
""")
    config = tmp_path / "user-config.toml"
    config.write_text('[fallback]\nquality_policy = "task_minimum"\n')
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")
    order = []

    def readiness(method):
        order.append("auth")
        return AgentReadiness(True, "auth")

    monkeypatch.setattr("ai_provider.execution_fallback.check_agent_readiness", readiness)
    source = tmp_path / "source.py"
    source.write_text("value = 0\n")
    original_test = "assert value == 2\n"
    test = tmp_path / "test_source.txt"
    test.write_text(original_test)

    def execute(prompt, config, **kwargs):
        order.append(config.access_method.value)
        if config.access_method is AccessMethod.CODEX_CLI:
            source.write_text("value = 1\n")
            events = parse_external_agent_jsonl(
                json.dumps({"type": "error", "message": "You've hit your usage limit"})
            )
            return ExternalAgentResult(
                ("codex",), 1, '{"type":"file_change","path":"source.py"}\n', "", events=events
            )
        assert source.read_text() == "value = 1\n"
        assert "Route-failure continuation" in prompt
        assert "source.py" in prompt
        assert config.approval_policy == "trusted_local"
        source.write_text("value = 2\n")
        return ExternalAgentResult(("copilot",), 0, "Completed", "")

    monkeypatch.setattr(cli, "_run_external_agent", execute)
    assert (
        cli.main(
            [
                "--mode",
                "implement",
                "Set value to 2 in source.py.",
                "--repo-root",
                str(tmp_path),
                "--catalog",
                str(catalog),
                "--route-id",
                "codex",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "allowances_allowed",
                "--approval-policy",
                "trusted_local",
                "--skip-prompt-review",
                "--execute",
            ]
        )
        == 0
    )
    assert order == ["auth", "auth", "codex_cli", "copilot_cli"]
    namespace = {}
    exec(source.read_text(), namespace)
    exec(test.read_text(), namespace)
    assert test.read_text() == original_test
    output = capsys.readouterr().out
    assert "fallback_switch: codex -> copilot" in output
    assert "effective_route_id: copilot" in output


def test_native_loop_preserves_tool_history_on_provider_limit(tmp_path):
    from ai_agent import (
        AgentLoop,
        PermissionManager,
        PermissionPolicy,
        ToolContext,
        default_coding_tools,
    )
    from ai_provider import (
        AIMessage,
        AIResponse,
        AIToolCall,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as Location,
    )

    class Client:
        calls = 0
        backend = BackendInfo(provider="fake", model="test", location=Location.LOCAL)

        def stream(self, request):
            raise NotImplementedError

        def complete(self, request):
            self.calls += 1
            if self.calls > 1:
                raise ProviderError("quota", category=ProviderErrorCategory.USAGE_LIMIT)
            return AIResponse(
                message=AIMessage(
                    MessageRole.ASSISTANT,
                    "",
                    tool_calls=(
                        AIToolCall(
                            "call-1", "create_file", {"path": "out.txt", "content": "partial"}
                        ),
                    ),
                ),
                backend=BackendInfo(provider="fake", model="test", location=Location.LOCAL),
            )

    with pytest.raises(ProviderError) as error:
        AgentLoop(
            Client(),
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        ).run("Write output")
    assert (tmp_path / "out.txt").read_text() == "partial"
    assert error.value.partial_messages[-1].role is MessageRole.TOOL
    assert error.value.partial_messages[-2].tool_calls[0].name == "create_file"


def test_handoff_omits_raw_external_tool_payload():
    from ai_provider.repo_coding_assistant import _fallback_observed

    result = ExternalAgentResult((), 1, "PRIVATE_TOOL_PAYLOAD", "PRIVATE_TOOL_PAYLOAD")
    assert "PRIVATE_TOOL_PAYLOAD" not in _fallback_observed(result)


@pytest.mark.parametrize("native", [False, True])
def test_provider_coding_wrappers_continue_on_normalized_limit(monkeypatch, routes, native):
    from ai_agent.loop import AgentResult
    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as Location,
    )
    from ai_provider import repo_coding_assistant as cli

    catalog = tuple(
        replace(
            row,
            backend=replace(
                row.backend,
                route=replace(
                    row.backend.route,
                    provider=provider,
                    access_method=AccessMethod.PROVIDER_API,
                    auth_method=AuthMethod.API_KEY,
                    cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
                    billing_source=billing,
                ),
            ),
        )
        for row, provider, billing in (
            (routes[0], "openai", BillingSource.OPENAI_API_BILLING),
            (routes[1], "google", BillingSource.GOOGLE_API_BILLING),
        )
    )
    task = replace(profile(), cost_policy_tier=CostPolicyTier.BILLING_ALLOWED)
    plan = prepare_execution("Fix", task, catalog, review_prompt=False).execution_plan
    assert plan is not None
    run = FallbackSession(task, catalog, plan.target, compatible=lambda target: True)
    args = argparse.Namespace(fallback_session=run, mode="implement" if native else "ask")
    config = cli.backend_config_from_execution_target(plan.target)
    calls = []

    def complete(config):
        calls.append(config.provider.value)
        if config.provider.value == "openai":
            raise ProviderError("429", category=ProviderErrorCategory.RATE_LIMIT)
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "Done"),
            backend=BackendInfo(provider="google", model="auto", location=Location.EXTERNAL),
        )

    monkeypatch.setattr(
        cli,
        "_run_native_agent",
        lambda prompt, config, *a, **k: AgentResult(response=complete(config)),
    )
    monkeypatch.setattr(cli, "run_coding_prompt", lambda *a, **k: complete(config))
    monkeypatch.setattr(
        cli,
        "create_chat_client",
        lambda config: SimpleNamespace(complete=lambda request: complete(config)),
    )
    if native:
        result = cli._run_native_agent_with_fallback("Fix", config, task, args, Path.cwd())
    else:
        result = cli._run_coding_prompt_with_fallback(
            "Fix", task, catalog, args=args, repo_root=Path.cwd(), execute=True
        )
        assert result.orchestration.recommendation.selected.backend.provider == "google"
    assert result.response.message.content == "Done"
    assert calls == ["openai", "google"]
