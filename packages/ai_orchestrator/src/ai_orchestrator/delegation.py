"""Policy for deciding which coding subtasks are suitable for local delegation."""

from __future__ import annotations

from dataclasses import dataclass

from ai_orchestrator.models import DelegationKind, TaskType


@dataclass(frozen=True, slots=True)
class DelegationDecision:
    """Explain whether a subtask may be delegated to a lower-capability model."""

    allowed: bool
    reason: str


_LOCAL_CODING_KINDS = frozenset(
    {
        DelegationKind.CONTEXT_EXTRACTION,
        DelegationKind.FILE_SUMMARIZATION,
        DelegationKind.SYMBOL_EXTRACTION,
        DelegationKind.TEST_CASE_GENERATION,
        DelegationKind.PROMPT_REFINEMENT,
    }
)


def assess_delegation(
    *,
    task_type: TaskType,
    delegation_kind: DelegationKind,
) -> DelegationDecision:
    """Assess whether a local model is suitable for a delegated subtask."""

    if task_type is TaskType.CODING:
        if delegation_kind in _LOCAL_CODING_KINDS:
            return DelegationDecision(
                allowed=True,
                reason="bounded coding support task with verifiable source output",
            )
        return DelegationDecision(
            allowed=False,
            reason=(
                "local delegation must not decide architecture or implementation; "
                "a stronger primary model must make that decision"
            ),
        )
    return DelegationDecision(
        allowed=delegation_kind
        not in {
            DelegationKind.ARCHITECTURAL_RECOMMENDATION,
            DelegationKind.IMPLEMENTATION_DECISION,
        },
        reason="decision-making subtasks require the primary model",
    )
