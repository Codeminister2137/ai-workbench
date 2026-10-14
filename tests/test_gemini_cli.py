"""Gemini's native transport preserves shared tools and free-route boundaries offline."""

import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from ai_orchestrator import AccessMethod, BillingSource, CostPolicyTier, load_model_catalog
from ai_provider import gemini_cli
from ai_provider.agent_readiness import check_agent_readiness
from ai_provider.execution_fallback import external_usage_limit
from ai_provider.external_agents import (
    ExternalAgentConfig,
    ExternalAgentResult,
    build_external_agent_command,
    is_external_agent_access_method,
    run_external_agent,
)


@pytest.fixture
def configured(tmp_path, monkeypatch):
    package = tmp_path / "client"
    package.mkdir()
    (package / "package.json").write_text(
        json.dumps(
            {
                "name": "@google/gemini-cli",
                "version": gemini_cli.CLI_VERSION,
            }
        )
    )
    entry = package / "bundle/gemini.js"
    entry.parent.mkdir()
    entry.write_text("// official entry fixture")
    monkeypatch.setenv("GEMINI_CLI_COMMAND", str(entry))
    monkeypatch.setenv("GEMINI_NODE_COMMAND", "node-fixture")
    for name in gemini_cli.AUTH_OVERRIDES:
        monkeypatch.delenv(name, raising=False)
    return ExternalAgentConfig(
        AccessMethod.GEMINI_CLI,
        str(entry),
        "gemini-3.5-flash",
        tmp_path,
        10,
        sandbox="read-only",
        approval_policy="workspace_write",
        shared_tool_profile="coding",
    )


def stream(*events):
    return "\n".join(json.dumps(event) for event in events)


def test_gemini_command_uses_explicit_node_model_and_no_broad_permissions(configured):
    command = build_external_agent_command(configured)
    assert is_external_agent_access_method(AccessMethod.GEMINI_CLI)
    assert command[:2] == ("node-fixture", configured.command)
    assert command[command.index("--model") + 1] == "gemini-3.5-flash"
    assert command[command.index("--allowed-mcp-server-names") + 1] == "repo_shared"
    assert not {"--yolo", "--allow-all", "--sandbox"}.intersection(command)


@pytest.mark.parametrize(
    "changes",
    [
        {"shared_tool_profile": None},
        {"resume": "latest"},
        {"web_search": True},
        {"image_paths": (Path("image.png"),)},
        {"output_schema_path": Path("schema.json")},
        {"model": "auto"},
        {"sandbox": "danger-full-access"},
        {"json_output": False},
    ],
)
def test_gemini_refuses_unmapped_or_unrestricted_options(configured, changes):
    with pytest.raises((ValueError, NotImplementedError)):
        build_external_agent_command(replace(configured, **changes))


def test_unaccepted_client_version_is_ineligible(configured):
    package = Path(configured.command).parent.parent / "package.json"
    package.write_text('{"name":"@google/gemini-cli","version":"0.65.0"}')
    assert not check_agent_readiness(AccessMethod.GEMINI_CLI).ready


def test_invocation_carries_complete_stdin_and_scoped_settings_then_cleans(configured):
    payload = "Required instructions\nEarlier user history\nPartial progress\nNew task"
    settings_paths = []
    original_env = dict(os.environ)

    def runner(command, **kwargs):
        assert kwargs["input"] == payload
        assert payload not in command
        assert kwargs["env"]["GEMINI_CLI_TRUST_WORKSPACE"] == "true"
        settings_path = configured.cwd / ".gemini/settings.json"
        settings_paths.append(settings_path)
        settings = json.loads(settings_path.read_text())
        assert settings["tools"]["core"] == []
        assert settings["tools"]["discoveryCommand"] == ""
        assert settings["hooksConfig"]["enabled"] is False
        assert settings["security"]["auth"]["enforcedType"] == "oauth-personal"
        assert settings["advanced"]["ignoreLocalEnv"] is True
        assert settings["mcpServers"]["repo_shared"]["trust"] is True
        assert "edit_file" in settings["mcpServers"]["repo_shared"]["includeTools"]
        assert "--approval-policy" in settings["mcpServers"]["repo_shared"]["args"]
        return subprocess.CompletedProcess(
            command,
            0,
            stream(
                {"type": "message", "role": "assistant", "delta": True, "content": "Done"},
                {"type": "result", "status": "success"},
            ),
            "",
        )

    result = run_external_agent(payload, configured, runner=runner)
    assert result.events and result.events.final_answer == "Done"
    assert result.cleanup_verified is None  # A fake runner cannot certify process cleanup.
    assert settings_paths and not settings_paths[0].exists()
    assert os.environ == original_env
    assert not (configured.cwd / ".gemini").exists()


