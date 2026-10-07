"""Offline readiness must not authenticate, execute clients or claim live capacity."""

import json
from pathlib import Path

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


def test_list_skills_reports_offline_discovery_and_prerequisites(monkeypatch, tmp_path, capsys):
    skill = tmp_path / "skills/review-repo-change/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: review-repo-change\ndescription: review\n---\nRead the diff.")
    monkeypatch.setattr("ai_agent.skills.shutil.which", lambda executable: "git")
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("network"))
    assert (
        cli.main(
            [
                "--repo-root",
                str(tmp_path),
                "--skill-dir",
                str(skill.parents[1]),
                "--list-skills",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ready"
    assert report["shared_tool_profile"] == "inspection"
    assert report["execution"].startswith("offline;")
    assert report["skills"] == [
        {
            "name": "review-repo-change",
            "available": True,
            "source": str(skill.relative_to(tmp_path)),
            "required_tools": ["find_files", "git_diff", "git_status", "grep_search", "read_file"],
            "reason": None,
        }
    ]


def test_list_skills_reports_unavailable_prerequisites(tmp_path, capsys, monkeypatch):
    skill = tmp_path / "skills/review-repo-change/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: review-repo-change\ndescription: review\n---\nRead the diff.")
    monkeypatch.setattr("ai_agent.skills.shutil.which", lambda executable: None)
    assert (
        cli.main(
            [
                "--repo-root",
                str(tmp_path),
                "--skill-dir",
                str(skill.parents[1]),
                "--list-skills",
            ]
        )
        == 1
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert "requires an installed Git executable" in report["skills"][0]["reason"]


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
                "--validation-python",
                str(tmp_path / ".venv" / "Scripts" / "python.exe"),
            )
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    copilot = next(row for row in report["fallback_candidates"] if "copilot" in row["route_id"])
    assert copilot["executor_compatible"]
    assert copilot["executable_status"] == "unavailable"
    assert copilot["authentication"] == "not_checked"
    assert copilot["tool_connection"] == "not_checked"
    assert not copilot["execution_ready"]
    assert any(row["reason"] == "different cost tier" for row in report["policy_exclusions"])


def test_readiness_distinguishes_available_executable_from_adapter_support(
    tmp_path, monkeypatch, capsys
):
    client = tmp_path / "copilot-test.exe"
    client.touch()
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", str(client))

    assert (
        cli.main(
            offline_args(
                tmp_path,
                "--approval-policy",
                "trusted_local",
                "--fallback-quality-policy",
                "task_minimum",
                "--validation-python",
                str(tmp_path / ".venv" / "Scripts" / "python.exe"),
            )
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    copilot = next(row for row in report["fallback_candidates"] if "copilot" in row["route_id"])
    assert copilot["executor_compatible"]
    assert copilot["executable_status"] == "available"
    assert copilot["authentication"] == "not_checked"
    assert copilot["tool_connection"] == "not_checked"
    assert copilot["allowance"] == "unknown"
    assert not copilot["execution_ready"]


def test_selected_skill_readiness_includes_implicit_read_only_tool_requirements(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr(
        "ai_provider.external_agents.external_agent_command",
        lambda _method: "mock-client",
    )
    skill_source = (
        Path(__file__).resolve().parents[1]
        / "packages"
        / "ai_agent"
        / "skills"
        / "review-repo-change"
        / "SKILL.md"
    )
    skill_directory = tmp_path / "skills"
    (skill_directory / "review-repo-change").mkdir(parents=True)
    (skill_directory / "review-repo-change" / "SKILL.md").write_text(
        skill_source.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert (
        cli.main(
            offline_args(
                tmp_path,
                "--skill",
                "review-repo-change",
                "--skill-dir",
                str(skill_directory),
                "--approval-policy",
                "interactive",
            )
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["requirements"] == {
        "shared_tool_profile": "inspection",
        "approval_policy": "read_only",
        "selected_skills": ["review-repo-change"],
    }
    candidates = {row["route_id"]: row for row in report["fallback_candidates"]}
    antigravity = candidates.get("google-antigravity-gemini-3-1-pro")
    if antigravity is not None:
        assert not antigravity["executor_compatible"]
        assert "headless mode denies MCP tools" in antigravity["reason"]
        assert "permissions.allow" in antigravity["reason"]


def test_skill_readiness_reports_missing_skill_as_blocked(tmp_path, capsys):
    assert (
        cli.main(
            offline_args(
                tmp_path,
                "--skill",
                "review-repo-change",
                "--skill-dir",
                str(tmp_path / "no-skills-here"),
            )
        )
        == 1
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "blocked"
    assert "needs exactly one source; found 0" in report["reason"]


def test_skill_readiness_rejects_research_tool_profile(tmp_path):
    with pytest.raises(SystemExit) as caught:
        cli.main(
            offline_args(tmp_path, "--skill", "review-repo-change", "--tool-profile", "research")
        )
    assert caught.value.code == 2


def test_readiness_explains_unsupported_codex_feature_on_alternate_shared_routes(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setattr(
        "ai_provider.external_agents.external_agent_command",
        lambda _method: "mock-client",
    )
    assert (
        cli.main(
            offline_args(
                tmp_path,
                "--shared-tools",
                "coding",
                "--approval-policy",
                "workspace_write",
                "--codex-search",
                "--fallback-quality-policy",
                "task_minimum",
            )
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    copilot = next(
        row
        for row in report["fallback_candidates"]
        if row["route_id"] == "github-copilot-cli-default"
    )
    assert not copilot["executor_compatible"]
    assert copilot["reason"] == ("Codex-specific options are not mapped for common inspection")


@pytest.mark.parametrize(
    "option",
    [
        ("--codex-resume", "session-123"),
        ("--codex-persist-session",),
        ("--codex-search",),
        ("--codex-image", "image.png"),
        ("--codex-output-schema", "schema.json"),
        ("--codex-mcp-tools",),
        ("--codex-output-last-message", "last-message.txt"),
    ],
)
@pytest.mark.parametrize("shared_profile", [None, "coding"])
@pytest.mark.parametrize(
    "method,route_id",
    [
        ("copilot_cli", "github-copilot-cli-default"),
        ("kiro_cli", "kiro-cli-default"),
    ],
)
def test_readiness_reports_unsupported_codex_options_on_alternate_routes(
    monkeypatch,
    tmp_path,
    option,
    shared_profile,
    method,
    route_id,
):
    from ai_orchestrator import AccessMethod, load_model_catalog, prepare_execution

    selected_method = AccessMethod(method)
    monkeypatch.setattr(
        "ai_provider.external_agents.external_agent_command",
        lambda access_method: "mock-client" if access_method is selected_method else None,
    )
    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    entry = next(item for item in catalog if item.backend.route_id == route_id)
    profile = cli.coding_task_profile(
        privacy_class=cli.OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        route_id_override=route_id,
        cost_policy_tier=entry.backend.cost_policy_tier,
    )
    plan = prepare_execution(
        "Check fallback option compatibility",
        profile,
        (entry,),
        review_prompt=False,
    ).execution_plan
    assert plan is not None
    argv = ["--mode", "ask", *option]
    if shared_profile:
        argv.extend(["--shared-tools", shared_profile, "--approval-policy", "workspace_write"])
    else:
        argv.extend(["--approval-policy", "trusted_local"])
    args = build_argument_parser().parse_args(argv)

    reason = cli._fallback_target_incompatibility(
        plan.target,
        args,
        tmp_path,
        probe_provider=False,
    )

    if option[0] == "--codex-persist-session":
        assert reason == "Codex session persistence is not mapped for alternate clients"
    else:
        expected_target = "common inspection" if shared_profile else "alternate clients"
        assert reason == f"Codex-specific options are not mapped for {expected_target}"


@pytest.mark.parametrize(
    "option",
    [
        ("--codex-resume", "session-123"),
        ("--codex-persist-session",),
        ("--codex-search",),
        ("--codex-image", "image.png"),
        ("--codex-output-schema", "schema.json"),
        ("--codex-mcp-tools",),
        ("--codex-output-last-message", "last-message.txt"),
    ],
)
@pytest.mark.parametrize("shared_profile", [None, "coding"])
def test_readiness_preserves_codex_options_on_codex_routes(option, shared_profile, tmp_path):
    from ai_orchestrator import load_model_catalog, prepare_execution

    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    entry = next(item for item in catalog if item.backend.route_id == "openai-codex-gpt-5-5")
    profile = cli.coding_task_profile(
        privacy_class=cli.OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        route_id_override=entry.backend.route_id,
        cost_policy_tier=entry.backend.cost_policy_tier,
    )
    plan = prepare_execution(
        "Check Codex option compatibility",
        profile,
        (entry,),
        review_prompt=False,
    ).execution_plan
    assert plan is not None
    argv = ["--mode", "ask", *option]
    if shared_profile:
        argv.extend(["--shared-tools", shared_profile, "--approval-policy", "workspace_write"])
    else:
        argv.append("--approval-policy")
        argv.append("trusted_local")
    args = build_argument_parser().parse_args(argv)
    args.fallback_session = None

    reason = cli._fallback_target_incompatibility(
        plan.target,
        args,
        tmp_path,
        probe_provider=False,
    )

    if option[0] == "--codex-mcp-tools" and shared_profile:
        assert reason == "Shared inspection cannot be combined with legacy Codex MCP tools"
    else:
        assert reason is None


@pytest.mark.parametrize(
    "approval_policy",
    ["read_only", "interactive", "workspace_write", "trusted_local"],
)
def test_readiness_reports_unsupported_unshared_alternate_approval(
    monkeypatch,
    tmp_path,
    approval_policy,
):
    from ai_orchestrator import load_model_catalog, prepare_execution

    monkeypatch.setattr(
        "ai_provider.external_agents.external_agent_command",
        lambda _method: "mock-client",
    )
    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    entry = next(item for item in catalog if item.backend.route_id == "github-copilot-cli-default")
    profile = cli.coding_task_profile(
        privacy_class=cli.OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        route_id_override=entry.backend.route_id,
        cost_policy_tier=entry.backend.cost_policy_tier,
    )
    plan = prepare_execution(
        "Check approval compatibility",
        profile,
        (entry,),
        review_prompt=False,
    ).execution_plan
    assert plan is not None
    args = build_argument_parser().parse_args(
        ["--mode", "ask", "--approval-policy", approval_policy]
    )

    reason = cli._fallback_target_incompatibility(
        plan.target,
        args,
        tmp_path,
        probe_provider=False,
    )

    if approval_policy == "trusted_local":
        assert reason is None
    else:
        assert reason == (
            "copilot_cli: only trusted_local is mapped; other approval modes are not mapped yet."
        )


@pytest.mark.parametrize(
    "action", ["--execute", "--start-ollama", "--codex-login", "--codex-mcp-setup"]
)
def test_offline_report_rejects_execution_and_setup(tmp_path, action):
    with pytest.raises(SystemExit) as caught:
        cli.main(offline_args(tmp_path, action))
    assert caught.value.code == 2


@pytest.mark.parametrize(
    "flags",
    [
        ("--native-tools", "--no-native-tools"),
        ("--codex-persist-session", "--codex-resume", "session-123"),
    ],
)
def test_offline_report_rejects_conflicting_execution_options(tmp_path, flags):
    with pytest.raises(SystemExit) as caught:
        cli.main(offline_args(tmp_path, *flags))
    assert caught.value.code == 2


def test_provider_option_exclusion_is_precise_and_does_not_probe(tmp_path):
    from ai_orchestrator import TaskProfile, load_model_catalog, prepare_execution

    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    plan = prepare_execution("Explain", TaskProfile(), catalog, review_prompt=False).execution_plan
    assert plan is not None
    args = build_argument_parser().parse_args(["--codex-search"])
    reason = cli._fallback_target_incompatibility(plan.target, args, tmp_path, probe_provider=False)
    assert reason == "provider executor cannot preserve requested options: --codex-search"


@pytest.mark.parametrize(
    "method,route_id",
    [
        ("codex_cli", "openai-codex-gpt-5-5"),
        ("copilot_cli", "github-copilot-cli-default"),
        ("kiro_cli", "kiro-cli-default"),
        ("antigravity_cli", "google-antigravity-gemini-3-1-pro"),
    ],
)
@pytest.mark.parametrize(
    "shared_profile,requested_policy,effective_policy",
    [
        ("inspection", "read_only", "read_only"),
        ("inspection", "interactive", "read_only"),
        ("coding", "read_only", "read_only"),
        ("coding", "interactive", "interactive"),
        ("coding", "workspace_write", "workspace_write"),
        ("coding", "trusted_local", "trusted_local"),
    ],
)
def test_shared_fallback_compatibility_preserves_profile_and_approval(
    monkeypatch,
    tmp_path,
    method,
    route_id,
    shared_profile,
    requested_policy,
    effective_policy,
):
    from ai_orchestrator import (
        AccessMethod,
        load_model_catalog,
        prepare_execution,
    )

    selected_method = AccessMethod(method)
    monkeypatch.setattr(
        "ai_provider.external_agents.external_agent_command",
        lambda access_method: "mock-client" if access_method is selected_method else None,
    )
    catalog = load_model_catalog("packages/ai_orchestrator/examples/model_catalog.toml")
    entry = next(item for item in catalog if item.backend.route_id == route_id)
    profile = cli.coding_task_profile(
        privacy_class=cli.OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        route_id_override=route_id,
        cost_policy_tier=entry.backend.cost_policy_tier,
    )
    plan = prepare_execution(
        "Check shared fallback compatibility",
        profile,
        (entry,),
        review_prompt=False,
    ).execution_plan
    assert plan is not None
    args = build_argument_parser().parse_args(
        [
            "--mode",
            "implement",
            "--shared-tools",
            shared_profile,
            "--approval-policy",
            requested_policy,
        ]
    )
    config = cli._fallback_config(plan.target, args, tmp_path)

    assert config.shared_tool_profile == shared_profile
    expected_config_policy = (
        "never"
        if selected_method is AccessMethod.CODEX_CLI and shared_profile == "inspection"
        else effective_policy
    )
    assert config.approval_policy == expected_config_policy
    assert config.sandbox == "read-only"
    reason = cli._fallback_target_incompatibility(
        plan.target,
        args,
        tmp_path,
        probe_provider=False,
    )
    if selected_method is AccessMethod.ANTIGRAVITY_CLI:
        assert reason is not None
        assert "headless mode denies MCP tools" in reason
        assert "permissions.allow" in reason
        assert "--dangerously-skip-permissions is not supported" in reason
    else:
        assert reason is None
