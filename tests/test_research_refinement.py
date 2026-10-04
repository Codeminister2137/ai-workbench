"""Research preflight, receipt-grounded review, and continued improvement regressions."""

import argparse
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.tools.base import ToolContext
from ai_provider import ProviderError
from ai_provider import repo_coding_assistant as cli
from ai_provider.orchestrated_runs import OrchestratedStagePlanItem, SQLiteOrchestratedRunStore
from ai_provider.research_execution import ResearchExecution
from ai_provider.research_refinement import run_research_refinement
from test_research_tools import receipt, valid_report


@pytest.fixture
def research_run(tmp_path):
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    record = store.create_run(
        repo_root=tmp_path,
        mode="implement",
        prompt="Research public sources",
        budget_seconds=600,
        approval_policy="trusted_local",
        primary_route_id="local",
        primary_provider="ollama",
        primary_model="test",
    )
    store.replace_stage_plan(
        record.run_id,
        [
            OrchestratedStagePlanItem(name, "local", "research")
            for name in (
                "implementation",
                "auxiliary_panel",
                "validation",
                "repair",
                "scrutiny",
                "final_handoff",
            )
        ],
    )
    tracker = cli.OrchestratedRunTracker(store=store, run_record=record)
    tracker.begin_run()
    tracker.start_stage("implementation")
    research = ResearchExecution(tmp_path, Path("report.md"), store, record.run_id)
    research.record("fetch_receipts", receipt())
    _write(research, valid_report())
    args = argparse.Namespace(
        research_execution=research,
        mode="implement",
        execute=True,
        max_repair_cycles=-1,
        timeout_seconds=60,
        validation_timeout_seconds=30,
        skip_validation=False,
        validation_command=[],
        tool_profile="research",
        prompt="Research public sources",
        start_ollama=False,
        ollama_command="ollama",
        ollama_startup_timeout_seconds=10,
        ollama_log_file=None,
        ollama_profile=None,
    )
    validation = tracker.record_validation_stage(
        args=args, repo_root=tmp_path, execution_status="completed"
    )
    tracker.complete_stage("repair", status="skipped", details={"attempt_count": 0})
    return args, tracker, validation, tmp_path


def _write(research, text):
    return research.registry.execute(
        ToolCall("write_research_report", {"content": text}), ToolContext(research.root)
    )


def _stage(run, name):
    return next(s for s in run[1]._store.list_stages(run[1].run_record.run_id) if s.name == name)


def test_tool_capable_repair_does_not_inline_the_tool_free_review_packet(research_run):
    research = research_run[0].research_execution
    _write(research, valid_report() + "\n" + "Large saved report paragraph. " * 2000)
    context = research.repair_context()
    assert str(research.target) in context
    assert "read_research_report" in context and "write_research_report" in context
    assert context.count("Large saved report paragraph") < 80
    assert "Draft preview truncated: True" in context
    assert "No tools are available" not in context
    assert len(context) < 7500


def test_repair_response_excerpt_preserves_original_requirements():
    task = "Required repository instructions " * 1200 + "FINAL_REQUIREMENT_MARKER"
    prompt = cli._build_orchestrated_repair_prompt(
        original_prompt=task,
        validation_stage=None,
        assistant_response_text="Prior optional answer " * 3000,
        attempt_number=1,
    )
    assert task in prompt
    assert "Prior response excerpt truncated" in prompt
    assert len(prompt) < len(task) + 7500


def _run(run, repair, review=None, deadline=None):
    def passing_review(**kwargs):
        kwargs["tracker"].scrutiny_status = "pass"
        kwargs["tracker"].complete_stage(
            "scrutiny",
            details={
                "verdict": "pass",
                "issues": "none",
                "next_action": "cross-check coverage",
            },
        )
        return kwargs["execution_status"]

    return run_research_refinement(
        args=run[0],
        tracker=run[1],
        repo_root=run[3],
        profile=cli.coding_task_profile(),
        catalog=(),
        validation_stage=run[2],
        assistant_response_text="done",
        execution_status="completed",
        deadline=deadline if deadline is not None else run[1].deadline,
        repair_attempt=repair,
        review=review or passing_review,
    )


