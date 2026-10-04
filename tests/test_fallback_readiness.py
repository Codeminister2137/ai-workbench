"""Offline readiness must not authenticate, execute clients or claim live capacity."""

import json

import pytest
from ai_provider import repo_coding_assistant as cli
from ai_provider.repo_assistant_args import build_argument_parser


def offline_args(tmp_path, *flags):
    return [
        "--fallback-readiness",
        "--repo-root",
        str(tmp_path),
        "--privacy",
        "public_or_low_risk",
        "--cost-policy",
        "allowances_allowed",
        "--route-id",
        "openai-codex-gpt-5-5",
        *flags,
    ]


def test_offline_report_preserves_approval_exclusions_without_side_effects(
    monkeypatch, tmp_path, capsys
):
    def forbidden(*args, **kwargs):
        pytest.fail("offline diagnostics attempted a runtime, account or context probe")

    monkeypatch.setattr(cli, "get_local_provider_capability_snapshot", forbidden)
    monkeypatch.setattr(cli, "load_prompt_context", forbidden)
    monkeypatch.setattr(cli, "is_ollama_server_available", forbidden)
    monkeypatch.setattr(cli, "_run_external_agent", forbidden)
    monkeypatch.setattr("ai_provider.execution_fallback.check_agent_readiness", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")
    monkeypatch.setenv("KIRO_COMMAND", "kiro-test")
    monkeypatch.setenv("ANTIGRAVITY_COMMAND", "agy-test")
    assert cli.main(offline_args(tmp_path)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "offline"
    assert report["authentication"] == "not_checked"
    assert report["allowance"] == "unknown"
    candidates = report["fallback_candidates"]
    assert candidates
    assert all(not row["executor_compatible"] for row in candidates)
    assert all("trusted_local" in row["reason"] for row in candidates)
    assert all(not row["execution_ready"] for row in candidates)
    assert list(tmp_path.iterdir()) == []


def test_compatible_offline_routes_do_not_claim_authenticated_or_connected(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")
    assert (
        cli.main(
            offline_args(
                tmp_path,
                "--approval-policy",
                "trusted_local",
                "--fallback-quality-policy",
                "task_minimum",
            )
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    copilot = next(row for row in report["fallback_candidates"] if "copilot" in row["route_id"])
    assert copilot["executor_compatible"]
    assert copilot["authentication"] == "not_checked"
    assert copilot["tool_connection"] == "not_checked"
    assert not copilot["execution_ready"]
    assert any(row["reason"] == "different cost tier" for row in report["policy_exclusions"])


@pytest.mark.parametrize(
    "action", ["--execute", "--start-ollama", "--codex-login", "--codex-mcp-setup"]
)
def test_offline_report_rejects_execution_and_setup(tmp_path, action):
    with pytest.raises(SystemExit) as caught:
        cli.main(offline_args(tmp_path, action))
    assert caught.value.code == 2


def test_provider_option_exclusion_is_precise_and_does_not_probe(tmp_path):
    from ai_orchestrator import TaskProfile, load_model_catalog, prepare_execution

    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    plan = prepare_execution("Explain", TaskProfile(), catalog, review_prompt=False).execution_plan
    assert plan is not None
    args = build_argument_parser().parse_args(["--codex-search"])
    reason = cli._fallback_target_incompatibility(plan.target, args, tmp_path, probe_provider=False)
    assert reason == "provider executor cannot preserve requested options: --codex-search"
