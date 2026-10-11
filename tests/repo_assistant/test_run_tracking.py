"""Durable stage receipts and bounded foreground execution contracts."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from ai_agent import run_tracking
from ai_agent.repo_assistant_args import build_argument_parser
from ai_agent.validation import ValidationCommandResult
from ai_orchestrator.models import TaskProfile
from ai_orchestrator.orchestrator import OrchestrationResult, OrchestrationStatus
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore


def test_tracker_and_record_cannot_extend_outer_execution_deadline(tmp_path, monkeypatch):
    args = _args(tmp_path)
    args.away_minutes = 2
    args.execute = True
    args._execution_deadline = 70.0
    monkeypatch.setattr("ai_agent.run_tracking.time.perf_counter", lambda: 10.0)
    tracker, _ = run_tracking.OrchestratedRunTracker.create(
        args=args, repo_root=tmp_path, orchestration=_orchestration(), prompt=args.prompt
    )
    assert tracker.deadline == 70.0
    assert tracker.run_record.budget_seconds == 60.0


def _args(tmp_path: Path):
    return build_argument_parser().parse_args(
        [
            "task",
            "--mode",
            "implement",
            "--away-minutes",
            "10",
            "--away-run-db",
            str(tmp_path / "runs.sqlite3"),
            "--validation-command",
            "pytest -q",
        ]
    )


def _orchestration():
    return OrchestrationResult(
        original_prompt="task",
        profile=TaskProfile(),
        status=OrchestrationStatus.MODEL_SELECTION_FAILED,
        prompt_judge=None,
        recommendation=None,
        execution_plan=None,
    )


def _tracker(tmp_path: Path):
    args = _args(tmp_path)
    tracker, stages = run_tracking.OrchestratedRunTracker.create(
        args=args,
        repo_root=tmp_path,
        orchestration=_orchestration(),
        prompt="task",
        progress_callback=lambda _: None,
    )
    assert len(stages) == len(run_tracking.ORCHESTRATED_STAGE_PLAN)
    return args, tracker


@pytest.mark.parametrize(
    "budget", [0, -1, float("nan"), float("inf"), -float("inf"), True, "10", 10**400]
)
def test_invalid_plan_budget_has_no_persistence_side_effects(tmp_path: Path, budget: Any):
    args = _args(tmp_path)
    args.away_minutes = budget
    with pytest.raises(ValueError, match="finite positive"):
        run_tracking.persist_orchestrated_run_plan(
            args=args, repo_root=tmp_path, orchestration=_orchestration(), prompt="task"
        )
    assert not Path(args.away_run_db).exists()


@pytest.mark.parametrize("budget", [0, -1, float("nan"), float("inf"), True])
def test_invalid_record_budget_does_not_start_run(tmp_path: Path, budget: Any):
    args, tracker = _tracker(tmp_path)
    store = SQLiteOrchestratedRunStore(Path(args.away_run_db))
    with pytest.raises(ValueError, match="finite positive"):
        run_tracking.OrchestratedRunTracker(
            store=store, run_record=replace(tracker.run_record, budget_seconds=budget)
        )
    persisted = store.get_run(tracker.run_record.run_id)
    assert persisted is not None
    assert persisted.status == "planned"


def test_plan_budget_is_derived_from_persisted_record(tmp_path: Path, capsys):
    args, tracker = _tracker(tmp_path)
    record = replace(tracker.run_record, budget_seconds=120)
    run_tracking.print_orchestrated_stage_plan(
        args=args, orchestration=_orchestration(), run_record=record
    )
    output = capsys.readouterr().out
    assert "away_plan_budget_minutes: 2\n" in output
    assert "away_plan_budget_seconds: 120\n" in output


def test_expired_budget_prevents_validation_process(tmp_path: Path, monkeypatch):
    args, tracker = _tracker(tmp_path)
    tracker.deadline = 1
    monkeypatch.setattr(run_tracking.time, "perf_counter", lambda: 2)
    monkeypatch.setattr(
        run_tracking,
        "run_validation_commands",
        lambda *a, **kw: pytest.fail("expired budget launched validation"),
    )
    stage = tracker.record_validation_stage(
        args=args, repo_root=tmp_path, execution_status="completed"
    )
    assert stage.status == "timeout"
    assert stage.details is not None
    assert stage.details["validation_status"] == "timeout"
    assert stage.details["results"] == []


@pytest.mark.parametrize("execution_status,skip", [("failed", False), ("completed", True)])
def test_skipped_validation_never_launches_checks(
    tmp_path: Path, monkeypatch, execution_status: str, skip: bool
):
    args, tracker = _tracker(tmp_path)
    args.skip_validation = skip
    monkeypatch.setattr(
        run_tracking,
        "run_validation_commands",
        lambda *a, **kw: pytest.fail("skipped validation launched checks"),
    )
    stage = tracker.record_validation_stage(
        args=args, repo_root=tmp_path, execution_status=execution_status
    )
    assert stage.status == "skipped"
    assert stage.details is not None
    assert stage.details["validation_status"] == "not_run"


def test_actual_failure_overrides_assistant_claims_in_handoff(tmp_path: Path, monkeypatch):
    args, tracker = _tracker(tmp_path)
    monkeypatch.setattr(
        run_tracking,
        "run_validation_commands",
        lambda *a, **kw: (
            ValidationCommandResult(
                command="pytest -q",
                status="failed",
                returncode=1,
                elapsed_seconds=0.1,
                stdout_preview="1 failed",
                stderr_preview="",
            ),
        ),
    )
    monkeypatch.setattr(run_tracking, "git_status_short", lambda _: (" M app.py",))
    stage = tracker.record_validation_stage(
        args=args, repo_root=tmp_path, execution_status="completed"
    )
    handoff = tracker.record_final_handoff_stage(
        execution_status="completed",
        validation_stage=stage,
        repo_root=tmp_path,
        assistant_response_text="All tests passed",
        final_answer_text="Done",
    )
    assert handoff.details is not None
    assert handoff.details["blockers"] == "validation failed"
    assert handoff.details["changed_files"] == [" M app.py"]
    persisted = SQLiteOrchestratedRunStore(Path(args.away_run_db)).list_stages(
        tracker.run_record.run_id
    )
    validation = next(item for item in persisted if item.name == "validation")
    assert validation.status == "failed"
    assert validation.details is not None
    results = validation.details["results"]
    assert isinstance(results, list)
    assert results[0]["returncode"] == 1


def test_validation_timeout_uses_remaining_run_budget(tmp_path: Path, monkeypatch):
    args, tracker = _tracker(tmp_path)
    args.validation_command = ["pytest -q", "ruff check ."]
    tracker.deadline = 200
    monkeypatch.setattr(run_tracking.time, "perf_counter", lambda: 10)
    captured = {}

    def execute(commands, **kwargs):
        captured.update(kwargs)
        return tuple(
            ValidationCommandResult(
                command=command,
                status="passed",
                returncode=0,
                elapsed_seconds=0,
                stdout_preview="",
                stderr_preview="",
            )
            for command in commands
        )

    monkeypatch.setattr(run_tracking, "run_validation_commands", execute)
    stage = tracker.record_validation_stage(
        args=args, repo_root=tmp_path, execution_status="completed"
    )
    assert stage.status == "completed"
    assert 0 < captured["timeout_seconds"] < 95


def test_missing_validation_receipt_is_explicit_in_handoff(tmp_path: Path, monkeypatch):
    _, tracker = _tracker(tmp_path)
    tracker.scrutiny_status = "pass"
    monkeypatch.setattr(run_tracking, "git_status_short", lambda _: ())
    handoff = tracker.record_final_handoff_stage(
        execution_status="completed",
        validation_stage=None,
        repo_root=tmp_path,
        assistant_response_text="Tests passed",
    )
    assert handoff.details is not None
    assert handoff.details["validation_status"] == "not_recorded"
    risks, next_action = handoff.details["risks"], handoff.details["next_action"]
    assert isinstance(risks, str) and isinstance(next_action, str)
    assert "validation not recorded" in risks
    assert "run deterministic validation" in next_action


@pytest.mark.parametrize("status", ["failed", "timeout"])
def test_stage_failure_cannot_be_hidden_by_missing_optional_details(tmp_path: Path, status: str):
    _, tracker = _tracker(tmp_path)
    from ai_provider.orchestrated_runs import OrchestratedStageRecord

    stage = OrchestratedStageRecord(
        tracker.run_record.run_id, 5, "validation", "local", status, "validate"
    )
    assert run_tracking.execution_status_with_validation_stage("completed", stage) == (
        "completed_with_validation_errors"
    )
