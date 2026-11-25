"""Emergency handoffs cannot reuse implementation tools or client session options."""

import argparse
from types import SimpleNamespace

import pytest
from ai_agent import repo_coding_assistant as cli
from ai_orchestrator import (
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    ExecutionTarget,
    PrivacyClass,
)
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.external_agents import ExternalAgentResult


def target(method=AccessMethod.COPILOT_CLI):
    return ExecutionTarget(
        route_id="preservation",
        provider="ollama" if method is AccessMethod.LOCAL_RUNTIME else "openai",
        product="test",
        model="test-model",
        access_method=method,
        auth_method=AuthMethod.CHATGPT_SIGN_IN,
        billing_source=BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        timeout_seconds=30,
    )


def args():
    return argparse.Namespace(
        approval_policy="trusted_local",
        shared_tools="coding",
        codex_persist_session=True,
        codex_resume="previous-task",
        codex_output_last_message="report.txt",
        codex_output_schema="schema.json",
        codex_search=True,
        codex_image=["private.png"],
        codex_mcp_tools=True,
        shared_task_id="owner-task",
        system="IMPLEMENT ORIGINAL TASK",
        prompt="PRIVATE ORIGINAL OBJECTIVE",
        fallback_session=None,
    )


def test_external_preservation_strips_implementation_options(tmp_path, monkeypatch):
    namespace = args()
    before = vars(namespace).copy()
    captured = {}
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")

    def run(payload, config, **kwargs):
        captured.update(payload=payload, config=config, kwargs=kwargs)
        return ExternalAgentResult((), 0, "handoff report", "")

    monkeypatch.setattr(cli, "_run_external_agent", run)
    monkeypatch.setattr(cli, "_run_native_agent", lambda *a, **k: pytest.fail("agent loop"))
    report = cli._preserve_fallback_work(
        target(), "observed metadata", args=namespace, profile=None, repo_root=tmp_path
    )
    config = captured["config"]
    assert report == "handoff report"
    assert config.sandbox == "read-only"
    assert config.approval_policy == "read_only"
    assert config.shared_tool_profile == "inspection"
    assert not config.resume
    assert not config.codex_mcp_tools and not config.web_search and not config.image_paths
    assert config.output_schema_path is None and config.output_last_message_path is None
    assert config.shared_session_id is None and not config.shared_terminal_approvals
    command = cli._build_external_agent_command(config)
    tools_start = command.index("--available-tools") + 1
    tools_end = command.index("--no-ask-user")
    assert set(command[tools_start:tools_end]) == {
        "repo_shared-read_file",
        "repo_shared-list_dir",
        "repo_shared-find_files",
        "repo_shared-grep_search",
        "repo_shared-git_status",
        "repo_shared-git_diff",
    }
    assert "PRIVATE ORIGINAL OBJECTIVE" not in captured["payload"]
    assert "IMPLEMENT ORIGINAL TASK" not in captured["payload"]
    assert vars(namespace) == before


def test_native_preservation_has_no_tools_or_agent_loop(tmp_path, monkeypatch):
    requests = []

    def complete(request):
        requests.append(request)
        return SimpleNamespace(message=SimpleNamespace(content="metadata report"))

    monkeypatch.setattr(
        cli, "create_chat_client", lambda config: SimpleNamespace(complete=complete)
    )
    monkeypatch.setattr(cli, "_run_native_agent", lambda *a, **k: pytest.fail("agent loop"))
    report = cli._preserve_fallback_work(
        target(AccessMethod.LOCAL_RUNTIME),
        "metadata only",
        args=args(),
        profile=SimpleNamespace(privacy_class=PrivacyClass.SENSITIVE_REVIEW_REQUIRED),
        repo_root=tmp_path,
    )
    assert report == "metadata report"
    assert len(requests) == 1
    assert requests[0].tools == ()
    assert requests[0].privacy_class.value == "sensitive_review_required"
    assert requests[0].messages[-1].content == "metadata only"
    assert requests[0].metadata == {"purpose": "emergency_preservation"}


def test_expired_preservation_never_starts_model(tmp_path, monkeypatch):
    namespace = args()
    namespace.fallback_session = SimpleNamespace(deadline=0)
    monkeypatch.setattr(cli, "_run_external_agent", lambda *a, **k: pytest.fail("external call"))
    monkeypatch.setattr(cli, "create_chat_client", lambda *a, **k: pytest.fail("native call"))
    with pytest.raises(cli.ProviderError, match="deadline expired"):
        cli._preserve_fallback_work(
            target(), "metadata", args=namespace, profile=None, repo_root=tmp_path
        )


@pytest.mark.parametrize("wrapper", ["coding", "external", "native"])
def test_all_execution_wrappers_supply_preservation_callback(tmp_path, monkeypatch, wrapper):
    route = target()
    namespace = args()
    original = (
        ExternalAgentResult((), 1, "", "limit")
        if wrapper == "external"
        else SimpleNamespace(orchestration="original", response="original")
    )
    reports = []
    session = SimpleNamespace(initial=route, current=route, enabled=True, deadline=None)

    def run(prompt, execute, limited, *, observe, preserve):
        assert prompt == "original objective"
        assert preserve(route, "preservation metadata") == "safe handoff"
        return original

    session.run = run
    namespace.fallback_session = session

    def preserve(route, payload, **kwargs):
        reports.append((route, payload, kwargs))
        return "safe handoff"

    monkeypatch.setattr(cli, "_preserve_fallback_work", preserve)
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
        result = cli._run_native_agent_with_fallback(
            "original objective",
            BackendConfig(ProviderKind.OLLAMA, "test"),
            None,
            namespace,
            tmp_path,
        )
    assert result is original
    assert reports[0][1] == "preservation metadata"


def test_external_preservation_failures_are_not_successful_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")
    monkeypatch.setattr(
        cli,
        "_run_external_agent",
        lambda *a, **k: ExternalAgentResult((), 1, "completion claimed", "private error"),
    )
    with pytest.raises(cli.ProviderError, match="preservation client failed"):
        cli._preserve_fallback_work(
            target(), "metadata", args=args(), profile=None, repo_root=tmp_path
        )


def test_codex_preservation_refuses_unverified_native_shell_suppression(tmp_path, monkeypatch):
    route = target(AccessMethod.CODEX_CLI)
    monkeypatch.setattr(cli, "_run_external_agent", lambda *a, **k: pytest.fail("external call"))
    assert not cli._preservation_target_compatible(route, args(), tmp_path)
    with pytest.raises(cli.ProviderError, match="verified native tool suppression"):
        cli._preserve_fallback_work(
            route, "metadata", args=args(), profile=None, repo_root=tmp_path
        )


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        ("usage_limit_reached", cli.ProviderErrorCategory.USAGE_LIMIT),
        (
            "Selected model is at capacity. Please try a different model.",
            cli.ProviderErrorCategory.RETRYABLE,
        ),
    ],
)
def test_preservation_classifies_provider_failures(tmp_path, monkeypatch, failure, category):
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")
    monkeypatch.setattr(
        cli, "_run_external_agent", lambda *a, **k: ExternalAgentResult((), 1, "", failure)
    )
    with pytest.raises(cli.ProviderError) as error:
        cli._preserve_fallback_work(
            target(), "metadata", args=args(), profile=None, repo_root=tmp_path
        )
    assert error.value.category is category
