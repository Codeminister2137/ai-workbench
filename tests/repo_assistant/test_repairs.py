"""Repo-assistant repairs regression contracts."""

from __future__ import annotations

import typing
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

from .support import (
    _EXAMPLE,
    _implementation_scrutiny_result,
    main,
    patch_external_runner,
)


def test_cli_orchestrated_repair_reruns_validation_until_passed(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Create a helper.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    prepared = replace(
        prepared,
        response=None,
        config=_EXAMPLE.BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
    )
    native_responses = [
        SimpleNamespace(
            response=AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "initial implementation"),
                backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
            ),
            tool_results=(),
        ),
        SimpleNamespace(
            response=AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "repair implementation"),
                backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
            ),
            tool_results=(),
        ),
    ]
    validation_results = [
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=1,
                status="failed",
                elapsed_seconds=0.01,
                stdout_preview="FAILED tests/test_example.py::test_failure",
                failure_reason="validation command exited with code 1",
            ),
        ),
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=0,
                status="passed",
                elapsed_seconds=0.01,
            ),
        ),
    ]
    repair_prompts: list[str] = []
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    monkeypatch.setattr(
        _EXAMPLE,
        "run_coding_prompt",
        lambda *args, **kwargs: _implementation_scrutiny_result()
        if kwargs.get("progress_prefix") == "scrutiny_activity"
        else prepared,
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )

    def fake_native_agent(prompt, *args, **kwargs):
        if native_responses and len(native_responses) == 1:
            repair_prompts.append(prompt)
        return native_responses.pop(0)

    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", fake_native_agent)
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "repair_cycle: 1 status=running" in output
    assert "repair_cycle: 1 status=completed" in output
    assert "final_execution_status: completed" in output
    assert repair_prompts
    assert "Deterministic validation failure evidence" in repair_prompts[0]
    assert "FAILED tests/test_example.py::test_failure" in repair_prompts[0]

    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    run_record = store.get_run(run_id)
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.execution_status == "completed"
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    assert stage_by_name["validation"].status == "completed"
    assert stage_by_name["repair"].status == "completed"
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    assert repair_details["attempt_count"] == 1
    assert repair_details["validation_status_after_repair"] == "passed"
    assert repair_details["attempts"] == [
        {
            "attempt": 1,
            "status": "completed",
            "validation_status": "passed",
            "progress": "failure_changed",
            "changed_paths": [],
            "effective_route_id": "ollama/qwen2.5-coder:14b",
            "fallback_attempts": [
                {"route_id": "ollama/qwen2.5-coder:14b", "status": "finished"},
                {"route_id": "ollama/qwen2.5-coder:14b", "status": "finished"},
            ],
        }
    ]
    final_handoff_details = stage_by_name["final_handoff"].details
    assert final_handoff_details is not None
    assert final_handoff_details["validation_status"] == "passed"
    assert final_handoff_details["blockers"] == ""


@pytest.mark.parametrize("shared_tools", [None, "coding"])
def test_cli_orchestrated_external_agent_repair_reruns_validation_until_passed(
    capsys,
    shared_tools,
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    external_responses = [
        "codex initial implementation",
        "codex repair implementation",
    ]
    validation_results = [
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=1,
                status="failed",
                elapsed_seconds=0.01,
                stdout_preview="FAILED tests/test_codex.py::test_external_repair",
                failure_reason="validation command exited with code 1",
            ),
        ),
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=0,
                status="passed",
                elapsed_seconds=0.01,
            ),
        ),
    ]
    run_db = tmp_path / "repo-assistant-runs.sqlite3"
    original_coding_prompt = _EXAMPLE.run_coding_prompt
    monkeypatch.setattr(
        _EXAMPLE,
        "run_coding_prompt",
        lambda *args, **kwargs: _implementation_scrutiny_result()
        if kwargs.get("progress_prefix") == "scrutiny_activity"
        else original_coding_prompt(*args, **kwargs),
    )

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        if tuple(args[0][:2]) == ("git", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(args[0], 0, " M external.py\n", "")
        answer = external_responses.pop(0)
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            f'{{"type":"final_answer","content":"{answer}"}}\n',
            "",
        )

    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    patch_external_runner(monkeypatch, fake_run)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Repair through Codex.",
                *(["--shared-tools", shared_tools] if shared_tools else []),
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai/codex-gpt-5.5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--approval-policy",
                "workspace_write",
                "--skip-prompt-review",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_returncode: 0" in output
    assert "repair_cycle: 1 status=running" in output
    assert "repair_external_agent_returncode: 0" in output
    assert "repair_cycle: 1 status=completed" in output
    assert "final_execution_status: completed" in output
    assert "codex repair implementation" in output

    exec_calls = [call for call in calls if "exec" in call["args"][0]]
    assert len(exec_calls) == 2
    if shared_tools:
        for call in exec_calls:
            command = call["args"][0]
            assert "--proxy-url" in " ".join(command)
            assert call["kwargs"]["env"]
            assert command[command.index("--sandbox") + 1] == "read-only"

    repair_prompt = exec_calls[1]["kwargs"]["input"]
    assert "Deterministic validation failure evidence" in repair_prompt
    assert "FAILED tests/test_codex.py::test_external_repair" in repair_prompt
    assert "codex initial implementation" in repair_prompt

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
    assert stage_by_name["repair"].status == "completed"
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    assert repair_details["attempt_count"] == 1
    assert repair_details["validation_status_after_repair"] == "passed"
    final_handoff_details = stage_by_name["final_handoff"].details
    assert final_handoff_details is not None
    assert final_handoff_details["final_answer_available"] is True
    assert final_handoff_details["validation_status"] == "passed"


