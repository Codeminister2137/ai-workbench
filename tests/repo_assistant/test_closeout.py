"""The CLI closeout schema is fixed independently of the selected model."""

import pytest
from ai_provider.closeout import FINAL_RESPONSE_INSTRUCTION, format_cli_closeout


def test_closeout_uses_fixed_schema_and_reports_absent_validation_stage() -> None:
    output = format_cli_closeout(
        response_text="A model-specific final answer.",
        status="ready",
        execution_status="completed",
    )

    assert output.startswith("## **SUMMARY**\n")
    assert (
        "- Changed: Agent-reported outcome: A model-specific final answer. "
        "(workspace changes are not independently attributed by the CLI)." in output
    )
    assert "- Validated: No separate deterministic validation stage recorded." in output
    assert "- Notes: status=ready; execution_status=completed; fallback_attempts=none" in output
    assert "### Agent report\nA model-specific final answer." in output


@pytest.mark.parametrize("response", ["Tool-run pytest: 19 passed.", "All checks passed."])
def test_closeout_distinguishes_agent_checks_from_pipeline_validation(response: str) -> None:
    output = format_cli_closeout(
        response_text=response, status="ready", execution_status="completed"
    )

    validation_line = next(line for line in output.splitlines() if line.startswith("- Validated:"))
    assert validation_line == "- Validated: No separate deterministic validation stage recorded."
    assert "Not run by the CLI" not in validation_line
    assert f"### Agent report\n{response}" in output


def test_closeout_reports_validation_failure_and_fallback_attempts() -> None:
    output = format_cli_closeout(
        response_text=None,
        status="failed",
        execution_status="completed_with_validation_errors",
        validation_details={
            "validation_status": "failed",
            "results": [
                {"command": "pytest -q", "status": "failed"},
                {"command": "ruff check .", "status": "passed"},
            ],
        },
        fallback_attempts=[
            {"route_id": "codex", "status": "usage_limit"},
            {"route_id": "copilot", "status": "finished"},
        ],
        failure_reason="provider failed",
    )

    assert "- Validated: failed (pytest -q: failed; ruff check .: passed)" in output
    assert "- Changed: No final response was captured; no change summary is available." in output
    assert (
        "- Notes: status=failed; execution_status=completed_with_validation_errors; "
        "fallback_attempts=codex:usage_limit, copilot:finished; failure_reason=provider failed"
    ) in output
    assert "### Agent report\nNo final response was captured." in output


def test_final_response_instruction_requires_the_same_schema() -> None:
    assert "## **SUMMARY**" in FINAL_RESPONSE_INSTRUCTION
    assert "- Changed: ..." in FINAL_RESPONSE_INSTRUCTION
    assert "- Validated: ..." in FINAL_RESPONSE_INSTRUCTION
    assert "- Notes: ..." in FINAL_RESPONSE_INSTRUCTION
