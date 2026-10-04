import sqlite3
import sys
from pathlib import Path

import pytest
from ai_orchestrator.scheduling import ScheduledTaskStatus as Status
from ai_provider.orchestrated_runs import OrchestratedStagePlanItem, SQLiteOrchestratedRunStore
from ai_provider.repo_assistant_args import build_argument_parser
from ai_provider.research_execution import validate_research_arguments
from ai_provider.task_scheduler import (
    ResearchTask,
    ResearchTaskStore,
    execute_sequence,
    main,
    research_command,
    run_research_task,
)


@pytest.fixture
def store(tmp_path: Path) -> ResearchTaskStore:
    result = ResearchTaskStore(tmp_path / "runs.sqlite3")
    for task_id, duration in (("first", 60), ("long", 120), ("short", 10)):
        result.plan(ResearchTask(task_id, tmp_path, "Public Python research", "qwen3:8b", duration))
    return result


def test_additive_schema_preserves_existing_runs_and_stages(tmp_path: Path) -> None:
    path = tmp_path / "runs.sqlite3"
    original = SQLiteOrchestratedRunStore(path)
    run = original.create_run(
        repo_root=tmp_path,
        mode="implement",
        prompt="existing",
        budget_seconds=180,
        approval_policy="trusted_local",
        primary_route_id=None,
        primary_provider=None,
        primary_model=None,
    )
    stages = original.replace_stage_plan(
        run.run_id, [OrchestratedStagePlanItem("research", "primary", "existing")]
    )
    # Recreate the pre-scheduler schema in this temporary database.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE scheduled_research_tasks")
    store = ResearchTaskStore(path)
    store.plan(ResearchTask("new", tmp_path, "Public research", "local", 120))
    reopened = ResearchTaskStore(path)
    assert reopened.get_run(run.run_id) == run
    assert reopened.list_stages(run.run_id) == stages
    assert reopened.get_task("new").status is Status.PLANNED


def test_claim_is_atomic_and_does_not_resume_running_task(store: ResearchTaskStore) -> None:
    store.transition("first", expected=Status.PLANNED, status=Status.RUNNING)
    other = ResearchTaskStore(store.path)
    with pytest.raises(ValueError, match="no longer planned"):
        other.transition("first", expected=Status.PLANNED, status=Status.RUNNING)
    result = execute_sequence(
        other,
        ["first"],
        explicitly_started=True,
        constraints_satisfied=True,
        available_seconds=100,
        handoff_seconds=10,
        runner=lambda *_: pytest.fail("must not resume"),
    )
    assert result.stopped_at == "first"
    other.transition(
        "first", expected=Status.RUNNING, status=Status.FAILED, reason="Worker stopped"
    )
    with pytest.raises(ValueError, match="Unsupported"):
        other.transition("first", expected=Status.FAILED, status=Status.PLANNED)


def test_elapsed_time_stop_preserves_order_and_planned_waiters(store: ResearchTaskStore) -> None:
    elapsed = [0.0]
    called = []

    def run(task: ResearchTask, database: Path, budget: float) -> int:
        called.append(task.task_id)
        assert database == store.path
        assert budget == 60
        elapsed[0] += 50
        return 0

    result = execute_sequence(
        store,
        ["first", "long", "short"],
        explicitly_started=True,
        constraints_satisfied=True,
        available_seconds=180,
        handoff_seconds=20,
        clock=lambda: elapsed[0],
        runner=run,
    )
    assert result.completed == ("first",)
    assert result.stopped_at == "long"
    assert called == ["first"]
    assert store.get_task("long").status is Status.PLANNED
    assert store.get_task("short").status is Status.PLANNED


@pytest.mark.parametrize("started, constraints", [(False, True), (True, False)])
def test_unauthorized_sequence_does_not_invoke_adapter(store, started, constraints) -> None:
    result = execute_sequence(
        store,
        ["first"],
        explicitly_started=started,
        constraints_satisfied=constraints,
        available_seconds=100,
        handoff_seconds=10,
        runner=lambda *_: pytest.fail("no inference"),
    )
    assert result.stopped_at == "first"
    assert store.get_task("first").status is Status.PLANNED


@pytest.mark.parametrize("code, late", [(124, False), (3, False), (0, True)])
def test_failed_or_overrunning_worker_stops_sequence(store, code, late) -> None:
    elapsed = [0.0]

    def run(*_) -> int:
        elapsed[0] = 61 if late else 1
        return code

    result = execute_sequence(
        store,
        ["first", "short"],
        explicitly_started=True,
        constraints_satisfied=True,
        available_seconds=180,
        handoff_seconds=10,
        clock=lambda: elapsed[0],
        runner=run,
    )
    assert result.stopped_at == "first"
    assert store.get_task("first").status is Status.FAILED
    assert store.get_task("first").exit_code == code
    assert store.get_task("short").status is Status.PLANNED


def test_interruption_is_durable_without_destroying_definition(store) -> None:
    def interrupted(*_) -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_sequence(
            store,
            ["first", "short"],
            explicitly_started=True,
            constraints_satisfied=True,
            available_seconds=100,
            handoff_seconds=10,
            runner=interrupted,
        )
    assert store.get_task("first").status is Status.FAILED
    assert store.get_task("first").prompt == "Public Python research"
    assert store.get_task("short").status is Status.PLANNED


