"""Neutral, provider-independent prompt refinement primitives."""

from __future__ import annotations

from ai_orchestrator.models import (
    PromptRefinementRequest,
    PromptRefinementResult,
)
from ai_orchestrator.prompt_judge import judge_prompt


def refine_prompt(request: PromptRefinementRequest) -> PromptRefinementResult:
    """Refine a prompt deterministically without calling a model.

    Prior responses and critiques are preserved as optional inputs for callers
    that want to provide a model-assisted refinement implementation later.
    This function intentionally does not interpret or rewrite them.
    """

    judged = judge_prompt(request.prompt, request.profile)
    assumptions: tuple[str, ...] = ()
    if request.prior_response and request.prior_critique:
        assumptions = (
            "The prior response and critique are advisory evidence, not new user requirements.",
        )

    return PromptRefinementResult(
        original_prompt=request.prompt,
        refined_prompt=judged.refined_prompt,
        issues=judged.issues,
        assumptions=assumptions,
        change_summary=judged.change_summary,
        requires_user_approval=judged.refined_prompt is not None,
    )
