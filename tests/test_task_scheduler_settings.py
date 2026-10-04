"""Persisted scheduler settings, v1 compatibility and fixed acceptance execution."""

import json
import sqlite3
import sys

import pytest
from ai_orchestrator.scheduling import ScheduledTaskStatus as Status
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore
from ai_provider.repo_assistant_args import build_argument_parser
from ai_provider.research_acceptance import RESEARCH_ACCEPTANCE_PROMPT
from ai_provider.research_execution import validate_research_arguments
from ai_provider.research_task_settings import ResearchTaskSettings
from ai_provider.task_scheduler import ResearchTask, ResearchTaskStore, main, research_command


def test_v1_migration_preserves_all_lifecycle_states_and_immutable_definitions(tmp_path):
    database = tmp_path / "old.sqlite3"
    SQLiteOrchestratedRunStore(database).initialize()
    with sqlite3.connect(database) as connection:
        for state in Status:
            connection.execute(
                """INSERT INTO scheduled_research_tasks
                (task_id, created_at_utc, updated_at_utc, repo_root, prompt, model,
                 required_seconds, status, exit_code, reason)
                VALUES (?, 'created', 'updated', ?, 'old prompt', 'old model',
                        6600, ?, 7, 'old reason')""",
                (state.value, str(tmp_path), state.value),
            )
        before = connection.execute(
            "SELECT task_id, created_at_utc, updated_at_utc, repo_root, prompt, model, "
            "required_seconds, status, exit_code, reason FROM scheduled_research_tasks"
        ).fetchall()
    migrated = ResearchTaskStore(database)
    assert {task.status for task in migrated.list_tasks()} == set(Status)
    assert all(task.settings == ResearchTaskSettings() for task in migrated.list_tasks())
    assert all(task.task_kind == "research" for task in migrated.list_tasks())
    migrated.initialize()
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT task_id, created_at_utc, updated_at_utc, repo_root, prompt, model, "
                "required_seconds, status, exit_code, reason FROM scheduled_research_tasks"
            ).fetchall()
            == before
        )
        assert {
            row[0]
            for row in connection.execute("SELECT schema_version FROM scheduled_research_tasks")
        } == {2}


@pytest.mark.parametrize(
    "values",
    [
        {"review_policy": "cloud"},
        {"review_mode": "unsupported"},
        {"max_repair_cycles": -2},
        {"max_repair_cycles": True},
        {"review_policy": "quality_first", "review_model": " "},
        {"review_policy": "quality_first", "review_tokenizer_file": 5},
        {"review_policy": "quality_first", "review_output_tokens": 8193},
        {"review_policy": "quality_first", "review_timeout_seconds": float("nan")},
        {"review_policy": "quality_first", "review_timeout_seconds": "300"},
        {"review_model": "qwen3:14b"},
        {"command": "arbitrary shell command"},
    ],
)
def test_invalid_persisted_settings_fail_closed(values):
    with pytest.raises(ValueError):
        ResearchTaskSettings.from_json(json.dumps(values))


def test_planning_roundtrip_preserves_settings_and_resolves_tokenizer_against_repo(
    tmp_path, monkeypatch, capsys
):
    database = tmp_path / "queue.sqlite3"
    monkeypatch.chdir(tmp_path.parent)
    monkeypatch.setattr(
        "ai_provider.task_scheduler.supervise_research",
        lambda *_, **__: pytest.fail("planning must not start a process"),
    )
    assert (
        main(
            [
                "--database",
                str(database),
                "plan",
                "acceptance",
                "--acceptance",
                "--repo-root",
                str(tmp_path),
                "--model",
                "gpt-oss:20b",
                "--required-minutes",
                "110",
                "--research-review-policy",
                "quality_first",
                "--research-review-model",
                "qwen3:14b",
                "--research-review-mode",
                "deliberative",
                "--research-review-output-tokens",
                "8192",
                "--research-review-timeout-seconds",
                "240",
                "--research-review-tokenizer-file",
                "assets/tokenizer.json",
                "--max-repair-cycles",
                "-1",
            ]
        )
        == 0
    )
    task = ResearchTaskStore(database).get_task("acceptance")
    assert task.prompt == RESEARCH_ACCEPTANCE_PROMPT
    assert task.settings == ResearchTaskSettings(
        "quality_first",
        "qwen3:14b",
        "deliberative",
        8192,
        240,
        str(tmp_path / "assets/tokenizer.json"),
        -1,
    )
    parser = build_argument_parser()
    args = parser.parse_args(research_command(task, database)[3:])
    validate_research_arguments(args, tmp_path, parser)
    assert args.research_review_tokenizer_file == tmp_path / "assets/tokenizer.json"
    assert args.max_repair_cycles == -1 and args.max_action_rounds == 20
    assert args.context_budget_chars == 1500 and args.timeout_seconds == 300
    assert args.away_run_db != database
    assert "--start-ollama" not in research_command(task, database)
    assert not (tmp_path / "artifacts").exists()
    assert main(["--database", str(database), "list"]) == 0
    output = capsys.readouterr().out
    assert "acceptance: planned, 110 minutes" in output
    assert "tokenizer" not in output and "qwen3" not in output


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--acceptance", "--prompt", "custom"],
        ["--prompt", "topic", "--research-review-model", "local"],
        ["--prompt", "topic", "--max-repair-cycles", "-2"],
    ],
)
def test_invalid_cli_definition_creates_no_database(tmp_path, extra):
    database = tmp_path / "queue.sqlite3"
    with pytest.raises(SystemExit):
        main(
            [
                "--database",
                str(database),
                "plan",
                "invalid",
                "--model",
                "local",
                "--required-minutes",
                "110",
                *extra,
            ]
        )
    assert not database.exists()


