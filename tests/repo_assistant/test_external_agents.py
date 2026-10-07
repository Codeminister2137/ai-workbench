"""Repo-assistant external agents regression contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

from .support import (
    _EXAMPLE,
    main,
    parse_external_agent_jsonl,
)


def test_cli_plans_codex_external_agent_route(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--codex-mcp-tools",
                "--skip-prompt-review",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "route_id: openai-codex-gpt-5-5" in output
    assert "access_method: codex_cli" in output
    assert "external_agent_command: codex-test" in output
    assert "external_agent_command_line_json:" in output
    assert "external_agent_mcp_tools: True" in output
    assert "delegation: enabled: external Codex MCP delegate_task available" in output
    assert "delegation: disabled" not in output
    assert "delegate_task" in output
    assert "execution_status: planned" in output


def test_cli_approval_policy_read_only_maps_to_codex_sandbox(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Inspect this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--approval-policy",
                "read_only",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "approval_policy: read_only" in output
    assert "external_agent_sandbox: read-only" in output
    assert '"--ask-for-approval", "never"' in output
    assert '"--sandbox", "read-only"' in output


def test_cli_approval_policy_trusted_local_maps_to_commit_capable_codex_sandbox(
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Implement the change.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--approval-policy",
                "trusted_local",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "approval_policy: trusted_local" in output
    assert "external_agent_sandbox: danger-full-access" in output
    assert '"--ask-for-approval", "never"' in output
    assert '"--sandbox", "danger-full-access"' in output


def test_cli_rejects_codex_commit_request_without_trusted_local(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "implement",
                "Commit that slice.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--native-tools",
                "--approval-policy",
                "workspace_write",
                "--skip-prompt-review",
            ]
        )


def test_cli_executes_codex_external_agent_route(capsys, monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        if tuple(args[0][:2]) == ("git", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(args[0], 0, " M example.py\n", "")
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            "\n".join(
                [
                    '{"type":"command.started","command":"git status --short"}',
                    '{"type":"tool.completed","name":"read_file"}',
                    '{"type":"tool.completed","name":"delegate_task"}',
                    '{"type":"item.completed","item":{"type":"web_search","query":"OpenAI"}}',
                    '{"type":"file_change","path":"example.py"}',
                    '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}',
                    '{"type":"final_answer","content":"codex done"}',
                ]
            )
            + "\n",
            "",
        )

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    monkeypatch.setattr(
        _EXAMPLE,
        "_run_validation_commands",
        lambda *args, **kwargs: (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=0,
                status="passed",
                elapsed_seconds=0.01,
            ),
        ),
    )

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--approval-policy",
                "workspace_write",
                "--skip-prompt-review",
                "--codex-mcp-tools",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "external_agent_returncode: 0" in output
    assert "external_agent_jsonl_events: parsed" in output
    assert "external_agent_command_line_json:" in output
    assert "external_agent_command_event_count: 1" in output
    assert "external_agent_tool_event_count: 2" in output
    assert "external_agent_web_search_event_count: 1" in output
    assert "external_agent_file_change_event_count: 1" in output
    assert "external_agent_usage_json:" in output
    assert (
        "delegation: enabled: external Codex MCP delegate_task available; "
        "completed: external Codex MCP delegate_task"
    ) in output
    assert "codex done" in output
    assert "execution_status: completed" in output
    assert "external_agent_status: running elapsed_seconds=0.0" in output
    assert "away_stage_status: validation status=completed" in output
    assert "away_stage_status: final_handoff status=completed" in output
    assert "## **SUMMARY**" in output
    assert "- Validated: passed" in output
    assert "- Notes: status=ready; execution_status=completed" in output
    assert "### Agent report\ncodex done" in output
    assert output.rfind("codex done") > output.rfind("execution_status: completed")
    command = next(call["args"][0] for call in calls if "exec" in call["args"][0])
    exec_index = command.index("exec")
    approval_index = command.index("--ask-for-approval")
    assert command[0] == "codex-test"
    assert command[approval_index : approval_index + 2] == ("--ask-for-approval", "never")
    assert approval_index < exec_index
    assert "--json" in command
    assert "--sandbox" in command
    assert "workspace-write" in command
    exec_call = next(call for call in calls if "exec" in call["args"][0])
    stdin_prompt = exec_call["kwargs"]["input"]
    assert stdin_prompt.startswith("# Repo assistant system prompt")
    assert "You are a repo-aware coding assistant." in stdin_prompt
    assert "## **SUMMARY**" in stdin_prompt
    assert "# User request" in stdin_prompt
    assert "# External agent execution metadata" in stdin_prompt
    assert "codex_sandbox: workspace-write" in stdin_prompt
    assert "Do not describe the session as read-only" in stdin_prompt
    assert calls[0]["kwargs"]["encoding"] == "utf-8"
    assert calls[0]["kwargs"]["errors"] == "replace"
    assert "# Repository context" in stdin_prompt
    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    run_record = store.get_run(run_id)
    assert run_record is not None
    assert run_record.execution_status == "completed"
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    assert stage_by_name["validation"].status == "completed"
    validation_details = stage_by_name["validation"].details
    assert validation_details is not None
    assert validation_details["validation_status"] == "passed"
    assert stage_by_name["final_handoff"].status == "completed"
    final_handoff_details = stage_by_name["final_handoff"].details
    assert final_handoff_details is not None
    assert final_handoff_details["final_answer_available"] is True
    assert final_handoff_details["assistant_response_available"] is False
    assert final_handoff_details["changed_files"] == [" M example.py"]


def test_external_agent_jsonl_parser_extracts_failure_and_final_answer() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            [
                '{"type":"agent_message","role":"assistant","content":"intermediate"}',
                '{"type":"item.completed","item":{"type":"web_search","query":"OpenAI"}}',
                '{"type":"turn.failed","error":{"message":"sandbox denied"}}',
                '{"type":"final_answer","content":"last answer"}',
                "not-json",
            ]
        )
    )

    assert events.final_answer == "last answer"
    assert events.failure_reason == "sandbox denied"
    assert len(events.web_search_events) == 1
    assert events.parse_errors


def test_cli_does_not_print_raw_jsonl_when_codex_fails(capsys, monkeypatch) -> None:
    raw_jsonl = '{"type":"turn.failed","error":{"message":"unsupported model"}}\n'

    def fake_run(*args, **kwargs):
        return _EXAMPLE.subprocess.CompletedProcess(args[0], 1, raw_jsonl, "")

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "external_agent_failure_reason: unsupported model" in output
    assert "external_agent_final_answer: unavailable" in output
    assert raw_jsonl.strip() not in output


def test_cli_reports_nonzero_external_agent_exit_without_jsonl_failure(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fake_run(*args, **kwargs):
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            2,
            '{"type":"final_answer","content":"partial answer"}\n',
            "plain stderr failure detail",
        )

    log_file = tmp_path / "transcript.log"
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
                "--log-file",
                str(log_file),
            ]
        )
        == 2
    )

    output = capsys.readouterr().out
    assert "partial answer" in output
    assert "external_agent_failure_reason: process exited with code 2" in output
    assert "external_agent_failure_hint: inspect external_agent_stderr_file" in output
    assert "external_agent_stderr_file:" in output
    assert "external_agent_stderr_summary: filtered stderr captured" in output
    assert "external_agent_stderr_first_line: plain stderr failure detail" in output
    assert "execution_status: failed" in output
    assert output.rfind("partial answer") > output.rfind("execution_status: failed")


def test_cli_reports_antigravity_headless_refusal_despite_zero_exit(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fake_run(*args, **kwargs):
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            "",
            "jetski: no output produced; headless mode tool was auto-denied",
        )

    monkeypatch.setenv("ANTIGRAVITY_COMMAND", "agy-test")
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda *args, **kwargs: AgentReadiness(True, "fixture authentication ready"),
    )
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "google-antigravity-gemini-3-1-pro",
                "--approval-policy",
                "trusted_local",
                "--execute",
                "--skip-prompt-review",
                "--log-file",
                str(tmp_path / "transcript.log"),
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "execution_status: failed" in output
    assert "external_agent_returncode: 0" in output
    assert "headless tool permission was denied" in output


def test_cli_explains_codex_timeout_without_duplicate_response_header(
    capsys,
    monkeypatch,
) -> None:
    def fake_run(*args, **kwargs):
        raise _EXAMPLE.subprocess.TimeoutExpired(args[0], timeout=60.0)

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert output.count("## **SUMMARY**") == 1
    assert output.count("### Agent report") == 1
    assert "failure_hint: Codex CLI did not finish before the repo assistant timeout" in output
    assert "--codex-login-device" in output


def test_external_agent_stderr_summarizes_pytest_failures() -> None:
    stderr = "\n".join(
        [
            "2026-09-29T16:24:07Z ERROR codex_core::tools::router: error=Exit code: 1",
            "Output:",
            "================================== FAILURES ===================================",
            "__________________ test_cli_plans_codex_external_agent_route __________________",
            "FAILED tests/test_repo_coding_assistant_example.py::test_one - AssertionError",
            "FAILED tests/test_repo_coding_assistant_example.py::test_two - AssertionError",
        ]
    )

    summary = _EXAMPLE._format_external_agent_stderr(stderr, limit=1)

    assert summary.startswith("external_agent_stderr_summary:")
    assert "FAILURES" not in summary
    assert "external_agent_stderr_first_line: test_cli_plans_codex_external_agent_route" in summary
    assert "pytest_failures_detected: 2" in summary
    assert "pytest_failure: tests/test_repo_coding_assistant_example.py::test_one" in summary
    assert "pytest_failures_omitted: 1; see external_agent_stderr_file" in summary


def test_external_agent_jsonl_parser_ignores_completed_failure_mentions() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            [
                '{"type":"item.completed","item":{"type":"agent_message",'
                '"text":"Validation initially failed, then passed."}}',
                '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}',
            ]
        )
    )

    assert events.failure_reason is None


def test_external_agent_stderr_filters_noisy_codex_model_refresh() -> None:
    stderr = "\n".join(
        [
            "2026-09-28T08:57:23Z ERROR codex_models_manager::manager: "
            "failed to refresh available models: unknown variant `max`",
            "actionable stderr",
        ]
    )

    assert _EXAMPLE._format_external_agent_stderr(stderr) == (
        "external_agent_stderr_summary: filtered stderr captured; "
        "see external_agent_stderr_file for full output\n"
        "external_agent_stderr_first_line: actionable stderr\n"
    )


def test_external_agent_stderr_sidecar_filters_noisy_codex_model_refresh(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "repo-assistant.log"
    stderr = "\n".join(
        [
            "2026-09-28T08:57:23Z ERROR codex_models_manager::manager: "
            "failed to refresh available models: unknown variant `max`; body: huge",
            "actionable stderr",
        ]
    )

    stderr_path = _EXAMPLE._write_external_agent_stderr(stderr, log_file)

    assert stderr_path is not None
    text = stderr_path.read_text(encoding="utf-8")
    assert "[omitted 1 known noisy Codex model-refresh stderr line(s)]" in text
    assert "actionable stderr" in text
    assert "body: huge" not in text


def test_external_agent_failure_hint_explains_codex_unauthorized() -> None:
    hint = _EXAMPLE._external_agent_failure_hint(
        "unexpected status 401 Unauthorized: Missing bearer or basic authentication "
        "in header, url: https://api.openai.com/v1/responses"
    )

    assert hint is not None
    assert "Codex CLI reached OpenAI" in hint
    assert "CODEX_COMMAND" in hint


def test_external_agent_failure_hint_explains_codex_collab_failure() -> None:
    hint = _EXAMPLE._external_agent_failure_hint("collab_tool_call")

    assert hint is not None
    assert "external Codex CLI" in hint
    assert "repo-assistant provider-native delegation" in hint


def test_cli_preserves_raw_codex_jsonl_in_transcript_only(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    raw_jsonl = '{"type":"final_answer","content":"transcript answer"}\n'

    def fake_run(*args, **kwargs):
        return _EXAMPLE.subprocess.CompletedProcess(args[0], 0, raw_jsonl, "")

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    log_file = tmp_path / "codex.log"

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
                "--log-file",
                str(log_file),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    transcript = log_file.read_text(encoding="utf-8")
    assert "transcript answer" in output
    assert "=== External agent raw JSONL ===" not in output
    assert "=== External agent raw JSONL ===" in transcript
    assert raw_jsonl.strip() in transcript


def test_cli_can_use_codex_output_last_message_file(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    def fake_run(*args, **kwargs):
        output_index = args[0].index("--output-last-message") + 1
        Path(args[0][output_index]).write_text("last-message answer", encoding="utf-8")
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            '{"type":"turn.completed"}\n',
            "",
        )

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    output_file = tmp_path / "codex" / "last.txt"

    assert (
        main(
            [
                "--mode",
                "ask",
                "Review this repository.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--skip-prompt-review",
                "--codex-output-last-message",
                str(output_file),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_output_last_message:" in output
    assert "last-message answer" in output
    assert output_file.read_text(encoding="utf-8") == "last-message answer"