def test_unknown_late_id_preflight_prevents_any_worker(store) -> None:
    with pytest.raises(KeyError):
        execute_sequence(
            store,
            ["first", "absent"],
            explicitly_started=True,
            constraints_satisfied=True,
            available_seconds=100,
            handoff_seconds=10,
            runner=lambda *_: pytest.fail("must preflight"),
        )
    assert store.get_task("first").status is Status.PLANNED


def test_command_fixed_local_free_supervised_research(store) -> None:
    command = research_command(store.get_task("first"), store.path)
    for flag, value in (
        ("--privacy", "local_only"),
        ("--provider", "ollama"),
        ("--cost-policy", "local_only"),
        ("--tool-profile", "research"),
    ):
        assert command[command.index(flag) + 1] == value
    assert "--start-ollama" not in command
    assert "--orchestrated" in command
    assert command[-2:] == ["--", "Public Python research"]


def test_worker_command_passes_real_research_validation_without_side_effects(store) -> None:
    task = store.get_task("first")
    parser = build_argument_parser()
    args = parser.parse_args(research_command(task, store.path)[3:])
    validate_research_arguments(args, task.repo_root, parser)
    assert args.research_report is not None
    assert not (task.repo_root / args.research_report).exists()


def test_report_paths_are_queue_specific_and_do_not_embed_task_ids(tmp_path) -> None:
    task = ResearchTask("../../outside / label", tmp_path, "Public research", "local", 60)
    parser = build_argument_parser()
    first = parser.parse_args(research_command(task, tmp_path / "first.sqlite3")[3:])
    second = parser.parse_args(research_command(task, tmp_path / "second.sqlite3")[3:])
    validate_research_arguments(first, tmp_path, parser)
    assert first.research_report != second.research_report
    assert first.research_report.parts[:2] == ("artifacts", "scheduled-research")
    assert first.research_report.name == "report.md"
    assert len(first.research_report.parent.name) == 64


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout"])
def test_cli_sequence_uses_real_supervised_process_and_persists_result(
    tmp_path, monkeypatch, capsys, outcome
) -> None:
    """Exercise CLI admission, claims, subprocess supervision and durable state without AI."""
    database = tmp_path / "runs.sqlite3"
    prefix = ["--database", str(database)]
    for task_id in ("smoke", "waiting"):
        assert (
            main(
                [
                    *prefix,
                    "plan",
                    task_id,
                    "--prompt",
                    "Public smoke task",
                    "--model",
                    "local",
                    "--required-minutes",
                    "0.05" if outcome == "timeout" else "0.1",
                    "--repo-root",
                    str(tmp_path),
                ]
            )
            == 0
        )

    def worker_command(task, path):
        # Validate the production command before replacing only the AI worker.
        parser = build_argument_parser()
        args = parser.parse_args(research_command(task, path)[3:])
        validate_research_arguments(args, task.repo_root, parser)
        code = "from pathlib import Path; Path('worker-started').write_text('started'); "
        if outcome == "timeout":
            code += "import time; time.sleep(10)"
        else:
            code += f"raise SystemExit({0 if outcome == 'success' else 3})"
        return [sys.executable, "-c", code]

    monkeypatch.setattr("ai_provider.task_scheduler.research_command", worker_command)
    # The local imported function above retains the production builder.
    result = main(
        [
            *prefix,
            "run",
            "smoke",
            "waiting",
            "--start",
            "--local-compute-available",
            "--available-minutes",
            "1",
            "--handoff-minutes",
            "0.1",
        ]
    )
    reopened = ResearchTaskStore(database)
    assert (tmp_path / "worker-started").read_text() == "started"
    if outcome == "success":
        assert result == 0
        assert all(task.status is Status.COMPLETED for task in reopened.list_tasks())
        assert "research_supervisor_status: completed" in capsys.readouterr().out
    else:
        assert result == 1
        assert reopened.get_task("smoke").status is Status.FAILED
        assert reopened.get_task("smoke").exit_code == (124 if outcome == "timeout" else 3)
        assert reopened.get_task("waiting").status is Status.PLANNED


def test_adapter_passes_remaining_allocation_to_existing_supervisor(store, monkeypatch) -> None:
    task = store.get_task("first")
    calls = []

    def supervisor(command, **kwargs):
        calls.append((command, kwargs))
        return 124

    monkeypatch.setattr("ai_provider.task_scheduler.supervise_research", supervisor)
    assert run_research_task(task, store.path, 59.5) == 124
    assert calls == [
        (
            research_command(task, store.path),
            {
                "root": task.repo_root,
                "database": store.path,
                "budget_seconds": 59.5,
            },
        )
    ]


def test_cli_plans_lists_and_defers_without_worker(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "ai_provider.task_scheduler.supervise_research",
        lambda *_, **__: pytest.fail("no providers during planning"),
    )
    prefix = ["--database", str(tmp_path / "runs.sqlite3")]
    assert (
        main(
            [
                *prefix,
                "plan",
                "new",
                "--prompt",
                "Public topic",
                "--model",
                "local",
                "--required-minutes",
                "90",
                "--repo-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert main([*prefix, "list"]) == 0
    assert "new: planned, 90 minutes" in capsys.readouterr().out
    assert main([*prefix, "defer", "new", "--reason", "Owner needs compute"]) == 0
    assert ResearchTaskStore(tmp_path / "runs.sqlite3").get_task("new").status is Status.DEFERRED


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf"), True])
def test_invalid_allocation_rejected(tmp_path, duration) -> None:
    with pytest.raises(ValueError):
        ResearchTask("invalid", tmp_path, "Topic", "local", duration)
