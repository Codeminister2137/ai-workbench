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
@pytest.mark.parametrize("scrutiny_policy", ["advisory", "required"])
def test_scrutiny_findings_qualify_claims_without_replacing_the_draft(
    verdict: str, scrutiny_policy: str
) -> None:
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
        scrutiny_policy=scrutiny_policy,
    )

    assert "#### Reviewer issues\nNo hash verification was observed." in output
    assert "#### Reviewer next action\nVerify it or retract that claim." in output
    assert "Reviewer-proposed revision (not applied or independently verified)" in output
    assert f"scrutiny_policy={scrutiny_policy}" in output
    assert "execution_status=completed_with_tool_errors" in output

    if scrutiny_policy == "required":
        assert output.count(draft) == 1
        assert output.endswith(f"### Agent report — draft with unresolved scrutiny\n{draft}\n")
        assert "completion=not_established" in output
        changed = next(line for line in output.splitlines() if line.startswith("- Changed:"))
        assert draft not in changed and "unresolved scrutiny" in changed
        assert "- Validated: passed (Recorded checks only;" in output
    else:
        # ADR-066 default: findings are shown and do not gate the outcome, so the
        # draft is reported as the outcome rather than withheld as an unaccepted draft.
        assert "completion=not_established" not in output
        assert "### Scrutiny findings (advisory)" in output
        assert output.endswith(f"### Agent report\n{draft}\n")
        assert "Agent-reported outcome: I independently verified the supplied hash." in output


def test_advisory_policy_still_withholds_a_completion_when_the_review_never_ran() -> None:
    """A missing review is missing evidence, not an advisory judgement.

    ADR-066 made non-pass verdicts advisory; it did not make a promised-but-absent
    review look like a completed one.
    """

    output = format_cli_closeout(
        response_text="Draft answer.",
        status="ready",
        execution_status="completed_with_scrutiny_errors",
        scrutiny_details={"failure_reason": "Reviewer timed out."},
    )
    assert "completion=not_established" in output
    assert "The draft below is not an accepted completion report." in output


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


def test_passing_review_surfaces_residual_format_issues() -> None:
    """A pass with an unreadable remainder is still shown, but does not gate."""

    output = format_cli_closeout(
        response_text="Draft answer.",
        status="ready",
        execution_status="completed",
        scrutiny_details={
            "verdict": "pass",
            "format_issues": ["missing heading(s): SCORE", "unreadable score: 'high'"],
        },
    )

    assert "### Scrutiny format issues (advisory)" in output
    assert "#### Reviewer output was partially unreadable" in output
    assert "- missing heading(s): SCORE" in output
    assert "- unreadable score: 'high'" in output
    assert "scrutiny=pass_with_format_issues" in output
    assert "completion=not_established" not in output
    assert output.endswith("### Agent report\nDraft answer.\n")
    assert "Agent-reported outcome: Draft answer." in output


def test_passing_review_without_format_issues_renders_no_review_section() -> None:
    output = format_cli_closeout(
        response_text="Draft answer.",
        status="ready",
        execution_status="completed",
        scrutiny_details={"verdict": "pass", "format_issues": []},
    )

    assert "Scrutiny" not in output
    assert "partially unreadable" not in output
    assert "scrutiny=pass_with_format_issues" not in output
    assert output == format_cli_closeout(
        response_text="Draft answer.", status="ready", execution_status="completed"
    )
