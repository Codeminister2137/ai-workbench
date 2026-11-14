"""External execution completes unless the final result is missing (9add8f87 A)."""

from ai_agent.repo_coding_assistant import (
    _external_execution_completed,
    _intermediate_failure_only,
)


def test_clean_zero_exit_completes() -> None:
    assert _external_execution_completed(0, None, "answer") is True
    assert _intermediate_failure_only(0, None, "answer") is False


def test_intermediate_failure_with_answer_completes() -> None:
    assert _external_execution_completed(0, "command_execution", "answer") is True
    assert _intermediate_failure_only(0, "command_execution", "answer") is True


def test_intermediate_failure_without_answer_fails() -> None:
    assert _external_execution_completed(0, "command_execution", None) is False
    assert _external_execution_completed(0, "command_execution", "  ") is False


def test_nonzero_exit_always_fails() -> None:
    assert _external_execution_completed(1, None, "answer") is False
    assert _external_execution_completed(1, "command_execution", "answer") is False
