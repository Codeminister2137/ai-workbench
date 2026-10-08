"""Regression coverage for unattended no-op repairs and grounded local scrutiny."""

import argparse
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from ai_agent import repo_coding_assistant as cli
from ai_agent.repair_workflow import run_orchestrated_repair_loop
from ai_agent.run_tracking import OrchestratedRunTracker
from ai_agent.scrutiny_workflow import run_orchestrated_scrutiny
from ai_orchestrator import load_model_catalog
from ai_orchestrator.repair import repair_progress, review_reserve_seconds
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderError,
)
from ai_provider.coding_assist import CodingAssistResult
from ai_provider.orchestrated_runs import OrchestratedStagePlanItem, SQLiteOrchestratedRunStore
from ai_provider.repair_state import changed_paths, workspace_fingerprints


@pytest.fixture
def run(tmp_path, monkeypatch):
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    record = store.create_run(
        repo_root=tmp_path,
        mode="implement",
        prompt="Write RESEARCH_test.md",
        budget_seconds=600,
        approval_policy="workspace_write",
        primary_route_id="local",
        primary_provider="ollama",
        primary_model="test",
    )
    store.replace_stage_plan(
        record.run_id,
        [
            OrchestratedStagePlanItem(name, "local", "test")
            for name in ("validation", "repair", "scrutiny", "final_handoff")
        ],
    )
    tracker = OrchestratedRunTracker(store=store, run_record=record)
    tracker.begin_run()
    args = argparse.Namespace(
        mode="implement",
        execute=True,
        max_repair_cycles=-1,
        timeout_seconds=60,
        validation_timeout_seconds=30,
        skip_validation=False,
        validation_command=["verify"],
        prompt="Write RESEARCH_test.md",
        start_ollama=True,
        ollama_command="ollama",
        ollama_startup_timeout_seconds=10,
        ollama_log_file=None,
        ollama_profile=None,
    )
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *a, **kw: (
            cli.ValidationCommandResult(
                "verify", 1, "failed", 0.1, stdout_preview="missing research file: RESEARCH_test.md"
            ),
        ),
    )
    validation = tracker.record_validation_stage(
        args=args, repo_root=tmp_path, execution_status="completed"
    )
    return args, tracker, validation, store, tmp_path


def _loop(run, repair, **overrides):
    args, tracker, validation, _, root = run
    return run_orchestrated_repair_loop(
        args=args,
        tracker=tracker,
        repo_root=root,
        execution_status=overrides.get("execution_status", "completed_with_validation_errors"),
        validation_stage=validation,
        original_prompt=args.prompt,
        assistant_response_text="done",
        deadline=overrides.get("deadline"),
        repair_attempt=repair,
    )


def _stage(run, name):
    return next(s for s in run[3].list_stages(run[1].run_record.run_id) if s.name == name)


def _review_result(text: str) -> CodingAssistResult:
    prepared = cli.run_coding_prompt(
        "review",
        cli.coding_task_profile(model_override="qwen2.5-coder:14b"),
        load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml")),
    )
    return replace(
        prepared,
        response=AIResponse(
            AIMessage(MessageRole.ASSISTANT, text),
            BackendInfo("ollama", "qwen2.5-coder:14b", BackendLocation.LOCAL),
        ),
    )


@pytest.mark.parametrize("initial_status", ["completed", "completed_with_validation_errors"])
def test_skipped_revalidation_does_not_erase_existing_validation_failure(run, initial_status):
    run[0].skip_validation = True
    attempts = []

    def repair(prompt, number, timeout):
        attempts.append(number)
        return "completed", "The repair is complete"

    status, validation, _ = _loop(run, repair, execution_status=initial_status)
    assert attempts == [1]
    assert status == "completed_with_validation_errors"
    assert validation is not None and validation.details is not None
    assert validation.details["validation_status"] == "not_run"
    stage = _stage(run, "repair")
    assert stage.status == "skipped"
    assert stage.details["stop_reason"] == "validation_not_run"


def test_disabled_repair_does_not_hide_initial_validation_failure(run):
    run[0].max_repair_cycles = 0
    status, _, _ = _loop(
        run, lambda *a: pytest.fail("disabled repair ran"), execution_status="completed"
    )
    assert status == "completed_with_validation_errors"
    assert _stage(run, "repair").status == "skipped"