def test_passing_structure_and_review_still_trigger_repeated_refinement(research_run):
    seen = []
    research_run[0].max_repair_cycles = 3

    def improve(prompt, number, timeout):
        assert "not a quality verdict" in prompt
        assert "Reviewer advice" in prompt
        assert "Executive summary" in prompt
        assert "Actual current-run fetch receipts" in prompt
        assert "First call read_research_report" in prompt
        assert "Do not merely summarize proposed edits" in prompt
        assert 0 < timeout <= 60
        seen.append(number)
        _write(
            research_run[0].research_execution, valid_report() + f"\nCoverage refinement {number}"
        )
        return "completed", "updated"

    status, validation, _ = _run(research_run, improve)
    assert status == "completed"
    assert validation is not None and validation.details is not None
    assert validation.details["validation_status"] == "passed"
    assert seen == [1, 2, 3]
    history = _stage(research_run, "repair").details["research_refinement"]
    assert history["stop_reason"] == "cycle_limit"
    assert all(a["progress"] == "evidence_changed" for a in history["attempts"])
    assert all(a["response_summary"] == "updated" for a in history["attempts"])


def test_identical_rewrites_and_repeated_fetches_do_not_fill_budget(research_run):
    def noop(*args):
        research = research_run[0].research_execution
        research.record("fetch_receipts", receipt())
        _write(research, valid_report())
        return "completed", "I performed more checks"

    status, _, _ = _run(research_run, noop)
    assert status == "completed"
    history = _stage(research_run, "repair").details["research_refinement"]
    assert history["stop_reason"] == "repeated_no_progress"
    assert history["attempt_count"] == 2


def test_failed_review_is_not_repeated_without_an_artifact_change(research_run):
    calls = []

    def review(**kwargs):
        calls.append(1)
        kwargs["tracker"].scrutiny_status = "failed"
        kwargs["tracker"].complete_stage(
            "scrutiny", status="failed", details={"failure_reason": "provider timeout"}
        )
        return "completed_with_scrutiny_errors"

    status, validation, _ = _run(
        research_run, lambda *a: pytest.fail("No refinement after failed review"), review
    )
    assert calls == [1]
    assert status == "completed_with_scrutiny_errors"
    assert validation is not None and validation.details is not None
    assert validation.details["validation_status"] == "passed"
    assert _stage(research_run, "scrutiny").status == "failed"
    history = _stage(research_run, "repair").details["research_refinement"]
    assert history["stop_reason"] == "review_failed" and history["attempt_count"] == 0


def test_reviewer_findings_feed_primary_and_repaired_artifact_is_reviewed(research_run):
    research_run[0].max_repair_cycles = 1
    observations = []

    def review(**kwargs):
        observations.append(kwargs["args"].research_execution.target.read_text())
        verdict = "needs_revision" if len(observations) == 1 else "pass"
        kwargs["tracker"].complete_stage(
            "scrutiny",
            details={
                "verdict": verdict,
                "issues": "missing cross-check",
                "next_action": "fetch primary docs",
            },
        )
        kwargs["tracker"].scrutiny_status = verdict
        return (
            "completed_with_scrutiny_findings" if verdict != "pass" else kwargs["execution_status"]
        )

    def improve(prompt, *args):
        assert "missing cross-check" in prompt
        _write(research_run[0].research_execution, valid_report() + "\nCross-check documented.")
        return "completed", "fixed"

    assert _run(research_run, improve, review)[0] == "completed"
    assert len(observations) == 2
    assert "Cross-check documented." in observations[-1]


def test_new_source_evidence_resets_progress_but_duplicate_receipts_do_not(research_run):
    research_run[0].max_repair_cycles = 4

    def improve(prompt, number, timeout):
        if number == 2:
            new = copy.copy(receipt())
            new["requested_url"] = new["final_url"] = "https://docs.python.org/3/library/"
            research_run[0].research_execution.record("fetch_receipts", new)
        return "completed", "cross-checked"

    _run(research_run, improve)
    history = _stage(research_run, "repair").details["research_refinement"]
    assert [a["progress"] for a in history["attempts"]] == [
        "no_progress",
        "evidence_changed",
        "no_progress",
        "no_progress",
    ]


