"""Repo-assistant repairs regression contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

from .support import (
    _EXAMPLE,
    _implementation_scrutiny_result,
    main,
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
        _EXAMPLE,
        "_run_validation_commands",
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
            "effective_route_id": "ollama-qwen2-5-coder-14b",
            "fallback_attempts": [
                {"route_id": "ollama-qwen2-5-coder-14b", "status": "finished"},
                {"route_id": "ollama-qwen2-5-coder-14b", "status": "finished"},
            ],
        }
    ]
    final_handoff_details = stage_by_name["final_handoff"].details
    assert final_handoff_details is not None
    assert final_handoff_details["validation_status"] == "passed"
    assert final_handoff_details["blockers"] == ""


def test_cli_orchestrated_external_agent_repair_reruns_validation_until_passed(
    capsys,
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
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(
        _EXAMPLE,
        "_run_validation_commands",
        lambda *args, **kwargs: validation_results.pop(0),
    )

    assert (
        main(
            [
                "--mode",
                "implement",
                "Repair through Codex.",
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
