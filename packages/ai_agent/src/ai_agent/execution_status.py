"""Execution-completeness facts for delegated and child agent runs (ADR-078)."""

from __future__ import annotations

from dataclasses import dataclass

from ai_provider import AIResponse, FinishReason


@dataclass(frozen=True, slots=True)
class ExecutionStatus:
    """Whether a child run stopped on a final answer, and why not when it did not.

    This is a fact about how the run ended, not a judgement about the task
    outcome. A run with an earlier tool error can still be complete, and a
    complete run still needs independent validation of its reported effects.
    """

    complete: bool
    reason: str

    def render(self) -> str:
        """Return the supervisor-facing one-line statement of this fact."""
        return (
            f"Execution complete: {str(self.complete).lower()} ({self.reason}); "
            "task outcome still requires independent validation."
        )


def assess_execution(response: AIResponse) -> ExecutionStatus:
    """Report whether a child response ended as a final answer rather than mid-work."""
    if response.tool_calls or response.message.tool_calls:
        return ExecutionStatus(False, "unresolved tool calls")
    if not response.message.content.strip():
        return ExecutionStatus(False, "empty final response")
    if response.finish_reason is FinishReason.LENGTH:
        return ExecutionStatus(False, "provider output length limit")
    if response.finish_reason is FinishReason.ERROR:
        return ExecutionStatus(False, "provider error finish reason")
    return ExecutionStatus(
        True, f"final response returned (finish_reason={response.finish_reason.value})"
    )