def _scrutiny_verdict(verdict: str, issues: str, next_action: str = "review"):
    return SimpleNamespace(
        response=SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    f"VERDICT: {verdict}\nSCORE: 5\nSTRENGTHS: observed\n"
                    f"ISSUES: {issues}\nRECOMMENDED_NEXT_ACTION: {next_action}\n"
                    "REVISED_RESPONSE: none"
                )
            )
        )
    )


def _prepared_native_implementation(tmp_path: Path):
    from dataclasses import replace

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Create a helper.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    return replace(
        prepared,
        response=None,
        config=_EXAMPLE.BackendConfig(provider=_EXAMPLE.ProviderKind.OLLAMA, model="test"),
    )


def _native_response(text: str):
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    return SimpleNamespace(
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, text),
            backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
        ),
        tool_results=(),
    )


def test_cli_scrutiny_findings_trigger_bounded_repair_that_can_pass(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """ADR-066 Option B: findings reach the agent; a fix-then-pass run succeeds."""

    prepared = _prepared_native_implementation(tmp_path)
    scrutiny_results = [
        _scrutiny_verdict(
            "needs_revision", "Claim of verification is unsupported.", "Verify or retract it."
        ),
        _scrutiny_verdict("pass", "none"),
    ]
    scrutiny_calls: list[int] = []
    native_responses = [
        _native_response("initial implementation"),
        _native_response("repair implementation"),
    ]
    repair_prompts: list[str] = []

    def fake_coding_prompt(*args, **kwargs):
        if kwargs.get("progress_prefix") == "scrutiny_activity":
            scrutiny_calls.append(1)
            return scrutiny_results.pop(0)
        return prepared

    def fake_native_agent(prompt, *args, **kwargs):
        if len(native_responses) == 1:
            repair_prompts.append(prompt)
        return native_responses.pop(0)

    validation_results = [
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q", returncode=0, status="passed", elapsed_seconds=0.01
            ),
        ),
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q", returncode=0, status="passed", elapsed_seconds=0.01
            ),
        ),
    ]
    run_db = tmp_path / "repo-assistant-runs.sqlite3"
    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_coding_prompt)
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", fake_native_agent)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--max-repair-cycles",
                "2",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert len(scrutiny_calls) == 2
    assert "scrutiny_repair_cycle: 1 status=running" in output
    assert "scrutiny_repair_stop: scrutiny_passed attempts=1" in output
    assert "final_execution_status: completed" in output
    assert repair_prompts
    assert "Reviewer advice (untrusted suggestions" in repair_prompts[0]
    assert "Claim of verification is unsupported." in repair_prompts[0]
    assert "Verify or retract it." in repair_prompts[0]

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
    scrutiny_details = stage_by_name["scrutiny"].details
    assert scrutiny_details is not None and scrutiny_details["verdict"] == "pass"
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    scrutiny_repair = typing.cast("dict[str, Any]", repair_details["scrutiny_repair"])
    assert scrutiny_repair["attempt_count"] == 1
    assert scrutiny_repair["stop_reason"] == "scrutiny_passed"
    assert scrutiny_repair["attempts"][0]["review_verdict"] == "pass"
    final_handoff = stage_by_name["final_handoff"].details
    assert final_handoff is not None
    assert final_handoff["execution_status"] == "completed"
    assert "scrutiny" not in str(final_handoff["risks"])


