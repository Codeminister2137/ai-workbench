from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

RESPONSE_SCRUTINY_SYSTEM_PROMPT = """
You scrutinize a repo-aware coding assistant response for usefulness and accuracy.
Compare the candidate response with the original request and the supplied repository
context. Do not invent facts or claim that a recommendation is required when the
context does not support it.

Return a concise report with exactly these headings:
VERDICT: pass | needs_revision | fail
SCORE: 0-10
STRENGTHS:
ISSUES:
RECOMMENDED_NEXT_ACTION:
REVISED_RESPONSE:

Judge whether the answer is grounded in the repository, distinguishes completed
work from remaining work, identifies the smallest useful next action, avoids
generic filler, and states uncertainty or decision boundaries. If the candidate
is already good, say so rather than proposing unnecessary changes.
""".strip()
_RESPONSE_SCRUTINY_HEADINGS = (
    "VERDICT",
    "SCORE",
    "STRENGTHS",
    "ISSUES",
    "RECOMMENDED_NEXT_ACTION",
    "REVISED_RESPONSE",
)
_RESPONSE_SCRUTINY_VERDICTS = {"pass", "needs_revision", "fail"}
_RESPONSE_SCRUTINY_HEADING_PATTERN = (
    r"(?mi)^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?"
    r"(VERDICT|SCORE|STRENGTHS|ISSUES|RECOMMENDED[ _]NEXT[ _]ACTION|REVISED[ _]RESPONSE)"
    r"(?:\*\*)?:(?:\*\*)?[ \t]*(.*)$"
)
_FENCED_JSON_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class ResponseScrutinyReport:
    """Parsed second-pass response-quality report."""

    verdict: str
    score: int
    strengths: str
    issues: str
    recommended_next_action: str
    revised_response: str
    raw_text: str


def build_response_scrutiny_prompt(original_prompt: str, response: str) -> str:
    """Build a bounded second-pass prompt for evaluating one assistant response."""

    return (
        "Original repository-analysis request:\n"
        f"{original_prompt}\n\n"
        "Candidate assistant response:\n"
        f"{response}\n\n"
        "Scrutinize the candidate response using the required report format."
    )


def parse_response_scrutiny_report(text: str) -> ResponseScrutinyReport:
    """Parse and validate the structured response-scrutiny report."""

    sections = _parse_response_scrutiny_heading_sections(text)
    if sections is None:
        sections = _parse_response_scrutiny_json_sections(text)

    missing = [heading for heading in _RESPONSE_SCRUTINY_HEADINGS if heading not in sections]
    if missing:
        raise ValueError("missing scrutiny heading(s): " + ", ".join(missing))

    verdict = sections["VERDICT"].strip().lower()
    if verdict not in _RESPONSE_SCRUTINY_VERDICTS:
        raise ValueError(f"invalid scrutiny verdict: {sections['VERDICT']!r}")

    try:
        score = int(sections["SCORE"].strip())
    except ValueError as exc:
        raise ValueError(f"invalid scrutiny score: {sections['SCORE']!r}") from exc
    if not 0 <= score <= 10:
        raise ValueError(f"scrutiny score out of range: {score}")

    return ResponseScrutinyReport(
        verdict=verdict,
        score=score,
        strengths=sections["STRENGTHS"],
        issues=sections["ISSUES"],
        recommended_next_action=sections["RECOMMENDED_NEXT_ACTION"],
        revised_response=sections["REVISED_RESPONSE"],
        raw_text=text,
    )


def _parse_response_scrutiny_heading_sections(text: str) -> dict[str, str] | None:
    """Parse report sections from canonical heading lines."""

    matches = list(
        re.finditer(
            _RESPONSE_SCRUTINY_HEADING_PATTERN,
            text,
        )
    )
    if not matches:
        return None

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = match.group(1).upper().replace(" ", "_")
        if heading in sections:
            raise ValueError(f"duplicate scrutiny heading: {heading}")
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        first_line = match.group(2).strip()
        continuation = text[match.end() : section_end].strip()
        sections[heading] = f"{first_line}\n{continuation}".strip() if continuation else first_line

    return sections


def _parse_response_scrutiny_json_sections(text: str) -> dict[str, str]:
    """Parse report sections from a JSON object with canonical keys."""

    candidate = text.strip()
    match = _FENCED_JSON_PATTERN.search(candidate)
    if match:
        candidate = match.group(1)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        heading: _stringify_scrutiny_section(parsed[heading])
        for heading in _RESPONSE_SCRUTINY_HEADINGS
        if heading in parsed
    }


def _stringify_scrutiny_section(value: Any) -> str:
    """Convert JSON scrutiny values to stable transcript text."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, indent=2)
