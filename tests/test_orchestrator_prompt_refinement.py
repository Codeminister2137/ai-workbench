from __future__ import annotations

from ai_orchestrator import (
    PromptRefinementRequest,
    refine_prompt,
)


def test_refine_prompt_provides_deterministic_pre_execution_refinement() -> None:
    result = refine_prompt(PromptRefinementRequest(prompt="Fix this"))

    assert result.original_prompt == "Fix this"
    assert result.refined_prompt is not None
    assert "Instructions:" in result.refined_prompt
    assert result.requires_user_approval is True


def test_refine_prompt_preserves_prior_response_and_critique_as_provenance_only() -> None:
    result = refine_prompt(
        PromptRefinementRequest(
            prompt="Review the plan.",
            prior_response="A draft answer.",
            prior_critique="The draft is too broad.",
        )
    )

    assert result.assumptions == (
        "The prior response and critique are advisory evidence, not new user requirements.",
    )
    assert result.original_prompt == "Review the plan."