@pytest.mark.parametrize("override_deadline", [False, True])
def test_caller_cannot_disable_or_extend_tracker_repair_deadline(
    run, monkeypatch, override_deadline
):
    deadline = run[1].deadline
    monkeypatch.setattr(cli.time, "perf_counter", lambda: deadline)
    status, _, _ = _loop(
        run,
        lambda *a: pytest.fail("expired tracker budget launched a repair"),
        deadline=deadline + 100 if override_deadline else None,
    )
    assert status == "completed_with_validation_errors"
    stage = _stage(run, "repair")
    assert stage.status == "timeout"
    assert stage.details["attempt_count"] == 0


@pytest.mark.parametrize("response", ["Done.", "Ran a tool and checked the report."])
def test_identical_no_op_repairs_stop_even_when_unbounded(run, response):
    status, validation, _ = _loop(run, lambda *a: ("completed", response))
    assert status == "completed_with_validation_errors"
    assert validation is not None and validation.details is not None
    assert validation.details["validation_status"] == "failed"
    stage = _stage(run, "repair")
    assert stage.status == "stalled"
    assert stage.details["attempt_count"] == 2
    assert stage.details["stop_reason"] == "repeated_no_progress"


def test_ignored_report_changes_allow_active_repairs(run, monkeypatch):
    attempts = []

    def repair(prompt, number, timeout):
        attempts.append(number)
        (run[4] / "RESEARCH_test.md").write_text(f"Report revision {number}")
        return "completed", "updated report"

    def validate(*a, **kw):
        return (
            cli.ValidationCommandResult(
                "verify",
                0 if len(attempts) == 4 else 1,
                "passed" if len(attempts) == 4 else "failed",
                0.1,
                stdout_preview="missing research file: RESEARCH_test.md",
            ),
        )

    monkeypatch.setattr("ai_agent.run_tracking.run_validation_commands", validate)
    status, _, _ = _loop(run, repair)
    assert status == "completed"
    assert attempts == [1, 2, 3, 4]
    assert _stage(run, "repair").details["attempts"][0]["progress"] == "state_changed"


def test_changing_validation_evidence_resets_no_progress(run, monkeypatch):
    attempts = []

    def repair(*a):
        attempts.append(1)
        return "completed", "different claim alone is not progress"

    def validate(*a, **kw):
        failure = "new failure" if len(attempts) >= 2 else "missing research file: RESEARCH_test.md"
        return (cli.ValidationCommandResult("verify", 1, "failed", 0.1, stdout_preview=failure),)

    monkeypatch.setattr("ai_agent.run_tracking.run_validation_commands", validate)
    _loop(run, repair)
    assert len(attempts) == 4
    assert _stage(run, "repair").details["attempts"][1]["progress"] == "failure_changed"


def test_timing_noise_does_not_keep_repairs_alive(run, monkeypatch):
    attempts = []

    def repair(*a):
        attempts.append(1)
        return "completed", "done"

    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
        lambda *a, **kw: (
            cli.ValidationCommandResult(
                "verify",
                1,
                "failed",
                len(attempts),
                stdout_preview=(
                    f"missing research file: RESEARCH_test.md\n1 failed in {len(attempts)}.12s"
                ),
            ),
        ),
    )
    _loop(run, repair)
    # First appearance of the failure summary changes evidence; later timings do not.
    assert len(attempts) == 3


def test_logs_and_databases_do_not_count_as_repair_progress(run):
    def repair(*a):
        (run[4] / "logs").mkdir(exist_ok=True)
        (run[4] / "logs" / "activity.txt").write_text(str(a))
        return "completed", "done"

    _loop(run, repair)
    assert _stage(run, "repair").details["attempt_count"] == 2


def test_snapshot_detects_same_size_edits_and_deletion(tmp_path):
    report = tmp_path / "RESEARCH_test.md"
    report.write_text("one")
    before = workspace_fingerprints(tmp_path)
    report.write_text("two")
    after = workspace_fingerprints(tmp_path)
    assert changed_paths(before, after) == ["RESEARCH_test.md"]
    report.unlink()
    assert changed_paths(after, workspace_fingerprints(tmp_path)) == ["RESEARCH_test.md"]


