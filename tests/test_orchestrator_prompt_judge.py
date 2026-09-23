from __future__ import annotations

from ai_orchestrator import PromptIssueSeverity, judge_prompt


def test_prompt_judge_marks_empty_prompt_as_blocking() -> None:
    result = judge_prompt("   ")

    assert result.should_refine is False
    assert result.issues[0].severity is PromptIssueSeverity.BLOCKING


def test_prompt_judge_detects_short_ambiguous_prompt() -> None:
    result = judge_prompt("Fix this")

    codes = {issue.code for issue in result.issues}
    assert "low_context" in codes
    assert "ambiguous_reference" in codes
    assert result.should_refine is True
    assert result.refined_prompt is not None
    assert "Instructions:" in result.refined_prompt


def test_prompt_judge_does_not_require_refinement_for_specific_prompt() -> None:
    result = judge_prompt(
        "Explain how to run the provider tests as a numbered list with short commands."
    )

    assert result.should_refine is False
    assert result.refined_prompt is None


def test_prompt_judge_accepts_explicit_repository_reference() -> None:
    result = judge_prompt("Examine this repo and suggest next steps.")

    assert "ambiguous_reference" not in {issue.code for issue in result.issues}