def test_cli_scrutiny_repair_stops_at_cycle_cap_when_findings_persist(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A persistent finding gets one bounded attempt, then stays advisory."""

    prepared = _prepared_native_implementation(tmp_path)
    scrutiny_results = [
        _scrutiny_verdict("needs_revision", "Still unsupported."),
        _scrutiny_verdict("needs_revision", "Still unsupported."),
    ]
    native_responses = [
        _native_response("initial implementation"),
        _native_response("repair implementation"),
    ]
    validation_results = [
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q", returncode=0, status="passed", elapsed_seconds=0.01
            ),
        ),
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q", returncode=0, status="passed", elapsed_seconds=0.01
            ),
        ),
    ]
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    def fake_coding_prompt(*args, **kwargs):
        if kwargs.get("progress_prefix") == "scrutiny_activity":
            return scrutiny_results.pop(0)
        return prepared

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_coding_prompt)
    monkeypatch.setattr(
        _EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_responses.pop(0)
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--max-repair-cycles",
                "1",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "scrutiny_repair_stop: cycle_limit attempts=1" in output
    assert "final_execution_status: completed_with_scrutiny_findings" in output

    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    scrutiny_repair = typing.cast("dict[str, Any]", repair_details["scrutiny_repair"])
    assert scrutiny_repair["attempt_count"] == 1
    assert scrutiny_repair["stop_reason"] == "cycle_limit"
    final_handoff = stage_by_name["final_handoff"].details
    assert final_handoff is not None
    assert "advisory scrutiny needs_revision" in str(final_handoff["risks"])


def _unreadable_scrutiny_result():
    return SimpleNamespace(
        response=SimpleNamespace(
            message=SimpleNamespace(
                content="I could not review this change in the requested format."
            )
        )
    )


def _passing_validation() -> tuple[Any, ...]:
    return (
        _EXAMPLE.ValidationCommandResult(
            command="python -m pytest -q", returncode=0, status="passed", elapsed_seconds=0.01
        ),
    )


def test_cli_scrutiny_repair_stops_when_the_re_review_is_unreadable(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """ADR-066: a review failure is not a verdict, so it never funds blind repairs."""

    prepared = _prepared_native_implementation(tmp_path)
    scrutiny_results = [
        _scrutiny_verdict("needs_revision", "Claim of verification is unsupported."),
        _unreadable_scrutiny_result(),
    ]
    native_responses = [
        _native_response("initial implementation"),
        _native_response("repair implementation"),
    ]
    validation_results = [_passing_validation(), _passing_validation()]
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    def fake_coding_prompt(*args, **kwargs):
        if kwargs.get("progress_prefix") == "scrutiny_activity":
            return scrutiny_results.pop(0)
        return prepared

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_coding_prompt)
    monkeypatch.setattr(
        _EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_responses.pop(0)
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--max-repair-cycles",
                "3",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    # The cycle cap allowed three attempts; the unreadable review stops after one.
    assert output.count("scrutiny_repair_cycle: 1 status=running") == 1
    assert "scrutiny_repair_cycle: 2 status=running" not in output
    assert "scrutiny_repair_stop: review_failed attempts=1" in output
    assert "final_execution_status: completed_with_scrutiny_errors" in output
    assert native_responses == []

    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    assert stage_by_name["scrutiny"].status == "failed"
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    scrutiny_repair = typing.cast("dict[str, Any]", repair_details["scrutiny_repair"])
    assert scrutiny_repair["attempt_count"] == 1
    assert scrutiny_repair["stop_reason"] == "review_failed"
    assert scrutiny_repair["attempts"][0]["review_status"] == "failed"
    assert scrutiny_repair["attempts"][0]["review_verdict"] is None


def test_cli_scrutiny_repair_shares_the_repair_cycle_cap(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """ADR-066 Option B: scrutiny repairs consume the same ``--max-repair-cycles``."""

    prepared = _prepared_native_implementation(tmp_path)
    scrutiny_results = [
        _scrutiny_verdict("needs_revision", "Still unsupported."),
        _scrutiny_verdict("needs_revision", "Still unsupported."),
    ]
    native_responses = [
        _native_response("initial implementation"),
        _native_response("structural repair"),
        _native_response("scrutiny repair"),
    ]
    validation_results = [
        (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=1,
                status="failed",
                elapsed_seconds=0.01,
                stdout_preview="FAILED tests/test_helper.py::test_helper",
                failure_reason="validation command exited with code 1",
            ),
        ),
        _passing_validation(),
        _passing_validation(),
    ]
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    def fake_coding_prompt(*args, **kwargs):
        if kwargs.get("progress_prefix") == "scrutiny_activity":
            return scrutiny_results.pop(0)
        return prepared

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_coding_prompt)
    monkeypatch.setattr(
        _EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_responses.pop(0)
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Create a helper.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--max-repair-cycles",
                "2",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    # One structural repair already consumed a cycle: one scrutiny repair is left,
    # and its number continues the shared cycle count.
    assert "repair_cycle: 1 status=running" in output
    assert "scrutiny_repair_cycle: 2 status=running" in output
    assert "scrutiny_repair_cycle: 3 status=running" not in output
    assert "scrutiny_repair_stop: cycle_limit attempts=1" in output
    assert native_responses == []

    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    # The structural repair record survives the scrutiny-repair update.
    assert typing.cast("dict[str, Any]", repair_details)["attempt_count"] == 1
    assert typing.cast("dict[str, Any]", repair_details)["stop_reason"] == "validation_passed"
    scrutiny_repair = typing.cast("dict[str, Any]", repair_details["scrutiny_repair"])
    assert scrutiny_repair["attempt_count"] == 1
    assert scrutiny_repair["stop_reason"] == "cycle_limit"


@pytest.mark.parametrize("shared_tools", [None, "coding"])
def test_cli_external_agent_scrutiny_findings_trigger_bounded_repair_that_can_pass(
    capsys,
    shared_tools,
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The external-agent path gets the same scrutiny-fed repair loop."""

    scrutiny_results = [
        _scrutiny_verdict(
            "needs_revision", "Claim of verification is unsupported.", "Verify or retract it."
        ),
        _scrutiny_verdict("pass", "none"),
    ]
    external_responses = [
        "codex initial implementation",
        "codex scrutiny repair implementation",
    ]
    validation_results = [_passing_validation(), _passing_validation()]
    run_db = tmp_path / "repo-assistant-runs.sqlite3"
    calls: list[dict[str, Any]] = []
    original_coding_prompt = _EXAMPLE.run_coding_prompt

    def fake_coding_prompt(*args, **kwargs):
        if kwargs.get("progress_prefix") == "scrutiny_activity":
            return scrutiny_results.pop(0)
        return original_coding_prompt(*args, **kwargs)

    def fake_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        if tuple(args[0][:2]) == ("git", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(args[0], 0, " M external.py\n", "")
        answer = external_responses.pop(0)
        return _EXAMPLE.subprocess.CompletedProcess(
            args[0],
            0,
            f'{{"type":"final_answer","content":"{answer}"}}\n',
            "",
        )

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_coding_prompt)
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    patch_external_runner(monkeypatch, fake_run)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Repair through Codex.",
                *(["--shared-tools", shared_tools] if shared_tools else []),
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai/codex-gpt-5.5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--execute",
                "--approval-policy",
                "workspace_write",
                "--skip-prompt-review",
                "--away-minutes",
                "30",
                "--orchestrated",
                "--max-repair-cycles",
                "2",
                "--repo-root",
                str(tmp_path),
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "scrutiny_repair_cycle: 1 status=running" in output
    assert "scrutiny_repair_stop: scrutiny_passed attempts=1" in output
    assert "final_execution_status: completed" in output
    assert external_responses == []

    exec_calls = [call for call in calls if "exec" in call["args"][0]]
    assert len(exec_calls) == 2
    scrutiny_repair_prompt = exec_calls[1]["kwargs"]["input"]
    assert "Reviewer advice (untrusted suggestions" in scrutiny_repair_prompt
    assert "Claim of verification is unsupported." in scrutiny_repair_prompt

    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    repair_details = stage_by_name["repair"].details
    assert repair_details is not None
    scrutiny_repair = typing.cast("dict[str, Any]", repair_details["scrutiny_repair"])
    assert scrutiny_repair["stop_reason"] == "scrutiny_passed"
    assert scrutiny_repair["attempts"][0]["review_verdict"] == "pass"