def test_reserve_prevents_refinement_but_allows_final_review(research_run, monkeypatch):
    monkeypatch.setattr("ai_provider.research_refinement.time.perf_counter", lambda: 100)
    reviews = []

    def review(**kwargs):
        reviews.append(kwargs["deadline"])
        return kwargs["execution_status"]

    def forbidden(*args):
        pytest.fail("must preserve reserved review time")

    assert _run(research_run, forbidden, review, deadline=150)[0] == "completed"
    assert reviews == [150]
    assert (
        _stage(research_run, "repair").details["research_refinement"]["stop_reason"]
        == "review_budget_reserved"
    )


def test_failed_refinement_preserves_failure_and_history_before_final_review(research_run):
    def fail(*args):
        stage = _stage(research_run, "repair")
        assert stage.status == "running"
        assert stage.details["research_refinement"]["attempts"][0]["status"] == "running"
        raise ProviderError("provider unavailable")

    assert _run(research_run, fail)[0] == "completed_with_refinement_errors"
    assert (
        _stage(research_run, "repair").details["research_refinement"]["stop_reason"]
        == "refinement_execution_failed"
    )


def test_structural_attempts_count_against_shared_cycle_limit(research_run):
    research_run[0].max_repair_cycles = 2
    research_run[1].complete_stage("repair", details={"attempt_count": 2})

    def forbidden(*args):
        pytest.fail("must respect shared repair cycle limit")

    assert _run(research_run, forbidden)[0] == "completed"


def test_research_review_reads_report_and_receipts_without_unrelated_workspace(
    research_run, monkeypatch
):
    args, tracker, validation, root = research_run
    (root / "unrelated.py").write_text("PRIVATE_UNRELATED_DATA")

    def review(prompt, *rest, **kwargs):
        from ai_provider.scrutiny import RESEARCH_SCRUTINY_SYSTEM_PROMPT

        assert kwargs["system_prompt"] == RESEARCH_SCRUTINY_SYSTEM_PROMPT
        assert "Assistant completion summary (claims only, not source evidence)" in prompt
        assert "Candidate report text (model claims to check, not source evidence)" in prompt
        assert prompt.index("Actual current-run fetch receipts") < prompt.index("Executive summary")
        assert "PRIVATE_UNRELATED_DATA" not in prompt
        assert "Actual current-run fetch receipts" in prompt
        assert receipt()["final_url"] in prompt
        assert "No tools are available to this reviewer" in prompt
        assert "never retrieval evidence" in prompt
        assert "Report length is advisory" in prompt
        assert "Include all six mandatory headings in order" in prompt
        assert "Include REVISED_RESPONSE: None when no replacement is warranted" in prompt
        assert "Do not omit a heading because the draft passes or has no issues" in prompt
        assert "Executive summary" in prompt
        assert len(prompt) < 36_000
        return SimpleNamespace(
            response=SimpleNamespace(
                message=SimpleNamespace(
                    content="VERDICT: pass\nSCORE: 8\nSTRENGTHS: adequate\nISSUES: none\n"
                    "RECOMMENDED_NEXT_ACTION: none\nREVISED_RESPONSE: adequate"
                )
            )
        )

    monkeypatch.setattr(cli, "run_coding_prompt", review)
    assert (
        cli._run_orchestrated_scrutiny(
            args=args,
            tracker=tracker,
            repo_root=root,
            profile=cli.coding_task_profile(),
            catalog=(),
            validation_stage=validation,
            assistant_response_text="done" * 20_000,
            execution_status="completed",
            deadline=tracker.deadline,
        )
        == "completed"
    )