def test_review_budget_stops_repair_before_deadline(run, monkeypatch):
    monkeypatch.setattr(cli.time, "perf_counter", lambda: 950.0)

    def repair(*a):
        raise AssertionError("the last minute is reserved for scrutiny/handoff")

    _loop(run, repair, deadline=1000)
    stage = _stage(run, "repair")
    assert stage.status == "timeout"
    assert stage.details["attempt_count"] == 0
    assert stage.details["stop_reason"] == "review_budget_reserved"


def test_repair_validation_timeout_preserves_review_budget(run, monkeypatch):
    monkeypatch.setattr(cli.time, "perf_counter", lambda: 0)
    run[0].validation_command = ["verify", "verify again"]
    observed = []

    def validate(*a, **kw):
        observed.append(kw["timeout_seconds"])
        return (cli.ValidationCommandResult("verify", 0, "passed", 0.1),)

    monkeypatch.setattr("ai_agent.run_tracking.run_validation_commands", validate)

    def repair(prompt, number, timeout):
        assert timeout == 9.5
        return "completed", "done"

    _loop(run, repair, deadline=80)
    assert observed == [9.5]


def test_failed_repair_does_not_retry_or_claim_validation_pass(run):
    def repair(*a):
        raise ProviderError("native tool JSON is not a tool call")

    status, _, _ = _loop(run, repair)
    assert status == "completed_with_validation_errors"
    assert _stage(run, "repair").details["attempt_count"] == 1
    assert _stage(run, "repair").details["stop_reason"] == "repair_execution_failed"


def test_external_repair_timeout_preserves_run_records(run):
    def repair(*a):
        raise subprocess.TimeoutExpired("codex", 10, output="partial work")

    status, _, _ = _loop(run, repair)
    assert status == "completed_with_validation_errors"
    assert _stage(run, "repair").status == "timeout"
    assert _stage(run, "repair").details["attempt_count"] == 1


def test_initial_validation_does_not_consume_review_reserve(run, monkeypatch):
    monkeypatch.setattr(cli.time, "perf_counter", lambda: run[1].deadline - 50)

    def validate(*a, **kw):
        raise AssertionError("validation must leave the review reserve intact")

    monkeypatch.setattr("ai_agent.run_tracking.run_validation_commands", validate)
    stage = run[1].record_validation_stage(
        args=run[0], repo_root=run[4], execution_status="completed"
    )
    assert stage.status == "timeout"
    assert stage.details["validation_status"] == "timeout"


def test_scrutiny_provider_failure_is_visible(run, monkeypatch):
    def review(*a, **kw):
        raise ProviderError("local reviewer unavailable")

    status = run_orchestrated_scrutiny(
        coding_runner=review,
        args=run[0],
        tracker=run[1],
        repo_root=run[4],
        profile=cli.coding_task_profile(),
        catalog=(),
        validation_stage=run[2],
        assistant_response_text="done",
        execution_status="completed",
        deadline=None,
    )
    assert status == "completed_with_scrutiny_errors"
    assert _stage(run, "scrutiny").details["failure_reason"] == "local reviewer unavailable"


@pytest.mark.parametrize(
    "verdict,expected",
    [
        ("pass", "completed"),
        ("needs_revision", "completed_with_scrutiny_findings"),
        ("fail", "completed_with_scrutiny_findings"),
        ("invalid", "completed_with_scrutiny_errors"),
    ],
)
def test_scrutiny_reviews_artifact_validation_and_claims_locally(
    run, monkeypatch, verdict, expected
):
    (run[4] / "RESEARCH_test.md").write_text("Source-backed report")

    def review(prompt, profile, catalog, **kw):
        assert "Source-backed report" in prompt
        assert "missing research file" in prompt
        assert "claimed work complete" in prompt
        assert profile.privacy_class.value == "local_only"
        assert profile.cost_policy_tier.value == "local_only"
        assert profile.user_model_override is None
        assert kw["start_ollama"] is True
        text = (
            f"VERDICT: {verdict}\nSCORE: 7\nSTRENGTHS: x\nISSUES: y\n"
            "RECOMMENDED_NEXT_ACTION: inspect report\nREVISED_RESPONSE: incomplete"
        )
        return _review_result(text)

    status = run_orchestrated_scrutiny(
        coding_runner=review,
        args=run[0],
        tracker=run[1],
        repo_root=run[4],
        profile=cli.coding_task_profile(model_override="primary"),
        catalog=(),
        validation_stage=run[2],
        assistant_response_text="claimed work complete",
        execution_status="completed",
        deadline=None,
    )
    assert status == expected
    assert _stage(run, "scrutiny").status == ("failed" if verdict == "invalid" else "completed")


