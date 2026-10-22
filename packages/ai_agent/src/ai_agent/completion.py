"""Optional caller-declared evidence requirements for final model candidates."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ai_agent.contracts import ToolResult


@dataclass(frozen=True, slots=True)
class CompletionRequirement:
    """A trusted, read-only predicate over completed tool results.

    The identifier, rather than arbitrary predicate text, is used in host feedback.
    A predicate must return bool. It does not authorize tools or grade report prose.
    """

    requirement_id: str
    satisfied: Callable[[tuple[ToolResult, ...]], bool]

    def __post_init__(self) -> None:
        if not isinstance(self.requirement_id, str) or not re.fullmatch(
            r"[a-z][a-z0-9_.-]{0,79}", self.requirement_id
        ):
            raise ValueError("Completion requirement needs a bounded lowercase identifier")
        if not callable(self.satisfied):
            raise TypeError("Completion requirement needs a callable predicate")


def missing_requirements(
    requirements: tuple[CompletionRequirement, ...], results: tuple[ToolResult, ...]
) -> tuple[str, ...]:
    """Unknown/nonboolean results fail the checker rather than certify completion."""
    missing = []
    for requirement in requirements:
        value = requirement.satisfied(results)
        if type(value) is not bool:
            raise TypeError("Completion predicate must return bool")
        if not value:
            missing.append(requirement.requirement_id)
    return tuple(missing)
