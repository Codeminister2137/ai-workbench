"""Repo-assistant scrutiny regression contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore

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


def test_cli_can_scrutinize_completed_response(capsys, monkeypatch, tmp_path: Path) -> None:
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
                "ask",
                "Investigate the next action for this repository.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--execute",
                "--scrutinize-response",
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
    assert "## **SUMMARY**" in output
    assert "### Agent report" in output
    assert "primary answer" in output
    assert "=== Response scrutiny ===" in output
    assert "VERDICT: needs_revision" in output
    assert "scrutiny_verdict: needs_revision" in output
    assert "scrutiny_score: 4" in output
    assert "scrutiny_status: completed" in output
    assert "execution_status: completed_with_scrutiny_findings" in output
    assert len(calls) == 2
    assert calls[1][1] is True
    assert "Candidate assistant response:\nprimary answer" in calls[1][0]
    assert calls[1][2] == _EXAMPLE._RESPONSE_SCRUTINY_SYSTEM_PROMPT
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
    assert profiles[1].privacy_class is _EXAMPLE.OrchestratorPrivacyClass.LOCAL_ONLY
    assert profiles[1].cost_policy_tier is _EXAMPLE.CostPolicyTier.LOCAL_ONLY
    assert profiles[1].user_backend_override is None
    assert profiles[1].user_model_override is None


def test_scrutiny_requires_executing_ask_or_review() -> None:
    with pytest.raises(SystemExit):
        main(["--mode", "ask", "Review code.", "--scrutinize-response"])

    with pytest.raises(SystemExit):
        main(["--mode", "plan", "Review code.", "--execute", "--scrutinize-response"])
