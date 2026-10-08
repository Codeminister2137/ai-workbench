"""Validation behavior is independent from CLI orchestration and model output."""

import subprocess

import pytest
from ai_agent.validation import (
    ValidationCommandResult,
    activity_preview_lines,
    run_validation_commands,
    validation_results_json,
    validation_status,
)


@pytest.mark.parametrize("command", ["", "  ", 'python "unterminated'])
def test_malformed_validation_command_is_reported_without_execution(tmp_path, command):
    def forbidden(*args, **kwargs):
        pytest.fail("Malformed validation launched a process")

    results = run_validation_commands(
        (command,),
        repo_root=tmp_path,
        timeout_seconds=5,
        runner=forbidden,
        progress_callback=lambda _: None,
    )
    assert len(results) == 1
    assert results[0].status == "failed_to_start"
    assert results[0].executable is None
    assert results[0].failure_reason
    assert validation_status(results) == "failed"


@pytest.mark.parametrize("output", [b"partial stdout\xff", "partial stdout", None])
def test_timeout_preserves_available_output(tmp_path, output):
    def timeout(arguments, **kwargs):
        raise subprocess.TimeoutExpired(arguments, 5, output=output, stderr=b"partial stderr")

    results = run_validation_commands(
        ("checker",),
        repo_root=tmp_path,
        timeout_seconds=5,
        runner=timeout,
        progress_callback=lambda _: None,
    )
    result = results[0]
    assert result.status == "timeout"
    assert result.executable == "checker"
    assert result.stderr_preview == "partial stderr"
    assert (
        result.stdout_preview.startswith("partial stdout") if output else not result.stdout_preview
    )
    assert validation_status(results) == "timeout"


@pytest.mark.parametrize("limit", [0, 1, 5, 15, 20, 1500])
def test_output_preview_always_respects_character_budget(limit):
    preview = activity_preview_lines("line\n" * 1000, limit=limit)
    assert len(preview) <= limit
    assert not preview or "truncated" in preview or limit < 15


def test_process_failure_does_not_discard_later_validation_results(tmp_path):
    commands = []
    events = []

    def execute(arguments, **kwargs):
        commands.append(arguments)
        assert kwargs["cwd"] == tmp_path
        assert kwargs.get("shell", False) is False
        if arguments[0] == "missing":
            raise FileNotFoundError("not installed")
        return subprocess.CompletedProcess(
            arguments, 2, stdout="failure evidence", stderr="details"
        )

    results = run_validation_commands(
        ("missing", "checker --flag"),
        repo_root=tmp_path,
        timeout_seconds=5,
        runner=execute,
        progress_callback=events.append,
    )
    assert commands == [["missing"], ["checker", "--flag"]]
    assert [result.status for result in results] == ["failed_to_start", "failed"]
    assert results[1].stdout_preview == "failure evidence"
    assert results[1].returncode == 2
    assert validation_status(results) == "failed"
    assert len(events) == 4


def test_literal_shell_operators_are_never_interpreted(tmp_path):
    received = []

    def execute(arguments, **kwargs):
        received.append(arguments)
        assert kwargs.get("shell", False) is False
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    results = run_validation_commands(
        ("checker ; second-command",),
        repo_root=tmp_path,
        timeout_seconds=5,
        runner=execute,
        progress_callback=lambda _: None,
    )
    assert received == [["checker", ";", "second-command"]]
    assert validation_status(results) == "passed"


def test_validation_metadata_retains_unknown_exit_status_and_execution_evidence():
    result = ValidationCommandResult("checker", None, "timeout", 0.12345, executable="checker")
    metadata = validation_results_json((result,))[0]
    assert metadata["returncode"] is None
    assert metadata["elapsed_seconds"] == 0.123
    assert metadata["executable"] == "checker"
    assert validation_status(()) == "not_run"