def test_failed_invocation_removes_settings_and_retains_workspace(configured):
    paths = []
    original = configured.cwd / "original.txt"
    original.write_text("preserve")

    def runner(command, **kwargs):
        paths.append(configured.cwd / ".gemini/settings.json")
        raise OSError("fixture failure")

    with pytest.raises(OSError, match="fixture failure"):
        run_external_agent("task", configured, runner=runner)
    assert not paths[0].exists()
    assert original.read_text() == "preserve"


@pytest.mark.parametrize("name", gemini_cli.AUTH_OVERRIDES)
def test_auth_overrides_refuse_before_process_start(configured, monkeypatch, name):
    monkeypatch.setenv(name, "fixture")
    assert not check_agent_readiness(AccessMethod.GEMINI_CLI).ready
    with pytest.raises(ValueError, match="override"):
        run_external_agent("task", configured, runner=lambda *a, **k: pytest.fail("launched"))


def test_cached_google_sign_in_cannot_admit_retired_individual_route(configured, monkeypatch):
    monkeypatch.setenv("GEMINI_CLI_HOME", str(configured.cwd))
    home = configured.cwd / ".gemini"
    home.mkdir()
    (home / "settings.json").write_text('{"security":{"auth":{"selectedType":"oauth-personal"}}}')
    assert not check_agent_readiness(AccessMethod.GEMINI_CLI).ready
    (home / "oauth_creds.json").write_text("not JSON; contents must never be read")
    readiness = check_agent_readiness(AccessMethod.GEMINI_CLI)
    assert not readiness.ready and "retired on 2026-06-18" in readiness.reason
    assert not readiness.login_command
    (home / "settings.json").write_text('{"security":{"auth":{"selectedType":"gemini-api-key"}}}')
    assert not check_agent_readiness(AccessMethod.GEMINI_CLI).ready


def test_existing_project_settings_are_preserved_and_refused(configured):
    directory = configured.cwd / ".gemini"
    directory.mkdir()
    path = directory / "settings.json"
    path.write_text('{"user":"keep"}')
    with pytest.raises(FileExistsError):
        run_external_agent("task", configured, runner=lambda *a, **k: pytest.fail("launched"))
    assert path.read_text() == '{"user":"keep"}'


def test_modified_generated_settings_are_retained(configured):
    def runner(command, **kwargs):
        (configured.cwd / ".gemini/settings.json").write_text("changed by client")
        return subprocess.CompletedProcess(command, 1, "", "failed")

    run_external_agent("task", configured, runner=runner)
    assert (configured.cwd / ".gemini/settings.json").read_text() == "changed by client"


def test_stream_joins_only_assistant_deltas_after_last_tool_and_records_native_usage():
    events = gemini_cli.parse_events(
        stream(
            {"type": "message", "role": "user", "content": "quota exceeded"},
            {"type": "message", "role": "assistant", "content": "Inspecting"},
            {"type": "tool_use", "tool_name": "repo_shared__read_file", "tool_id": "1"},
            {"type": "tool_result", "tool_id": "1", "status": "error", "output": "quota exceeded"},
            {"type": "message", "role": "assistant", "delta": True, "content": "Reviewed "},
            {"type": "message", "role": "assistant", "delta": True, "content": "and done."},
            {
                "type": "result",
                "status": "success",
                "stats": {
                    "input_tokens": 120,
                    "output_tokens": 25,
                    "total_tokens": 150,
                    "cached": 80,
                    "models": {"gemini-3.5-flash": {"input_tokens": 120}},
                },
            },
        )
    )
    assert events.final_answer == "Reviewed and done."
    assert len(events.tool_events) == 2 and not events.failure_reason
    assert events.usage and events.usage["cached_input_tokens"] == 80
    assert events.usage["source"] == "gemini_cli" and events.usage["scope"] == "session"
    assert not external_usage_limit(ExternalAgentResult((), 0, "", "", events=events))


