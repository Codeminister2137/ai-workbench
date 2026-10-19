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


@pytest.mark.parametrize("verdict", ["needs_revision", "fail"])
def test_unresolved_scrutiny_qualifies_claims_without_replacing_the_draft(verdict: str) -> None:
    draft = "I independently verified the supplied hash."
    output = format_cli_closeout(
        response_text=draft,
        status="ready",
        execution_status="completed_with_tool_errors",
        validation_details={"validation_status": "passed"},
        scrutiny_details={
            "verdict": verdict,
            "issues": "No hash verification was observed.",
            "next_action": "Verify it or retract that claim.",
            "revised_response": "The supplied hash remains unverified.",
        },
    )

    assert output.count(draft) == 1
    assert output.endswith(f"### Agent report — draft with unresolved scrutiny\n{draft}\n")
    assert "#### Reviewer issues\nNo hash verification was observed." in output
    assert "#### Reviewer next action\nVerify it or retract that claim." in output
    assert "Reviewer-proposed revision (not applied or independently verified)" in output
    assert "completion=not_established" in output
    assert "execution_status=completed_with_tool_errors" in output
    changed = next(line for line in output.splitlines() if line.startswith("- Changed:"))
    assert draft not in changed and "unresolved scrutiny" in changed
    assert "- Validated: passed (Recorded checks only;" in output


@pytest.mark.parametrize(
    "details",
    [
        {"failure_reason": "Reviewer timed out."},
        {"failure_reason": "Invalid reviewer response."},
        {"skip_reason": "Budget exhausted before scrutiny."},
    ],
)
def test_unavailable_review_does_not_look_like_success(details: dict[str, object]) -> None:
    output = format_cli_closeout(
        response_text="Draft answer.",
        status="ready",
        execution_status="completed_with_scrutiny_errors",
        scrutiny_details=details,
    )
    assert "completion=not_established" in output
    assert "The draft below is not an accepted completion report." in output
    assert str(next(iter(details.values()))) in output
    assert "Reviewer-proposed revision" not in output


def test_passing_review_does_not_silently_adopt_a_proposed_rewrite() -> None:
    assert format_cli_closeout(
        response_text="Original answer.",
        status="ready",
        execution_status="completed",
        scrutiny_details={"verdict": "pass", "revised_response": "Reviewer rewrite."},
    ) == format_cli_closeout(
        response_text="Original answer.", status="ready", execution_status="completed"
    )
