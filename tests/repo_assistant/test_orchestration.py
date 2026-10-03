"""Repo-assistant orchestration regression contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

from .support import (
    _EXAMPLE,
    _implementation_scrutiny_result,
    main,
)


def test_cli_away_minutes_sets_visible_foreground_budget(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Work on the next repository task.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--away-minutes",
                "60",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "away_budget_minutes: 60" in output
    assert "away_budget_seconds: 3600" in output
    assert "away_timeout_seconds: 3600" in output
    assert "external_agent_timeout_mode: inactivity" in output
    assert "external_agent_inactivity_timeout_seconds: 3600" in output


def test_cli_orchestrated_plan_prints_stage_plan_without_provider(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("orchestrated plan mode must not contact a provider")

    monkeypatch.setattr(_EXAMPLE, "create_chat_client", fail_if_called)
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    assert (
        main(
            [
                "--mode",
                "plan",
                "Implement the next CLI stabilization slice.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--away-minutes",
                "60",
                "--orchestrated",
                "--approval-policy",
                "trusted_local",
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "away_orchestrated: enabled" in output
    assert "away_plan_mode: plan" in output
    assert "away_plan_budget_minutes: 60" in output
    assert "away_plan_budget_seconds: 3600" in output
    assert "away_plan_execution: not_started" in output
    assert "away_plan_skip_reason: plan mode never contacts a provider" in output
    assert f"away_run_db: {run_db}" in output
    assert "away_run_id: " in output
    assert "away_run_status: planned" in output
    assert "away_run_stage_records: 8" in output
    assert "away_plan_primary_provider: ollama" in output
    assert "away_plan_primary_model: qwen2.5-coder:14b" in output
    assert "away_plan_auxiliary_route_policy: derived_local_cheap" in output
    assert "away_plan_external_writes: disabled" in output
    assert "away_plan_approval_policy: trusted_local" in output
    assert 'away_plan_validation_commands_json: ["python -m pytest -q"]' in output
    assert "away_plan_max_repair_cycles: 3" in output
    assert "away_stage: prompt_review route=deterministic/local status=planned" in output
    assert "away_stage: planning route=primary status=planned" in output
    assert "away_stage: auxiliary_panel route=derived_local_cheap status=planned" in output
    assert "away_stage: implementation route=primary status=planned" in output
    assert "away_stage: validation route=deterministic/local status=planned" in output
    assert "away_stage: scrutiny route=derived_local_cheap status=planned" in output
    assert "away_stage: repair route=policy_bounded status=planned" in output
    assert "away_stage: final_handoff route=deterministic/local status=planned" in output
    assert "execution_status: planned" in output

    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    run_record = store.get_run(run_id)
    assert run_record is not None
    assert run_record.mode == "plan"
    assert run_record.budget_seconds == 3600
    assert run_record.approval_policy == "trusted_local"
    assert run_record.primary_provider == "ollama"
    assert run_record.primary_model == "qwen2.5-coder:14b"
    assert run_record.status == "planned"
    stage_records = store.list_stages(run_id)
    assert [record.name for record in stage_records] == [
        "prompt_review",
        "planning",
        "auxiliary_panel",
        "implementation",
        "validation",
        "scrutiny",
        "repair",
        "final_handoff",
    ]
    assert all(record.status == "planned" for record in stage_records)


def test_auxiliary_panel_uses_local_cheap_route_with_fake_client(monkeypatch) -> None:
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    captured = {}

    def start_server(base_url, **kwargs):
        captured["startup"] = kwargs

    monkeypatch.setattr("ai_provider.coding_assist.ensure_ollama_server", start_server)

    class FakeClient:
        def __init__(self, config) -> None:
            self.backend = BackendInfo(
                provider=config.provider.value,
                model=config.model,
                location=BackendLocation.LOCAL,
            )

        def complete(self, request):
            captured["request"] = request
            return AIResponse(
                message=AIMessage(MessageRole.ASSISTANT, "check tests and decision boundaries"),
                backend=self.backend,
            )

        def stream(self, request):
            raise NotImplementedError

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    parent_profile = _EXAMPLE.coding_task_profile(
        privacy_class=_EXAMPLE.OrchestratorPrivacyClass.EXTERNAL_ALLOWED,
        provider_override="openai",
        model_override="gpt-5.5",
    )
    events: list[str] = []

    result = _EXAMPLE.run_auxiliary_panel(
        "Implement the next CLI slice.",
        parent_profile,
        catalog,
        client_factory=FakeClient,
        start_ollama=True,
        ollama_command="custom-ollama",
        ollama_startup_timeout_seconds=7.0,
        ollama_log_path=Path("auxiliary-ollama.log"),
        progress_callback=events.append,
    )

    assert result.status == "completed"
    assert captured["startup"]["command"] == "custom-ollama"
    assert captured["startup"]["startup_timeout_seconds"] == 7.0
    assert captured["startup"]["log_path"] == Path("auxiliary-ollama.log")
    assert result.provider == "ollama"
    assert result.model is not None
    assert result.response_text == "check tests and decision boundaries"
    assert captured["request"].privacy_class == _EXAMPLE.ProviderPrivacyClass.LOCAL_ONLY
    assert "auxiliary reviewer" in captured["request"].messages[-1].content
    assert any(event.startswith("auxiliary_panel_activity: model_request -") for event in events)


def test_cli_orchestrated_implement_updates_stage_statuses(
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
    native_response = SimpleNamespace(
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "native done"),
            backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
        ),
        tool_results=(),
    )
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
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(
            status="completed",
            route_id="ollama-qwen2.5-coder:14b",
            provider="ollama",
            model="qwen2.5-coder:14b",
            response_text="auxiliary done",
        ),
    )
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_response)
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
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "=== Auxiliary panel ===" in output
    assert "auxiliary done" in output
    assert "away_stage_status: auxiliary_panel status=running" in output
    assert "away_stage_status: auxiliary_panel status=completed" in output
    assert "away_stage_status: implementation status=running" in output
    assert "away_stage_status: implementation status=completed" in output
    assert "away_stage_status: validation status=running" in output
    assert "away_stage_status: validation status=completed" in output
    assert "away_stage_status: final_handoff status=running" in output
    assert "away_stage_status: final_handoff status=completed" in output
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
    assert stage_by_name["auxiliary_panel"].status == "completed"
    assert stage_by_name["auxiliary_panel"].started_at_utc is not None
    assert stage_by_name["auxiliary_panel"].completed_at_utc is not None
    assert stage_by_name["auxiliary_panel"].details == {
        "failure_reason": "",
        "model": "qwen2.5-coder:14b",
        "provider": "ollama",
        "route_id": "ollama-qwen2.5-coder:14b",
        "route_policy": "derived_local_cheap",
    }
    assert stage_by_name["implementation"].status == "completed"
    assert stage_by_name["scrutiny"].status == "completed"
    scrutiny_details = stage_by_name["scrutiny"].details
    assert scrutiny_details is not None and scrutiny_details["verdict"] == "pass"
    assert stage_by_name["implementation"].started_at_utc is not None
    assert stage_by_name["implementation"].completed_at_utc is not None
    assert stage_by_name["validation"].status == "completed"
    assert stage_by_name["validation"].started_at_utc is not None
    assert stage_by_name["validation"].completed_at_utc is not None
    validation_details = stage_by_name["validation"].details
    assert validation_details is not None
    assert validation_details["execution_status_before_validation"] == "completed"
    assert validation_details["validation_status"] == "passed"
    assert validation_details["commands"] == ["python -m pytest -q"]
    validation_results = validation_details["results"]
    assert isinstance(validation_results, list)
    assert isinstance(validation_results[0], dict)
    assert validation_results[0]["status"] == "passed"
    assert stage_by_name["final_handoff"].status == "completed"
    assert stage_by_name["final_handoff"].started_at_utc is not None
    assert stage_by_name["final_handoff"].completed_at_utc is not None
    final_handoff_details = stage_by_name["final_handoff"].details
    assert final_handoff_details is not None
    assert final_handoff_details["execution_status"] == "completed"
    assert final_handoff_details["validation_status"] == "passed"
    assert final_handoff_details["assistant_response_available"] is True
    assert final_handoff_details["final_answer_available"] is False
    assert isinstance(final_handoff_details["changed_files"], list)
    assert final_handoff_details["next_action"] == "review the assistant response"


def test_cli_orchestrated_auxiliary_failure_affects_final_status(
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
    native_response = SimpleNamespace(
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "native done"),
            backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
        ),
        tool_results=(),
    )
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(
            status="failed",
            failure_reason="local model unavailable",
        ),
    )
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_response)
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
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "auxiliary_panel_status: failed" in output
    assert "execution_status: completed_with_auxiliary_errors" in output
    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    run_record = store.get_run(run_id)
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.execution_status == "completed_with_auxiliary_errors"
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    assert stage_by_name["auxiliary_panel"].status == "failed"
    assert stage_by_name["implementation"].status == "completed"


def test_cli_orchestrated_validation_failure_affects_final_status(
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
    native_response = SimpleNamespace(
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "native done"),
            backend=BackendInfo("ollama", "test", BackendLocation.LOCAL),
        ),
        tool_results=(),
    )
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        _EXAMPLE,
        "run_auxiliary_panel",
        lambda *args, **kwargs: _EXAMPLE.AuxiliaryPanelResult(status="completed"),
    )
    monkeypatch.setattr(_EXAMPLE, "_run_native_agent", lambda *args, **kwargs: native_response)
    monkeypatch.setattr(
        _EXAMPLE,
        "_run_validation_commands",
        lambda *args, **kwargs: (
            _EXAMPLE.ValidationCommandResult(
                command="python -m pytest -q",
                returncode=1,
                status="failed",
                elapsed_seconds=0.01,
                stdout_preview="FAILED tests/test_example.py::test_failure",
                failure_reason="validation command exited with code 1",
            ),
        ),
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
                "--away-run-db",
                str(run_db),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "away_stage_status: validation status=failed" in output
    assert "final_execution_status: completed_with_validation_errors" in output
    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    run_record = store.get_run(run_id)
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.execution_status == "completed_with_validation_errors"
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    assert stage_by_name["validation"].status == "failed"
    validation_details = stage_by_name["validation"].details
    assert validation_details is not None
    assert validation_details["validation_status"] == "failed"
    final_handoff_details = stage_by_name["final_handoff"].details
    assert final_handoff_details is not None
    assert final_handoff_details["blockers"] == "validation failed"


def test_cli_orchestrated_requires_away_minutes() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Work.", "--orchestrated"])


def test_cli_away_minutes_preserves_explicit_timeout(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Work on the next repository task.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--away-minutes",
                "60",
                "--timeout-seconds",
                "120",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "away_budget_seconds: 3600" in output
    assert "away_timeout_seconds: 120" in output
    assert "external_agent_inactivity_timeout_seconds: 120" in output


def test_cli_rejects_invalid_away_minutes() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Work.", "--away-minutes", "0"])