@pytest.mark.parametrize("corruption", ["settings", "schema"])
def test_unknown_contract_prevents_execution_and_preserves_planned_state(tmp_path, corruption):
    database = tmp_path / "queue.sqlite3"
    store = ResearchTaskStore(database)
    store.plan(ResearchTask("task", tmp_path, "Public topic", "local", 60))
    with sqlite3.connect(database) as connection:
        if corruption == "settings":
            connection.execute(
                "UPDATE scheduled_research_tasks SET settings_json = '{\"command\": 1}'"
            )
        else:
            connection.execute("UPDATE scheduled_research_tasks SET schema_version = 99")
    with pytest.raises(SystemExit):
        main(
            [
                "--database",
                str(database),
                "run",
                "task",
                "--start",
                "--local-compute-available",
                "--available-minutes",
                "2",
                "--handoff-minutes",
                "0",
            ]
        )
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT status FROM scheduled_research_tasks").fetchone()[0]
            == "planned"
        )


@pytest.mark.parametrize(
    "missing", [None, "search", "fetch", "write", "refinement", "handoff", "execution"]
)
def test_acceptance_subprocess_postchecks_control_durable_scheduler_success(
    tmp_path, monkeypatch, missing
):
    database = tmp_path / "queue.sqlite3"
    store = ResearchTaskStore(database)
    settings = ResearchTaskSettings(
        "quality_first", "qwen3:14b", "deliberative", max_repair_cycles=-1
    )
    store.plan(
        ResearchTask(
            "acceptance",
            tmp_path,
            RESEARCH_ACCEPTANCE_PROMPT,
            "local",
            10,
            settings=settings,
            task_kind="acceptance",
        )
    )
    store.plan(ResearchTask("waiting", tmp_path, "Public topic", "local", 10))

    def fake_ai_command(task, queue):
        if task.task_kind != "acceptance":
            return [sys.executable, "-c", "raise SystemExit(0)"]
        parser = build_argument_parser()
        args = parser.parse_args(research_command(task, queue)[3:])
        validate_research_arguments(args, task.repo_root, parser)
        evidence = {
            "search_receipts": [] if missing == "search" else [{"query_transmitted": True}],
            "fetch_receipts": [] if missing == "fetch" else [{"url": "one"}, {"url": "two"}],
            "report_receipts": [] if missing == "write" else [{"synthetic": True}],
        }
        refinement = {"research_refinement": {"attempt_count": 0 if missing == "refinement" else 1}}
        handoff_status = "failed" if missing == "handoff" else "completed"
        execution_status = (
            "completed_with_auxiliary_errors" if missing == "execution" else "completed"
        )
        # Run a real child that writes synthetic offline records. It loads no model.
        code = f"""
from pathlib import Path
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore, OrchestratedStagePlanItem
store = SQLiteOrchestratedRunStore(Path({str(args.away_run_db)!r}))
run = store.create_run(repo_root=Path.cwd(), mode='implement', prompt='synthetic smoke',
    budget_seconds=10, approval_policy='trusted_local', primary_route_id=None,
    primary_provider='ollama', primary_model='synthetic', status='completed',
    execution_status={execution_status!r})
store.replace_stage_plan(run.run_id, [OrchestratedStagePlanItem(name, 'local', 'smoke')
    for name in ('implementation', 'repair', 'final_handoff')])
store.complete_stage(run.run_id, 'implementation', details={evidence!r})
store.complete_stage(run.run_id, 'repair', details={refinement!r})
store.complete_stage(run.run_id, 'final_handoff', status={handoff_status!r})
report = Path({str(args.research_report)!r})
report.write_text('Synthetic offline fixture; no model or public fetching occurred.')
"""
        return [sys.executable, "-c", code]

    monkeypatch.setattr("ai_provider.task_scheduler.research_command", fake_ai_command)
    result = main(
        [
            "--database",
            str(database),
            "run",
            "acceptance",
            "waiting",
            "--start",
            "--local-compute-available",
            "--available-minutes",
            "1",
            "--handoff-minutes",
            "0.1",
        ]
    )
    assert result == (0 if missing is None else 1)
    reopened = ResearchTaskStore(database)
    assert reopened.get_task("acceptance").status is (
        Status.COMPLETED if missing is None else Status.FAILED
    )
    assert reopened.get_task("waiting").status is (
        Status.COMPLETED if missing is None else Status.PLANNED
    )
    assert reopened.get_task("acceptance").settings == settings


def test_acceptance_worker_failure_preserves_code_without_postchecks(tmp_path, monkeypatch):
    from ai_provider.task_scheduler import run_research_task

    task = ResearchTask(
        "acceptance", tmp_path, RESEARCH_ACCEPTANCE_PROMPT, "local", 10, task_kind="acceptance"
    )
    monkeypatch.setattr("ai_provider.task_scheduler.supervise_research", lambda *_, **__: 7)
    monkeypatch.setattr(
        "ai_provider.task_scheduler.check_acceptance",
        lambda *_, **__: pytest.fail("failed workers cannot pass acceptance"),
    )
    assert run_research_task(task, tmp_path / "queue.sqlite3", 9.5) == 7