@pytest.mark.parametrize(
    "mode,model",
    [
        ("auto", None),
        ("auto", "qwen3:14b"),
        ("direct", "qwen3:14b"),
        ("deliberative", "gpt-oss:20b"),
    ],
)
def test_opt_in_review_selects_and_records_plan_through_actual_call_path(
    research_run, monkeypatch, mode, model
):
    from ai_provider import research_review
    from ai_provider.contracts import AIMessage, AIResponse, FinishReason, MessageRole

    args, tracker, validation, root = research_run
    args.research_review_policy = "quality_first"
    args.research_review_model = model
    args.research_review_mode = mode
    expected_model = model or "qwen3:14b"
    tracker.run_record = cli.replace(tracker.run_record, primary_model="gpt-oss:20b")
    requests = []
    configs = []
    original_client = research_review.ResearchReviewClient

    def inspector(*a, **k):
        architecture = "gptoss" if model == "gpt-oss:20b" else "qwen3"
        return {"capabilities": ["thinking"], "model_info": {"general.architecture": architecture}}

    def client(*a, **k):
        return original_client(*a, **k, model_inspector=inspector)

    monkeypatch.setattr(research_review, "ResearchReviewClient", client)

    def factory(config):
        from ai_provider.contracts import BackendInfo, BackendLocation

        configs.append(config)
        backend = BackendInfo("ollama", config.model, BackendLocation.LOCAL)

        class FakeClient:
            def __init__(self):
                self.backend = backend

            def complete(self, request):
                requests.append(request)
                return AIResponse(
                    AIMessage(
                        MessageRole.ASSISTANT,
                        "VERDICT: pass\nSCORE: 8\nSTRENGTHS: grounded\nISSUES: none\n"
                        "RECOMMENDED_NEXT_ACTION: none\nREVISED_RESPONSE: None",
                    ),
                    backend,
                    finish_reason=FinishReason.STOP,
                )

            def stream(self, request):
                yield from ()

        return FakeClient()

    monkeypatch.setattr(cli, "create_chat_client", factory)
    catalog = cli.load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    assert (
        cli._run_orchestrated_scrutiny(
            args=args,
            tracker=tracker,
            repo_root=root,
            profile=cli.coding_task_profile(),
            catalog=catalog,
            validation_stage=validation,
            assistant_response_text="done",
            execution_status="completed",
            deadline=tracker.deadline,
        )
        == "completed"
    )
    assert len(requests) == 1 and configs[0].model == expected_model
    assert requests[0].max_output_tokens == 4096
    assert requests[0].metadata["ollama_thinking"] == (
        "high" if model == "gpt-oss:20b" else mode != "direct"
    )
    details = _stage(research_run, "scrutiny").details["research_review"]
    assert details["model"] == expected_model and details["reasons"]
    assert details["mode"] == ("deliberative" if mode == "auto" else mode)
    assert details["attempts"][0]["finish_reason"] == "stop"
    assert "Actual current-run fetch receipts" in requests[0].messages[-1].content
    assert "Assistant completion summary" in requests[0].messages[-1].content


def test_opt_in_unsupported_reviewer_is_recorded_as_failure_without_a_call(
    research_run, monkeypatch
):
    args, tracker, validation, root = research_run
    args.research_review_policy = "quality_first"
    args.research_review_model = "deepseek-coder-v2:16b"
    monkeypatch.setattr(
        cli,
        "run_coding_prompt",
        lambda *a, **k: pytest.fail("Unsupported preset must fail before inference"),
    )
    catalog = cli.load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    assert (
        cli._run_orchestrated_scrutiny(
            args=args,
            tracker=tracker,
            repo_root=root,
            profile=cli.coding_task_profile(),
            catalog=catalog,
            validation_stage=validation,
            assistant_response_text="done",
            execution_status="completed",
            deadline=tracker.deadline,
        )
        == "completed_with_scrutiny_errors"
    )
    assert _stage(research_run, "scrutiny").status == "failed"
    assert "failure_reason" in _stage(research_run, "scrutiny").details


def test_opt_in_final_review_reserve_is_used_by_refinement(research_run, monkeypatch):
    args, tracker, _, _ = research_run
    args.research_review_policy = "quality_first"
    tracker.run_record = cli.replace(tracker.run_record, budget_seconds=6600)
    monkeypatch.setattr("ai_provider.research_refinement.time.perf_counter", lambda: 100)
    reviews = []

    def review(**kwargs):
        reviews.append(kwargs["deadline"])
        return kwargs["execution_status"]

    assert (
        _run(
            research_run,
            lambda *a: pytest.fail("reserve excludes refinement"),
            review,
            deadline=350,
        )[0]
        == "completed"
    )
    assert reviews == [350]
    assert (
        _stage(research_run, "repair").details["research_refinement"]["review_reserve_seconds"]
        == 300
    )


def test_failed_refinement_revalidates_partial_report(research_run):
    def fail(*args):
        _write(research_run[0].research_execution, "Partial report after provider failure")
        raise ProviderError("provider unavailable")

    status, validation, _ = _run(research_run, fail)
    assert status == "completed_with_refinement_errors"
    assert validation is not None and validation.details is not None
    assert validation.details["validation_status"] == "failed"


