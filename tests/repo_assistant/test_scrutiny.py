"""Repo-assistant scrutiny regression contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore
from ai_provider.scrutiny import (
    UNPARSEABLE_VERDICT,
    parse_response_scrutiny_report_lenient,
)

from .support import (
    _EXAMPLE,
    main,
    parse_response_scrutiny_report,
)


@pytest.mark.parametrize(
    "verdict,score", [("**pass**", "**8**"), ("`pass`", "`8`"), ("pass**", "8**"), ("pass", "8/10")]
)
def test_scrutiny_accepts_markdown_emphasis_on_control_values(verdict, score):
    text = (
        f"VERDICT: {verdict}\nSCORE: {score}\nSTRENGTHS: validated\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: review\nREVISED_RESPONSE: report validated"
    )
    result = parse_response_scrutiny_report(text)
    assert result.verdict == "pass" and result.score == 8


@pytest.mark.parametrize("score", ["8/100", "11/10", "8.5/10", "8/10 extra"])
def test_scrutiny_rejects_invalid_score_scales(score):
    text = (
        f"VERDICT: pass\nSCORE: {score}\nSTRENGTHS: validated\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: review\nREVISED_RESPONSE: report validated"
    )
    with pytest.raises(ValueError):
        parse_response_scrutiny_report(text)


@pytest.mark.parametrize("prefix", ["", "### "])
def test_scrutiny_accepts_standalone_bold_sections_preserving_raw_text(prefix):
    text = (
        "**VERDICT:** needs_revision\n**SCORE:** 4/10\n"
        f"{prefix}**STRENGTHS**  \nVisible tests pass.\n"
        f"{prefix}**ISSUES**\nNo model test execution was observed.\n"
        "**RECOMMENDED_NEXT_ACTION:** Run the required command.\n"
        f"{prefix}**REVISED_RESPONSE**\nNone"
    )
    result = parse_response_scrutiny_report(text)
    assert result.verdict == "needs_revision" and result.score == 4
    assert result.strengths == "Visible tests pass."
    assert result.issues == "No model test execution was observed."
    assert result.revised_response == "None"
    assert result.raw_text == text


@pytest.mark.parametrize("heading", ["STRENGTHS", "Review **STRENGTHS**", "**STRENGTHS** inline"])
def test_colonless_prose_is_not_a_scrutiny_section(heading):
    text = (
        f"VERDICT: pass\nSCORE: 8\n{heading}\nVisible tests pass.\n"
        "ISSUES: None\nRECOMMENDED_NEXT_ACTION: None\nREVISED_RESPONSE: None"
    )
    with pytest.raises(ValueError, match="missing scrutiny heading.*STRENGTHS"):
        parse_response_scrutiny_report(text)


def test_mixed_bold_and_canonical_duplicate_sections_remain_invalid():
    text = (
        "VERDICT: pass\nSCORE: 8\nSTRENGTHS: Tests pass.\n"
        "**STRENGTHS**\nDuplicate.\nISSUES: None\n"
        "RECOMMENDED_NEXT_ACTION: None\nREVISED_RESPONSE: None"
    )
    with pytest.raises(ValueError, match="duplicate scrutiny heading: STRENGTHS"):
        parse_response_scrutiny_report(text)


@pytest.mark.parametrize("orchestrated", [False, True])
@pytest.mark.parametrize("scrutiny_policy", ["advisory", "required"])
def test_cli_can_scrutinize_completed_response(
    capsys, monkeypatch, tmp_path: Path, orchestrated: bool, scrutiny_policy: str
) -> None:
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as ProviderBackendLocation,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Investigate the next action for this repository.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    primary = replace(
        prepared,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "primary answer"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    scrutiny = replace(
        primary,
        response=AIResponse(
            message=AIMessage(
                MessageRole.ASSISTANT,
                "\n".join(
                    [
                        "VERDICT: needs_revision",
                        "SCORE: 4",
                        "STRENGTHS: names the relevant command",
                        "ISSUES: generic answer",
                        "RECOMMENDED_NEXT_ACTION: revise the answer",
                        "REVISED_RESPONSE:",
                        "Use the canonical command and inspect its logs.",
                    ]
                ),
            ),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    calls: list[tuple[str, bool, str | None]] = []
    run_db = tmp_path / "repo-assistant-runs.sqlite3"

    def fake_run(prompt, profile, catalog, **kwargs):
        calls.append((prompt, kwargs["execute"], kwargs.get("system_prompt")))
        return primary if len(calls) == 1 else scrutiny

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_run)
    monkeypatch.setattr(
        "ai_agent.run_tracking.run_validation_commands",
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
                "Investigate the next action for this repository.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--scrutinize-response",
                "--scrutiny-policy",
                scrutiny_policy,
                "--away-minutes",
                "30",
                "--away-run-db",
                str(run_db),
            ]
            + (["--orchestrated"] if orchestrated else [])
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "## **SUMMARY**" in output
    assert "### Agent report" in output
    assert "primary answer" in output
    assert "=== Response scrutiny ===" in output
    assert "VERDICT: needs_revision" in output
    assert "scrutiny_verdict: needs_revision" in output
    assert "scrutiny_score: 4" in output
    assert "scrutiny_status: completed" in output
    assert "execution_status: completed_with_scrutiny_findings" in output
    closeout = output.rsplit("## **SUMMARY**", 1)[1]
    assert "#### Reviewer issues\ngeneric answer" in closeout
    assert "#### Reviewer next action\nrevise the answer" in closeout
    assert "Reviewer-proposed revision (not applied or independently verified)" in closeout
    if scrutiny_policy == "required":
        # ADR-066 keeps the blocking behaviour available on request.
        assert "completion=not_established" in closeout
        assert "### Agent report — draft with unresolved scrutiny\nprimary answer" in closeout
        assert "Agent-reported outcome: primary answer" not in closeout
    else:
        # ADR-066 default: a non-pass verdict advises, it does not gate.
        assert "completion=not_established" not in closeout
        assert "### Scrutiny findings (advisory)" in closeout
        assert "### Agent report\nprimary answer" in closeout
        assert "Agent-reported outcome: primary answer" in closeout
    assert len(calls) == 2
    assert calls[1][1] is True
    assert "Candidate assistant response:\nprimary answer" in calls[1][0]
    assert calls[1][2] == _EXAMPLE._RESPONSE_SCRUTINY_SYSTEM_PROMPT
    if not orchestrated:
        return
    run_id = next(
        line.removeprefix("away_run_id: ")
        for line in output.splitlines()
        if line.startswith("away_run_id: ")
    )
    store = SQLiteOrchestratedRunStore(run_db)
    run_record = store.get_run(run_id)
    assert run_record is not None
    assert run_record.status == "completed"
    assert run_record.execution_status == "completed_with_scrutiny_findings"
    stage_by_name = {record.name: record for record in store.list_stages(run_id)}
    assert stage_by_name["scrutiny"].status == "completed"
    assert stage_by_name["scrutiny"].started_at_utc is not None
    assert stage_by_name["scrutiny"].completed_at_utc is not None
    assert stage_by_name["scrutiny"].details == {
        "route_policy": "derived_local_cheap",
        "score": 4,
        "verdict": "needs_revision",
        "issues": "generic answer",
        "next_action": "revise the answer",
        "revised_response": "Use the canonical command and inspect its logs.",
    }


def test_parse_response_scrutiny_report_validates_required_shape() -> None:
    report = parse_response_scrutiny_report(
        "\n".join(
            [
                "### **Verdict:** PASS",
                "### **SCORE:** 8",
                "### **STRENGTHS:**",
                "Grounded.",
                "### **ISSUES:**",
                "None.",
                "### **RECOMMENDED NEXT ACTION:** Keep answer.",
                "### **REVISED RESPONSE:**",
                "Original answer is acceptable.",
            ]
        )
    )

    assert report.verdict == "pass"
    assert report.score == 8
    assert report.strengths == "Grounded."
    assert report.issues == "None."
    assert report.revised_response == "Original answer is acceptable."


def test_parse_response_scrutiny_report_accepts_fenced_json_object() -> None:
    report = parse_response_scrutiny_report(
        """```json
{
  "VERDICT": "pass",
  "SCORE": 9,
  "STRENGTHS": ["names concrete files"],
  "ISSUES": ["needs one more validation step"],
  "RECOMMENDED_NEXT_ACTION": [{"type": "run_command", "command": "pytest"}],
  "REVISED_RESPONSE": null
}
```"""
    )

    assert report.verdict == "pass"
    assert report.score == 9
    assert "names concrete files" in report.strengths
    assert "run_command" in report.recommended_next_action
    assert report.revised_response == ""


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("VERDICT: pass\nSCORE: 5", "missing scrutiny heading"),
        (
            "\n".join(
                [
                    "VERDICT: maybe",
                    "SCORE: 5",
                    "STRENGTHS:",
                    "ISSUES:",
                    "RECOMMENDED_NEXT_ACTION:",
                    "REVISED_RESPONSE:",
                ]
            ),
            "invalid scrutiny verdict",
        ),
        (
            "\n".join(
                [
                    "VERDICT: pass",
                    "SCORE: 11",
                    "STRENGTHS:",
                    "ISSUES:",
                    "RECOMMENDED_NEXT_ACTION:",
                    "REVISED_RESPONSE:",
                ]
            ),
            "scrutiny score out of range",
        ),
    ],
)
def test_parse_response_scrutiny_report_rejects_invalid_reports(
    content: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_response_scrutiny_report(content)


def test_cli_marks_malformed_scrutiny_as_scrutiny_error(capsys, monkeypatch) -> None:
    from dataclasses import replace

    from ai_provider import (
        AIMessage,
        AIResponse,
        BackendInfo,
        MessageRole,
    )
    from ai_provider import (
        BackendLocation as ProviderBackendLocation,
    )

    catalog = _EXAMPLE.load_model_catalog(
        Path("packages/ai_orchestrator/examples/model_catalog.toml")
    )
    prepared = _EXAMPLE.run_coding_prompt(
        "Investigate the next action for this repository.",
        _EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog,
    )
    primary = replace(
        prepared,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "primary answer"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    scrutiny = replace(
        primary,
        response=AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, "VERDICT: pass\nSCORE: 8"),
            backend=BackendInfo(
                provider="ollama",
                model="qwen2.5-coder:14b",
                location=ProviderBackendLocation.LOCAL,
            ),
        ),
    )
    calls = 0
    profiles = []

    def fake_run(prompt, profile, catalog, **kwargs):
        nonlocal calls
        calls += 1
        profiles.append(profile)
        return primary if calls == 1 else scrutiny

    monkeypatch.setattr(_EXAMPLE, "run_coding_prompt", fake_run)

    assert (
        main(
            [
                "--mode",
                "ask",
                "Investigate the next action for this repository.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--scrutinize-response",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "scrutiny_status: invalid" in output
    assert "scrutiny_failure_reason: missing scrutiny heading" in output
    assert "execution_status: completed_with_scrutiny_errors" in output
    closeout = output.rsplit("## **SUMMARY**", 1)[1]
    assert "completion=not_established" in closeout
    assert "#### Review failure\nmissing scrutiny heading" in closeout
    assert "### Agent report — draft with unresolved scrutiny\nprimary answer" in closeout
    assert profiles[1].privacy_class is _EXAMPLE.OrchestratorPrivacyClass.LOCAL_ONLY
    assert profiles[1].cost_policy_tier is _EXAMPLE.CostPolicyTier.LOCAL_ONLY
    assert profiles[1].user_backend_override is None
    assert profiles[1].user_model_override is None


def test_scrutiny_requires_executing_ask_or_review() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "ask", "Review code.", "--scrutinize-response"])

    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Review code.", "--execute", "--scrutinize-response"])


def test_lenient_parse_is_silent_on_a_well_formed_report() -> None:
    text = (
        "VERDICT: pass\nSCORE: 8\nSTRENGTHS: grounded\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: None\nREVISED_RESPONSE: None"
    )
    report = parse_response_scrutiny_report_lenient(text)

    assert report.verdict == "pass"
    assert report.score == 8
    assert report.format_issues == ()


def test_lenient_parse_keeps_the_findings_of_a_partly_malformed_report() -> None:
    """A missing heading must not throw away a review that did reach a verdict."""

    text = "VERDICT: needs_revision\nSCORE: 4\nISSUES: generic answer"
    report = parse_response_scrutiny_report_lenient(text)

    assert report.verdict == "needs_revision"
    assert report.issues == "generic answer"
    assert any("missing heading" in issue for issue in report.format_issues)
    assert any("REVISED_RESPONSE" in issue for issue in report.format_issues)


def test_lenient_parse_never_turns_a_format_problem_into_a_quality_verdict() -> None:
    """Unreadable output reports UNPARSEABLE_VERDICT, never pass/fail or a score."""

    report = parse_response_scrutiny_report_lenient("Looks fine to me, no notes.")

    assert report.verdict == UNPARSEABLE_VERDICT
    assert report.verdict not in {"pass", "needs_revision", "fail"}
    assert report.score is None
    assert report.format_issues


def test_lenient_parse_reports_no_score_rather_than_inventing_a_zero() -> None:
    text = (
        "VERDICT: pass\nSTRENGTHS: grounded\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: None\nREVISED_RESPONSE: None"
    )
    report = parse_response_scrutiny_report_lenient(text)

    assert report.verdict == "pass"
    assert report.score is None
    assert any("SCORE" in issue for issue in report.format_issues)


def test_lenient_parse_keeps_an_out_of_range_score_out_of_the_report() -> None:
    text = (
        "VERDICT: pass\nSCORE: 42\nSTRENGTHS: grounded\nISSUES: none\n"
        "RECOMMENDED_NEXT_ACTION: None\nREVISED_RESPONSE: None"
    )
    report = parse_response_scrutiny_report_lenient(text)

    assert report.verdict == "pass"
    assert report.score is None
    assert any("out of range" in issue for issue in report.format_issues)


def test_lenient_parse_survives_a_duplicated_heading() -> None:
    text = (
        "VERDICT: fail\nSCORE: 2\nSTRENGTHS: a\nSTRENGTHS: b\nISSUES: c\n"
        "RECOMMENDED_NEXT_ACTION: d\nREVISED_RESPONSE: None"
    )
    report = parse_response_scrutiny_report_lenient(text)

    assert report.verdict == "fail"
    assert report.score == 2
    assert report.format_issues


def test_read_only_scrutiny_retains_bounded_observations_and_execution_status():
    from argparse import Namespace

    from ai_agent.contracts import ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence

    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=(
                ToolResult(
                    "run_command", "refused command", is_error=True, metadata={"executed": False}
                ),
                ToolResult(
                    "read_file", "def merge_spans(spans): ...", metadata={"path": "span_union.py"}
                ),
                ToolResult("git_diff", "observed diff"),
                ToolResult(
                    "run_command", "Ran 7 tests\nOK", metadata={"executed": True, "exit_code": 0}
                ),
            )
        )
    )
    assert "def merge_spans" in evidence and "observed diff" in evidence
    assert '"executed": false' in evidence and "is_error=True" in evidence
    assert '"exit_code": 0' in evidence and "Ran 7 tests\nOK" in evidence


def test_scrutiny_tool_receipts_are_bounded_and_not_claimed_when_missing():
    from argparse import Namespace

    from ai_agent.contracts import ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence

    assert "No native" in _observed_tool_evidence(Namespace())
    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=tuple(
                ToolResult("read_file", f"receipt-{index}\n" + "x" * 4000) for index in range(20)
            )
        )
    )
    assert len(evidence) <= 12_000
    assert "receipt-0\n" not in evidence
    assert "receipt-19\n" in evidence
    assert "truncated" in evidence and "omitted" in evidence


def test_scrutiny_evidence_keeps_latest_validation_and_diffs_when_older_reads_fill_budget():
    from argparse import Namespace

    from ai_agent.contracts import ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence

    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=(
                *(ToolResult("read_file", f"old-snapshot-{i}\n" + "x" * 4000) for i in range(12)),
                ToolResult(
                    "edit_file", "corrected the expectation", metadata={"path": "test_source.py"}
                ),
                ToolResult(
                    "run_command", "LATEST VALIDATION: Ran 8 tests\nOK", metadata={"exit_code": 0}
                ),
                ToolResult("git_diff", "LATEST DIFF: corrected expectation"),
                ToolResult("git_status", "LATEST STATUS"),
            )
        )
    )
    assert len(evidence) <= 12_000
    assert (
        "LATEST VALIDATION" in evidence
        and "LATEST DIFF" in evidence
        and "LATEST STATUS" in evidence
    )
    assert "corrected the expectation" in evidence
    assert (
        evidence.index("LATEST VALIDATION")
        < evidence.index("LATEST DIFF")
        < evidence.index("LATEST STATUS")
    )


def test_long_tool_output_retains_terminal_result_with_explicit_middle_omission():
    from argparse import Namespace

    from ai_agent.contracts import ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence

    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=(
                ToolResult("run_command", "COMMAND START\n" + "x" * 5000 + "\nRan 9 tests\nOK"),
            )
        )
    )
    assert "COMMAND START" in evidence and "Ran 9 tests\nOK" in evidence
    assert "middle omitted" in evidence and len(evidence) <= 12_000


def test_semantic_receipt_metadata_is_bounded_and_excludes_unrelated_fields():
    from argparse import Namespace

    from ai_agent.contracts import ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence

    files = [f"changed_{index}.py" for index in range(32)]
    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=(
                ToolResult(
                    "rename_preview",
                    "Preview only",
                    metadata={
                        "files": files,
                        "applied": False,
                    },
                ),
                ToolResult(
                    "rename_apply",
                    "Partially applied; reconcile remaining files",
                    is_error=True,
                    metadata={
                        "applied": [
                            {"path": name, "sha256": str(index) * 64, "unrelated": "EXCLUDED_VALUE"}
                            for index, name in enumerate(files)
                        ]
                    },
                ),
            )
        )
    )
    assert '"applied": false' in evidence
    assert '"files_omitted": 24' in evidence
    assert '"applied_files_omitted": 24' in evidence
    assert "changed_0.py" in evidence and "changed_31.py" not in evidence
    assert "EXCLUDED_VALUE" not in evidence
    assert "is_error=True" in evidence and "Partially applied" in evidence
    assert len(evidence) <= 12_000


def test_runtime_receipt_survives_later_large_reads_with_recent_validation(tmp_path):
    import sys
    from argparse import Namespace

    from ai_agent.contracts import ToolCall, ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence
    from ai_agent.tools.base import ToolContext
    from ai_agent.tools.python_runtime import PythonRuntimeTool

    runtime = PythonRuntimeTool().run(ToolCall("python_runtime", {}), ToolContext(tmp_path))
    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=(
                runtime,
                *(ToolResult("read_file", f"later-read-{i}\n" + "x" * 4000) for i in range(20)),
                ToolResult("run_command", "LATEST: 1 passed", metadata={"exit_code": 0}),
            )
        )
    )
    assert "Tool: python_runtime" in evidence
    assert sys.version.split()[0] in evidence
    assert "workspace_venv_active" in evidence
    assert "LATEST: 1 passed" in evidence
    assert evidence.index("Tool: python_runtime") < evidence.index("LATEST: 1 passed")
    assert len(evidence) <= 12_000


def test_public_fetch_and_runtime_provenance_survive_later_read_volume(tmp_path):
    import hashlib
    from argparse import Namespace

    from ai_agent.contracts import ToolCall, ToolResult
    from ai_agent.scrutiny_workflow import _observed_tool_evidence
    from ai_agent.tools.base import ToolContext
    from ai_agent.tools.python_runtime import PythonRuntimeTool
    from ai_agent.tools.research import FetchURLTool
    from ai_agent.tools.research_http import FetchedSource

    body = b"Public documentation example."
    url = "https://docs.python.org/3.14/library/json.html"
    receipt = {
        "requested_url": url,
        "final_url": url,
        "http_status": 200,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes_retained": len(body),
        "truncated": False,
    }
    context = ToolContext(tmp_path)
    runtime = PythonRuntimeTool().run(ToolCall("python_runtime", {}), context)
    fetched = FetchURLTool(
        lambda *args: None,
        fetcher=lambda _: FetchedSource(body, "text/plain", "utf-8", receipt),
    ).run(ToolCall("fetch_url", {"url": url}), context)
    assert not fetched.is_error
    evidence = _observed_tool_evidence(
        Namespace(
            _scrutiny_tool_results=(
                runtime,
                fetched,
                ToolResult("fetch_url", "PRIVATE GUARD REFUSAL", is_error=True),
                *(ToolResult("read_file", "later data " + "x" * 4000) for _ in range(20)),
                ToolResult("run_command", "LATEST VALIDATION"),
            )
        )
    )
    assert "Tool: python_runtime" in evidence and "Tool: fetch_url" in evidence
    assert url in evidence and receipt["sha256"] in evidence
    assert "PRIVATE GUARD REFUSAL" in evidence
    assert '"http_status": 200' in evidence and '"truncated": false' in evidence
    assert evidence.index("Tool: python_runtime") < evidence.index("Tool: fetch_url")
    assert evidence.index("Tool: fetch_url") < evidence.index("LATEST VALIDATION")
    assert len(evidence) <= 12_000


@pytest.mark.parametrize(
    "candidate", ["Observed the interpreter.", "Execution status: my own claim."]
)
def test_scrutiny_separates_candidate_from_host_status_and_retains_runtime(tmp_path, candidate):
    import sys
    import time
    from argparse import Namespace
    from unittest.mock import Mock

    from ai_agent.contracts import ToolCall
    from ai_agent.scrutiny_workflow import run_orchestrated_scrutiny
    from ai_agent.tools.base import ToolContext
    from ai_agent.tools.python_runtime import PythonRuntimeTool
    from ai_provider.repair_state import workspace_fingerprints

    from .support import _implementation_scrutiny_result

    runtime = PythonRuntimeTool().run(ToolCall("python_runtime", {}), ToolContext(tmp_path))
    args = Namespace(
        prompt="Report runtime and expected negative diagnostics.",
        timeout_seconds=5,
        start_ollama=False,
        ollama_command="ollama",
        ollama_startup_timeout_seconds=5,
        ollama_log_file=None,
        ollama_profile=None,
        _scrutiny_tool_results=(runtime,),
    )
    tracker = Mock(
        initial_workspace=workspace_fingerprints(tmp_path), deadline=time.perf_counter() + 30
    )
    requests = []

    def review(prompt, *a, **kwargs):
        requests.append((prompt, kwargs["system_prompt"]))
        return _implementation_scrutiny_result()

    run_orchestrated_scrutiny(
        args=args,
        tracker=tracker,
        repo_root=tmp_path,
        profile=_EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog=(),
        validation_stage=None,
        assistant_response_text=candidate,
        execution_status="completed_with_tool_errors",
        deadline=None,
        coding_runner=Mock(side_effect=review),
    )
    prompt, system = requests[0]
    response = prompt.split("Candidate assistant response:\n", 1)[1]
    assistant = response.split(
        "\n\nScrutinize the candidate response using the required report format.", 1
    )[0]
    host = response.split("# Host-observed execution evidence", 1)[1]
    assert assistant.strip() == candidate
    assert "Execution status: completed_with_tool_errors" in host
    assert "Tool: python_runtime" in host and sys.version.split()[0] in host
    assert "not authored by the assistant" in host
    assert "nonzero tool receipt" in system


@pytest.mark.parametrize("baseline", ["unchanged", "changed", "unavailable"])
def test_scrutiny_distinguishes_existing_git_diff_from_current_invocation_changes(
    tmp_path, baseline
):
    import time
    from argparse import Namespace
    from unittest.mock import Mock

    from ai_agent.contracts import ToolResult
    from ai_agent.scrutiny_workflow import run_orchestrated_scrutiny
    from ai_provider.repair_state import workspace_fingerprints

    from .support import _implementation_scrutiny_result

    source = tmp_path / "already_edited.py"
    source.write_text("earlier coding result\n")
    initial = None if baseline == "unavailable" else workspace_fingerprints(tmp_path)
    if baseline == "changed":
        source.write_text("new edit during this invocation\n")
    args = Namespace(
        prompt="Review the existing uncommitted change read-only.",
        timeout_seconds=5,
        start_ollama=False,
        ollama_command="ollama",
        ollama_startup_timeout_seconds=5,
        ollama_log_file=None,
        ollama_profile=None,
        _scrutiny_tool_results=(
            ToolResult("git_diff", "Existing Git diff: earlier coding result"),
            ToolResult("run_command", "11 passed", metadata={"exit_code": 0}),
        ),
    )
    tracker = Mock(
        initial_workspace=initial,
        deadline=time.perf_counter() + 30,
        start_stage=lambda *a, **kw: None,
        complete_stage=lambda *a, **kw: None,
    )
    requests = []

    def review(prompt, *a, **kwargs):
        requests.append((prompt, kwargs["system_prompt"]))
        return _implementation_scrutiny_result()

    run_orchestrated_scrutiny(
        args=args,
        tracker=tracker,
        repo_root=tmp_path,
        profile=_EXAMPLE.coding_task_profile(model_override="qwen2.5-coder:14b"),
        catalog=(),
        validation_stage=None,
        assistant_response_text="Inspected the existing change; no write tools used.",
        execution_status="completed",
        deadline=None,
        coding_runner=Mock(side_effect=review),
    )
    prompt, system = requests[0]
    assert "relative to this invocation's start" in prompt
    assert "Git diff/status do not establish when or by whom a change was made" in prompt
    assert "do not establish that runtime bookkeeping was untouched" in prompt
    assert "Existing Git diff: earlier coding result" in prompt and "11 passed" in prompt
    assert "current execution attempt" in prompt
    assert "read-only request can inspect earlier uncommitted changes" in system
    assert "No network tools does not mean" in system
    assert "Delivery contract: Agent narrative describes repository/tool actions" in system
    assert "None means unknown" in system
    assert "Scope does not excuse incorrect technical claims" in system
    assert "Flag unsupported broader claims" in " ".join(system.split())
    if baseline == "unchanged":
        assert "No fingerprint differences observed" in prompt
    elif baseline == "changed":
        assert "Observed changed/deleted paths:\nalready_edited.py" in prompt
        assert "No fingerprint differences observed" not in prompt
    else:
        assert (
            "Start snapshot unavailable; current-invocation change attribution is unknown" in prompt
        )
        assert "No fingerprint differences observed" not in prompt


@pytest.mark.parametrize("verdict", ["pass", "needs_revision"])
def test_old_review_cannot_certify_changed_input_after_incomplete_repair(verdict):
    from ai_provider.closeout import format_cli_closeout

    output = format_cli_closeout(
        response_text="Earlier report claims tests passed.",
        status="ready",
        execution_status="completed_with_tool_errors",
        scrutiny_details={"verdict": verdict, "input_changed_since_review": True},
        scrutiny_policy="advisory",
        validation_details={"validation_status": "not_run", "results": []},
    )
    assert "completion=not_established" in output
    assert "workspace changed during an incomplete repair" in output
    assert "Agent-reported outcome:" not in output
    assert "### Agent report — draft" in output
