"""Contracts for private preferences and approved alternate CLI execution."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from ai_orchestrator import AccessMethod, CostPolicyTier, TaskProfile, load_model_catalog
from ai_provider.external_agents import (
    ExternalAgentConfig,
    build_external_agent_command,
    parse_external_agent_jsonl,
    run_external_agent,
)
from ai_provider.user_config import load_user_config


def test_user_config_default_and_private_override(tmp_path: Path) -> None:
    path = tmp_path / "user-config.toml"
    assert load_user_config(path).cost_policy is CostPolicyTier.PREPAID_CREDITS_ALLOWED
    assert TaskProfile().cost_policy_tier is CostPolicyTier.PREPAID_CREDITS_ALLOWED
    path.write_text('[defaults]\ncost_policy = "allowances_allowed"\n', encoding="utf-8")
    assert load_user_config(path).cost_policy is CostPolicyTier.ALLOWANCES_ALLOWED


@pytest.mark.parametrize(
    "content",
    [
        '[defaults]\ncost_policy = "ALLOWANCES_ALLOWED"',
        '[defaults]\ncost_polciy = "allowances_allowed"',
        '[defualts]\ncost_policy = "allowances_allowed"',
        'defaults = "allowances_allowed"',
    ],
)
def test_user_config_rejects_invalid_preferences(tmp_path: Path, content: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_user_config(path)


def test_explicit_user_config_must_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_user_config(tmp_path / "missing.toml", required=True)


@pytest.mark.parametrize(
    "method, flag",
    [
        (AccessMethod.ANTIGRAVITY_CLI, "--dangerously-skip-permissions"),
        (AccessMethod.COPILOT_CLI, "--allow-all"),
        (AccessMethod.KIRO_CLI, "--trust-all-tools"),
    ],
)
def test_alternate_agents_transport_prompt_and_map_trusted_local(
    tmp_path: Path,
    method: AccessMethod,
    flag: str,
) -> None:
    config = ExternalAgentConfig(
        access_method=method,
        command="client",
        model="auto",
        cwd=tmp_path,
        timeout_seconds=10,
        approval_policy="trusted_local",
        sandbox="danger-full-access",
    )
    prompt = "Explain $HOME and `literal`\nwithout executing commands."
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    run_external_agent(prompt, config, runner=runner)
    command, kwargs = calls[0]
    assert flag in command
    assert kwargs["cwd"] == tmp_path
    if method is AccessMethod.ANTIGRAVITY_CLI:
        assert json.loads(kwargs["input"]) == {"event": "user", "message": {"content": prompt}}
    elif method is AccessMethod.COPILOT_CLI:
        assert command[command.index("-p") + 1] == prompt
        assert prompt not in build_external_agent_command(config)
        assert kwargs["input"] == ""
    else:
        assert kwargs["input"] == prompt
    for policy in ("interactive", "read_only", "workspace_auto", "never"):
        with pytest.raises(NotImplementedError, match="only trusted_local"):
            build_external_agent_command(replace(config, approval_policy=policy))
    with pytest.raises(NotImplementedError, match="Codex-specific"):
        build_external_agent_command(replace(config, web_search=True))


def test_antigravity_terminal_result_and_failure_are_normalized() -> None:
    events = parse_external_agent_jsonl(
        json.dumps(
            {
                "event": "result",
                "result": {
                    "status": "SUCCESS",
                    "response": "Done",
                    "usage": {"input_tokens": 4},
                },
            }
        )
    )
    assert events.final_answer == "Done"
    assert events.usage == {"input_tokens": 4}
    failure = parse_external_agent_jsonl(
        json.dumps(
            {
                "event": "result",
                "result": {"status": "ERROR", "error": "authentication required"},
            }
        )
    )
    assert failure.failure_reason == "authentication required"


def test_kiro_acp_result_and_credit_usage() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            json.dumps(event)
            for event in [
                {
                    "type": "sessionUpdate",
                    "data": {
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "Hello"},
                        }
                    },
                },
                {
                    "type": "metadata",
                    "data": {"meteringUsage": [{"value": 0.03, "unit": "credit"}]},
                },
                {"type": "runFinished", "data": {"status": "success", "finalText": "Hello world"}},
            ]
        )
    )
    assert events.final_answer == "Hello world"
    assert events.usage == {"metering_usage": [{"value": 0.03, "unit": "credit"}]}
    assert events.failure_reason is None
    failed = parse_external_agent_jsonl(
        json.dumps(
            {
                "type": "runFinished",
                "data": {"status": "interrupted", "stopReason": "cancelled"},
            }
        )
    )
    assert failed.failure_reason == "cancelled"


def test_copilot_assistant_answer_and_premium_usage() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            json.dumps(event)
            for event in [
                {"type": "user.message", "data": {"content": "Private prompt"}},
                {"type": "session.tools_updated", "data": {"model": "auto"}},
                {"type": "assistant.message", "data": {"content": "CONNECTED."}},
                {"type": "result", "exitCode": 0, "usage": {"premiumRequests": 1}},
            ]
        )
    )
    assert events.final_answer == "CONNECTED."
    assert events.usage == {"premiumRequests": 1}
    assert events.tool_events == ()


def test_requesty_catalog_requires_prepaid_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog = load_model_catalog(root / "packages/ai_orchestrator/examples/model_catalog.toml")
    requesty = [
        entry
        for entry in catalog
        if entry.backend.provider == "requesty" and entry.backend.product != "requesty_free"
    ]
    assert requesty
    assert all(
        entry.backend.cost_policy_tier is CostPolicyTier.PREPAID_CREDITS_ALLOWED
        for entry in requesty
    )


def test_cli_cost_policy_precedence(tmp_path: Path, capsys) -> None:
    from ai_provider.repo_coding_assistant import main

    root = Path(__file__).resolve().parents[1]
    config = tmp_path / "preferences.toml"
    config.write_text('[defaults]\ncost_policy = "allowances_allowed"\n', encoding="utf-8")
    args = [
        "--mode",
        "plan",
        "Explain the provider boundary.",
        "--repo-root",
        str(tmp_path),
        "--catalog",
        str(root / "packages/ai_orchestrator/examples/model_catalog.toml"),
        "--privacy",
        "external_allowed",
        "--route-id",
        "requesty-openai-gpt-5-mini",
        "--skip-prompt-review",
    ]
    assert main(args + ["--user-config", str(config)]) == 0
    assert "route_id: requesty-openai-gpt-5-mini" not in capsys.readouterr().out
    assert (
        main(args + ["--user-config", str(config), "--cost-policy", "prepaid_credits_allowed"]) == 0
    )
    assert "route_id: requesty-openai-gpt-5-mini" in capsys.readouterr().out
    assert main(args) == 0
    assert "route_id: requesty-openai-gpt-5-mini" in capsys.readouterr().out