def test_invalid_revision_can_be_repaired_in_next_refinement(research_run):
    research_run[0].max_repair_cycles = 2

    def improve(prompt, number, timeout):
        if number == 1:
            _write(research_run[0].research_execution, "Too short and missing sections")
        else:
            assert "missing required section" in prompt
            _write(research_run[0].research_execution, valid_report())
        return "completed", "revised"

    status, validation, _ = _run(research_run, improve)
    assert status == "completed"
    assert validation is not None and validation.details is not None
    assert validation.details["validation_status"] == "passed"
    history = _stage(research_run, "repair").details["research_refinement"]
    assert [a["validation_status"] for a in history["attempts"]] == ["failed", "passed"]


def test_attempt_deadline_clamps_each_request_and_stops_later_turns(monkeypatch):
    from ai_provider import (
        AIMessage,
        AIRequest,
        AIResponse,
        BackendConfig,
        BackendInfo,
        BackendLocation,
        MessageRole,
        ProviderKind,
    )
    from ai_provider.research_execution import ResearchChatClient

    now = [100.0]
    timeouts = []
    monkeypatch.setattr("ai_provider.research_execution.time.perf_counter", lambda: now[0])

    class Client:
        backend = BackendInfo("ollama", "test", BackendLocation.LOCAL)

        def complete(self, request: AIRequest) -> AIResponse:
            return AIResponse(AIMessage(MessageRole.ASSISTANT, "turn"), self.backend)

        def stream(self, request):
            raise NotImplementedError

    def factory(config):
        timeouts.append(config.timeout_seconds)
        return Client()

    client = ResearchChatClient(
        Client(),
        {},
        deadline=110.0,
        config=BackendConfig(provider=ProviderKind.OLLAMA, model="test", timeout_seconds=60),
        client_factory=factory,
    )
    request = AIRequest(messages=(AIMessage(MessageRole.USER, "refine"),))
    client.complete(request)
    now[0] = 108
    client.complete(request)
    now[0] = 110
    with pytest.raises(ProviderError, match="attempt budget exhausted"):
        client.complete(request)
    assert timeouts == [10, 2]


def test_research_reviewer_requests_sufficient_context_without_native_tools(
    research_run, monkeypatch
):
    from ai_provider import AIMessage, AIRequest, BackendConfig, MessageRole, ProviderKind

    captured = []

    class Client:
        backend = SimpleNamespace()

        def complete(self, request):
            captured.append(request)
            return SimpleNamespace(
                message=SimpleNamespace(content="review", tool_calls=()), tool_calls=()
            )

    monkeypatch.setattr(cli, "create_chat_client", lambda config: Client())

    def review(prompt, *rest, **kwargs):
        client = kwargs["client_factory"](
            BackendConfig(provider=ProviderKind.OLLAMA, model="deepseek-coder-v2:16b")
        )
        client.complete(AIRequest(messages=(AIMessage(MessageRole.USER, prompt),)))
        return SimpleNamespace(
            response=SimpleNamespace(
                message=SimpleNamespace(
                    content="VERDICT: pass\nSCORE: 8\nSTRENGTHS: adequate\nISSUES: none\n"
                    "RECOMMENDED_NEXT_ACTION: none\nREVISED_RESPONSE: adequate"
                )
            )
        )

    monkeypatch.setattr(cli, "run_coding_prompt", review)
    cli._run_orchestrated_scrutiny(
        args=research_run[0],
        tracker=research_run[1],
        repo_root=research_run[3],
        profile=cli.coding_task_profile(),
        catalog=(),
        validation_stage=research_run[2],
        assistant_response_text="done",
        execution_status="completed",
        deadline=None,
    )
    assert captured[0].metadata["ollama_context_length"] == 32768
    assert captured[0].max_output_tokens == 1200
    assert not captured[0].tools


