"""Deterministic prompt review before orchestration executes a request."""

from __future__ import annotations

import re

from ai_orchestrator.models import (
    PromptIssue,
    PromptIssueSeverity,
    PromptJudgeResult,
    TaskProfile,
)

_AMBIGUOUS_REFERENCES = re.compile(r"\b(this|that|it|thing|stuff|something)\b", re.IGNORECASE)
_CLEAR_REPOSITORY_REFERENCES = re.compile(
    r"\b(this|that)\s+(repo|repository|file|module|project|code|test|function|class|directory|document)\b",
    re.IGNORECASE,
)
_OUTPUT_HINTS = re.compile(
    r"\b(list|table|json|bullet|bullets|explain|summary|steps|format|answer)\b",
    re.IGNORECASE,
)
_CONFLICT_HINTS = (
    ("brief", "detailed"),
    ("concise", "comprehensive"),
    ("short", "long"),
    ("simple", "advanced"),
)


def judge_prompt(prompt: str, profile: TaskProfile | None = None) -> PromptJudgeResult:
    """Judge whether a prompt likely needs clarification before execution."""

    del profile
    normalized = " ".join(prompt.split())
    issues: list[PromptIssue] = []

    if not normalized:
        issues.append(
            PromptIssue(
                code="empty_prompt",
                message="Prompt is empty.",
                severity=PromptIssueSeverity.BLOCKING,
                confidence=1.0,
            )
        )
        return PromptJudgeResult(
            original_prompt=prompt,
            issues=tuple(issues),
            should_refine=False,
        )

    if len(normalized) < 20:
        issues.append(
            PromptIssue(
                code="low_context",
                message="Prompt is very short and may not provide enough context.",
                severity=PromptIssueSeverity.WARNING,
                confidence=0.75,
            )
        )

    if _has_ambiguous_reference(normalized) and len(normalized) < 120:
        issues.append(
            PromptIssue(
                code="ambiguous_reference",
                message="Prompt uses a vague reference that may need more context.",
                severity=PromptIssueSeverity.WARNING,
                confidence=0.65,
            )
        )

    if not _OUTPUT_HINTS.search(normalized):
        issues.append(
            PromptIssue(
                code="missing_output_shape",
                message="Prompt does not specify the desired output shape.",
                severity=PromptIssueSeverity.INFO,
                confidence=0.55,
            )
        )

    lowered = normalized.lower()
    for first, second in _CONFLICT_HINTS:
        if first in lowered and second in lowered:
            issues.append(
                PromptIssue(
                    code="possible_conflicting_constraints",
                    message=(
                        f"Prompt may contain conflicting constraints: {first!r} and {second!r}."
                    ),
                    severity=PromptIssueSeverity.WARNING,
                    confidence=0.6,
                )
            )

    should_refine = any(issue.severity is not PromptIssueSeverity.INFO for issue in issues)
    refined_prompt = None
    change_summary = None
    if should_refine:
        refined_prompt = _build_refined_prompt(normalized, issues)
        change_summary = "Clarified execution context without adding facts."

    return PromptJudgeResult(
        original_prompt=prompt,
        issues=tuple(issues),
        should_refine=should_refine,
        refined_prompt=refined_prompt,
        change_summary=change_summary,
    )


def _has_ambiguous_reference(prompt: str) -> bool:
    """Return whether the prompt contains an unqualified vague reference."""

    matches = list(_AMBIGUOUS_REFERENCES.finditer(prompt))
    if not matches:
        return False

    clear_spans = {match.span() for match in _CLEAR_REPOSITORY_REFERENCES.finditer(prompt)}
    for match in matches:
        if not any(
            clear_start <= match.start() < clear_end for clear_start, clear_end in clear_spans
        ):
            return True
    return False


def _build_refined_prompt(prompt: str, issues: list[PromptIssue]) -> str:
    additions: list[str] = []
    issue_codes = {issue.code for issue in issues}
    if "low_context" in issue_codes or "ambiguous_reference" in issue_codes:
        additions.append("If needed, state any assumptions before answering.")
    if "missing_output_shape" in issue_codes:
        additions.append("Provide a clear, structured answer.")

    if not additions:
        return prompt
    return f"{prompt}\n\nInstructions: {' '.join(additions)}"