def test_scrutiny_cannot_erase_validation_failure(run, monkeypatch):
    text = (
        "VERDICT: pass\nSCORE: 8\nSTRENGTHS: x\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: review\nREVISED_RESPONSE: done"
    )
    assert (
        run_orchestrated_scrutiny(
            coding_runner=lambda *a, **kw: _review_result(text),
            args=run[0],
            tracker=run[1],
            repo_root=run[4],
            profile=cli.coding_task_profile(),
            catalog=(),
            validation_stage=run[2],
            assistant_response_text="done",
            execution_status="completed_with_validation_errors",
            deadline=None,
        )
        == "completed_with_validation_errors"
    )


def test_reusable_scrutiny_uses_explicit_client_without_runtime_access(run):
    run[0].start_ollama = False
    requests = []
    text = (
        "VERDICT: pass\nSCORE: 8\nSTRENGTHS: x\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: review\nREVISED_RESPONSE: done"
    )

    class Client:
        def __init__(self, config):
            self.backend = BackendInfo(config.provider.value, config.model, BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            return AIResponse(AIMessage(MessageRole.ASSISTANT, text), self.backend)

        def stream(self, request):
            raise NotImplementedError

    status = run_orchestrated_scrutiny(
        args=run[0],
        tracker=run[1],
        repo_root=run[4],
        profile=cli.coding_task_profile(),
        catalog=load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml")),
        validation_stage=run[2],
        assistant_response_text="done",
        execution_status="completed_with_validation_errors",
        deadline=None,
        client_factory=Client,
    )
    assert len(requests) == 1
    assert requests[0].privacy_class.value == "local_only"
    assert status == "completed_with_validation_errors"
    assert _stage(run, "scrutiny").details["verdict"] == "pass"


@pytest.mark.parametrize("override_deadline", [False, True])
def test_caller_cannot_disable_or_extend_tracker_scrutiny_deadline(
    run, monkeypatch, override_deadline
):
    deadline = run[1].deadline
    monkeypatch.setattr(cli.time, "perf_counter", lambda: deadline)
    status = run_orchestrated_scrutiny(
        args=run[0],
        tracker=run[1],
        repo_root=run[4],
        profile=cli.coding_task_profile(),
        catalog=(),
        validation_stage=None,
        assistant_response_text="done",
        execution_status="completed",
        deadline=deadline + 100 if override_deadline else None,
        coding_runner=lambda *a, **kw: pytest.fail("expired tracker budget launched scrutiny"),
    )
    assert status == "completed_with_scrutiny_errors"
    assert _stage(run, "scrutiny").status == "skipped"


def test_budget_exhausted_scrutiny_is_recorded_in_handoff(run, monkeypatch):
    monkeypatch.setattr(cli.time, "perf_counter", lambda: 1000)

    def review(*a, **kw):
        raise AssertionError("must not call a provider after budget exhaustion")

    status = run_orchestrated_scrutiny(
        coding_runner=review,
        args=run[0],
        tracker=run[1],
        repo_root=run[4],
        profile=cli.coding_task_profile(),
        catalog=(),
        validation_stage=None,
        assistant_response_text="done",
        execution_status="completed",
        deadline=1000,
    )
    handoff = run[1].record_final_handoff_stage(
        execution_status=status,
        validation_stage=None,
        repo_root=run[4],
        assistant_response_text="done",
    )
    assert status == "completed_with_scrutiny_errors"
    assert _stage(run, "scrutiny").status == "skipped"
    assert "scrutiny not_run" in handoff.details["risks"]
    assert handoff.details["scrutiny_status"] == "not_run"


def test_neutral_policy_and_review_reserve():
    assert repair_progress(state_changed=True, failure_changed=False) == "state_changed"
    assert repair_progress(state_changed=False, failure_changed=True) == "failure_changed"
    assert repair_progress(state_changed=False, failure_changed=False) == "no_progress"
    assert review_reserve_seconds(30) == 3
    assert review_reserve_seconds(10000) == 120