@pytest.mark.parametrize(
    "model,installed_tools",
    [
        ("qwen2.5-coder:14b", True),
        ("gpt-oss:20b", False),
    ],
)
def test_primary_preflight_failure_skips_auxiliary_and_scrutiny(
    tmp_path, monkeypatch, capsys, model, installed_tools
):
    monkeypatch.setattr(
        "ai_provider.research_execution.show_ollama_model",
        lambda *a, **k: {"capabilities": ["tools"] if installed_tools else []},
    )
    monkeypatch.setattr(cli, "is_ollama_server_available", lambda *a: True)

    def forbidden(*args, **kwargs):
        pytest.fail("no model work may precede primary capability/routing preflight")

    monkeypatch.setattr(cli, "run_auxiliary_panel", forbidden)
    monkeypatch.setattr(cli, "_run_native_agent", forbidden)
    monkeypatch.setattr(cli, "_run_orchestrated_scrutiny", forbidden)
    assert (
        cli.main(
            [
                "Research public sources",
                "--mode",
                "implement",
                "--execute",
                "--orchestrated",
                "--away-minutes",
                "5",
                "--tool-profile",
                "research",
                "--research-report",
                "report.md",
                "--privacy",
                "local_only",
                "--cost-policy",
                "local_only",
                "--provider",
                "ollama",
                "--model",
                model,
                "--repo-root",
                str(tmp_path),
                "--approval-policy",
                "trusted_local",
                "--away-run-db",
                str(tmp_path / "runs.sqlite3"),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(tmp_path / "runs.sqlite3")
    stages = {s.name: s for s in store.list_stages(run_id)}
    run = store.get_run(run_id)
    assert run is not None and run.status == "failed"
    assert stages["implementation"].details is not None
    assert stages["implementation"].details["preflight_status"] == "failed"
    for name in ("auxiliary_panel", "scrutiny", "repair", "validation"):
        assert stages[name].status == "skipped"
    assert stages["final_handoff"].status == "failed"
    assert stages["final_handoff"].details is not None
    assert stages["final_handoff"].details["final_answer_available"] is True
    assert not (tmp_path / "report.md").exists()


def test_cli_structural_repair_receives_saved_draft_and_receipts(tmp_path, monkeypatch):
    from ai_provider import AIMessage, AIResponse, BackendInfo, BackendLocation, MessageRole

    catalog = cli.load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
    prepared = cli.run_coding_prompt(
        "Research", cli.coding_task_profile(model_override="gpt-oss:20b"), catalog
    )
    monkeypatch.setattr(cli, "run_coding_prompt", lambda *a, **k: prepared)
    monkeypatch.setattr(
        "ai_provider.research_execution.research_runtime_options", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        cli, "run_auxiliary_panel", lambda *a, **k: cli.AuxiliaryPanelResult(status="completed")
    )

    def review(**kwargs):
        kwargs["tracker"].scrutiny_status = "pass"
        kwargs["tracker"].complete_stage("scrutiny", details={"verdict": "pass"})
        return kwargs["execution_status"]

    monkeypatch.setattr(cli, "_run_orchestrated_scrutiny", review)
    calls = []

    def native(prompt, config, profile, args, root, **kwargs):
        calls.append(prompt)
        research = args.research_execution
        if len(calls) == 1:
            research.record("fetch_receipts", receipt())
            _write(research, "SAVED_DRAFT_REQUIRING_EXTENSION")
        else:
            assert "SAVED_DRAFT_REQUIRING_EXTENSION" in prompt
            assert "Actual current-run fetch receipts" in prompt
            assert "improve substantive analysis" in prompt
            assert "Length alone never requires repair" in prompt
            assert args.research_attempt_deadline is not None
            _write(research, valid_report())
        return SimpleNamespace(
            response=AIResponse(
                AIMessage(MessageRole.ASSISTANT, "saved"),
                BackendInfo("ollama", "gpt-oss:20b", BackendLocation.LOCAL),
            ),
            tool_results=(),
        )

    monkeypatch.setattr(cli, "_run_native_agent", native)
    assert (
        cli.main(
            [
                "Research public sources",
                "--mode",
                "implement",
                "--execute",
                "--orchestrated",
                "--away-minutes",
                "5",
                "--tool-profile",
                "research",
                "--research-report",
                "report.md",
                "--privacy",
                "local_only",
                "--cost-policy",
                "local_only",
                "--provider",
                "ollama",
                "--model",
                "gpt-oss:20b",
                "--repo-root",
                str(tmp_path),
                "--approval-policy",
                "trusted_local",
                "--away-run-db",
                str(tmp_path / "runs.sqlite3"),
                "--max-repair-cycles",
                "1",
            ]
        )
        == 0
    )
    assert len(calls) == 2