def test_only_native_failed_error_channel_triggers_usage_fallback():
    events = gemini_cli.parse_events(
        stream(
            {"type": "error", "severity": "error", "message": "RESOURCE_EXHAUSTED: quota exceeded"},
            {"type": "result", "status": "error", "error": {"message": "quota exceeded"}},
        )
    )
    assert external_usage_limit(ExternalAgentResult((), 0, "", "", events=events))


def test_gemini_echo_redaction_does_not_reduce_sent_input_or_assistant_review(configured):
    prompt = "Required private instructions and complete history"

    def runner(command, **kwargs):
        assert kwargs["input"] == prompt
        return subprocess.CompletedProcess(
            command,
            0,
            stream(
                {"type": "message", "role": "user", "content": prompt},
                {"type": "message", "role": "assistant", "content": "Substantive review"},
                {"type": "result", "status": "success"},
            ),
            "",
        )

    result = run_external_agent(prompt, configured, runner=runner)
    assert prompt not in result.stdout and "[user input omitted]" in result.stdout
    assert result.events and result.events.final_answer == "Substantive review"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not JSON",
        '{"type":"message","role":"assistant","content":"done"}',
    ],
)
def test_incomplete_or_invalid_stream_is_never_success(text):
    assert gemini_cli.parse_events(text).failure_reason


def test_opt_in_catalog_is_distinct_from_default_and_other_google_products():
    root = Path(__file__).resolve().parents[1]
    opt_in = load_model_catalog(root / "packages/ai_orchestrator/examples/gemini_cli_catalog.toml")
    entry = next(item for item in opt_in if item.backend.access_method is AccessMethod.GEMINI_CLI)
    assert entry.backend.access_method is AccessMethod.GEMINI_CLI
    assert entry.backend.product == "gemini_cli"
    assert entry.backend.billing_source is BillingSource.GEMINI_CLI_FREE
    assert entry.backend.cost_policy_tier is CostPolicyTier.FREE_ONLY
    default = load_model_catalog(root / "packages/ai_orchestrator/examples/model_catalog.toml")
    assert not any(item.backend.access_method is AccessMethod.GEMINI_CLI for item in default)
    requesty = next(item for item in opt_in if item.backend.product == "requesty_free")
    assert requesty == next(
        item for item in default if item.backend.route_id == requesty.backend.route_id
    )


def test_gemini_free_fallback_preserves_quality_privacy_and_billing_tier():
    from ai_orchestrator import PrivacyClass, QualityThreshold, TaskCapability, TaskProfile
    from ai_orchestrator.fallback import fallback_candidates
    from ai_orchestrator.planner import ExecutionTarget

    root = Path(__file__).resolve().parents[1]
    opt_in = load_model_catalog(root / "packages/ai_orchestrator/examples/gemini_cli_catalog.toml")
    gemini = next(item for item in opt_in if item.backend.access_method is AccessMethod.GEMINI_CLI)
    default = load_model_catalog(root / "packages/ai_orchestrator/examples/model_catalog.toml")
    requesty = next(
        item for item in default if item.backend.route_id == "requesty-free-gemma-4-31b"
    )
    backend = requesty.backend
    target = ExecutionTarget(
        backend.route_id,
        backend.provider,
        backend.product,
        backend.model,
        backend.access_method,
        backend.auth_method,
        backend.billing_source,
        backend.cost_policy_tier,
    )
    catalog = (*default, gemini)
    profile = TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.FREE_ONLY,
        required_capabilities=frozenset({TaskCapability.CHAT, TaskCapability.TOOLS}),
        quality_threshold=QualityThreshold.STANDARD,
    )
    assert [item.backend.route_id for item in fallback_candidates(profile, catalog, target)] == [
        "gemini-cli-free-flash"
    ]
    assert not fallback_candidates(
        replace(profile, quality_threshold=QualityThreshold.HIGH), catalog, target
    )
    assert not fallback_candidates(
        replace(profile, privacy_class=PrivacyClass.LOCAL_ONLY), catalog, target
    )
    assert not fallback_candidates(
        profile, catalog, target, exhausted_billing_sources=frozenset({"gemini_cli_free"})
    )
