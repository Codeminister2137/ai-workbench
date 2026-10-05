"""Repo-assistant cli basics regression contracts."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest

from .support import (
    _EXAMPLE,
    _EXAMPLE_PATH,
    _AsciiTerminal,
    _TeeOutput,
    main,
)


def test_tee_output_preserves_utf8_transcript_when_terminal_replaces_unicode() -> None:
    terminal = _AsciiTerminal()
    transcript = StringIO()
    tee = _TeeOutput(terminal, transcript)

    assert tee.write("Understand ↓ Inspect") == len("Understand ↓ Inspect")

    assert transcript.getvalue() == "Understand ↓ Inspect"
    assert terminal.getvalue() == "Understand ? Inspect"


def test_tee_output_flushes_progress_to_disk(tmp_path):
    path = tmp_path / "transcript.log"
    with path.open("w", encoding="utf-8") as transcript:
        tee = _TeeOutput(StringIO(), transcript)
        tee.write("started research\n")
        assert path.read_text() == "started research\n"


def test_cli_help_lists_google_provider() -> None:
    result = __import__("subprocess").run(
        [
            sys.executable,
            str(_EXAMPLE_PATH),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--provider {ollama,openai,requesty,google}" in result.stdout
    assert "--mode {ask,review,implement,plan,diagnose,chat}" in result.stdout
    assert "--scrutinize-response" in result.stdout
    assert "--approval-policy" in result.stdout
    assert "--codex-search" in result.stdout
    assert "--codex-mcp-tools" in result.stdout
    assert "--codex-image" in result.stdout
    assert "--codex-mcp-setup" in result.stdout
    assert "--codex-mcp-register-global" in result.stdout
    assert "--codex-login" in result.stdout
    assert "--codex-login-device" in result.stdout
    assert "--away-minutes" in result.stdout
    assert "--orchestrated" in result.stdout
    assert "--away-run-db" in result.stdout
    assert "--chat-db" in result.stdout
    assert "--chat-session" in result.stdout
    assert "--chat-list" in result.stdout
    assert "--chat-context-mode" in result.stdout
    assert "--chat-history-budget-chars" in result.stdout
    assert "--chat-recent-message-count" in result.stdout


def test_instruction_overflow_refuses_before_route_preparation(tmp_path, monkeypatch, capsys):
    (tmp_path / "AGENTS.md").write_text("required rules" * 10)
    monkeypatch.setattr(
        _EXAMPLE, "prepare_execution", lambda *a, **kw: pytest.fail("must not prepare a route")
    )
    status = main(["Review", "--repo-root", str(tmp_path), "--instruction-budget-chars", "10"])
    assert status == 1
    assert "instructions were not truncated" in capsys.readouterr().out


def test_repo_assistant_script_uses_stable_package_entrypoint() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "repo-assistant.ps1"
    text = script.read_text(encoding="utf-8")

    assert "python -m uv run ai-assistant" in text
    assert "examples\\repo_coding_assistant.py" not in text
    assert "Add-DefaultLogFile" in text
    assert "artifacts\\repo-assistant-$timestamp" in text
    assert '"assistant.log"' in text
    assert '"--ollama-log-file"' in text
    assert '--codex-login"' in text
    assert '--codex-login-device"' in text


def test_broad_analysis_script_keeps_canonical_manual_workflow() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "repo-assistant-broad-analysis.ps1"
    text = script.read_text(encoding="utf-8")

    assert '"--mode", "ask"' in text
    assert '"--execute"' in text
    assert '"--start-ollama"' in text
    assert '"--scrutinize-response"' in text
    assert '"--log-full-prompt"' in text
    assert "artifacts\\repo-assistant-broad-analysis-$timestamp" in text
    assert "$artifactDirectory\\assistant.log" in text
    assert "$artifactDirectory\\ollama.log" in text
    assert '"--log-file", $LogFile' in text
    assert '"--ollama-log-file", $OllamaLogFile' in text
    assert 'repo-assistant.ps1") @cliArgs' in text


def test_research_script_keeps_local_unattended_defaults() -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "repo-assistant-research.ps1"
    text = script.read_text(encoding="utf-8")

    assert '[string] $Model = "gpt-oss:20b"' in text
    assert "[double] $AwayMinutes = 110" in text
    assert "artifacts\\research-${safeTopic}-${timestamp}" in text
    assert "$artifactDirectory\\report.md" in text
    assert '"--away-run-db", "$artifactDirectory\\runs.sqlite3"' in text
    assert '"--privacy", "local_only"' in text
    assert '"--cost-policy", "local_only"' in text
    assert '"--approval-policy", "trusted_local"' in text
    assert '"--orchestrated"' in text
    assert '"--max-repair-cycles", "-1"' in text
    assert '"--tool-profile", "research"' in text
    assert '"--research-report", $OutputFile' in text
    assert '$effectiveArgs += @($CliArgs | Where-Object { $_ -ne "" })' in text
    assert '"--env-file", ".env"' in text
    assert '"python", "-m", "ai_provider.research_runner"' in text
    assert '$nativeArgs = @("-m", "uv") + $uvArgs + $effectiveArgs' in text
    assert "python @nativeArgs" in text
    assert '"--search-provider", $SearchProvider' in text
    assert '"--search-privacy", $SearchPrivacy' in text


def test_cli_modes_enforce_action_boundaries(capsys, monkeypatch, tmp_path) -> None:
    from ai_provider.local_capabilities import LocalProviderCapabilitySnapshot, LocalSystemInfo

    snapshot = LocalProviderCapabilitySnapshot(
        system=LocalSystemInfo("TestOS", "1", "test", "test"),
        models_path=tmp_path,
        models_disk=None,
        ollama_available=False,
        ollama_version=None,
        installed_ollama_models=(),
        running_ollama_models=(),
    )
    monkeypatch.setattr(
        "ai_provider.repo_coding_assistant.get_local_provider_capability_snapshot", lambda: snapshot
    )
    monkeypatch.setattr(_EXAMPLE, "_external_agent_status", lambda: {"codex": {}})
    assert main(["--mode", "diagnose"]) == 0
    diagnose_output = capsys.readouterr().out
    assert '"system"' in diagnose_output
    assert '"external_agents"' in diagnose_output

    with pytest.raises(SystemExit):
        main(["--mode", "implement", "make a change"])


def test_plan_mode_does_not_create_a_provider_client(capsys, monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review the selected implementation.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "mode: plan" in output
    assert "status: ready" in output
    assert "delegation: disabled" in output
    assert "execution_status: planned" in output


def test_cli_log_file_captures_invocation_and_transcript(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)
    log_file = tmp_path / "repo-assistant.log"

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review CLI logging.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--log-file",
                str(log_file),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    text = log_file.read_text(encoding="utf-8")

    assert "=== CLI invocation ===" in text
    assert "timestamp_utc:" in text
    assert "cwd:" in text
    assert "Review CLI logging." in text
    assert '"--mode", "plan"' in text
    assert '"--log-file"' in text
    assert "=== Repo Coding Assistant ===" in text
    assert "execution_status: planned" in text
    assert "=== Run metrics ===" in text
    assert "total_wall_seconds:" in text
    assert "process_cpu_seconds:" in text
    assert "python_memory_peak_bytes:" in text
    assert "primary_elapsed_seconds:" in text
    assert "primary_usage_source: unavailable" in text
    assert "scrutiny_usage_source: unavailable" in text
    assert "=== Primary model input ===" not in text
    assert output == text


def test_cli_log_full_prompt_captures_assembled_model_input(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)
    log_file = tmp_path / "repo-assistant.log"

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review CLI full-prompt logging.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--log-file",
                str(log_file),
                "--log-full-prompt",
            ]
        )
        == 0
    )
    text = log_file.read_text(encoding="utf-8")

    assert "=== Primary model input ===" in text
    assert "system_prompt:" in text
    assert "user_prompt:" in text
    assert "Do not emit local" in text
    assert "action JSON" in text
    assert "Supported action types:" not in text
    assert "# User request" in text
    assert "Review CLI full-prompt logging." in text
    assert "# Repository context" in text
    assert "AGENTS.md" in text
    assert capsys.readouterr().out == text


def test_default_system_prompt_only_includes_action_json_when_enabled() -> None:
    from ai_provider.repo_context import build_default_system_prompt

    answer_prompt = build_default_system_prompt(actions_enabled=False)
    action_prompt = build_default_system_prompt(actions_enabled=True)

    assert "Do not emit local" in answer_prompt
    assert "action JSON" in answer_prompt
    assert "Supported action types:" not in answer_prompt
    assert "Supported action types:" in action_prompt
    assert '{"actions"' in action_prompt


def test_log_full_prompt_requires_log_file() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Review logging.", "--log-full-prompt"])


def test_stable_ai_assistant_entry_point_loads_cli() -> None:
    from ai_provider.cli import main as stable_main

    assert stable_main(["--mode", "plan", "Review code.", "--provider", "ollama"]) == 0


def test_stable_cli_reports_provider_failures(capsys, monkeypatch) -> None:
    from ai_provider import ProviderError
    from ai_provider import repo_coding_assistant as stable_cli

    def fail_request(*args, **kwargs):
        raise ProviderError("provider unavailable")

    monkeypatch.setattr(stable_cli, "run_coding_prompt", fail_request)

    assert (
        stable_cli.main(
            [
                "--mode",
                "ask",
                "Review code.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert "status: failed" in output
    assert "failure_reason: provider unavailable" in output
    assert "execution_status: failed" in output


def test_tee_output_writes_to_terminal_and_transcript() -> None:
    from io import StringIO

    terminal = StringIO()
    transcript = StringIO()
    output = _TeeOutput(terminal, transcript)

    output.write("assistant output\n")
    output.flush()

    assert terminal.getvalue() == "assistant output\n"
    assert transcript.getvalue() == "assistant output\n"
