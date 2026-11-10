"""Groundedness gate: verification claims in agent reports need tool evidence.

A report that says work was verified, tested, or confirmed must cite
observations from this run's tool results. Claim classes are coarse on
purpose: they catch fabricated verification (claims with no supporting
tool class at all), not subtly wrong details. File-level claim mapping
is a documented extension point, not part of this gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ai_agent.contracts import ToolResult

ClaimClass = Literal["inspection", "modification", "test_execution"]

#: Successful tools that count as looking at the world.
INSPECTION_TOOLS = frozenset(
    {
        "read_file",
        "list_dir",
        "find_files",
        "grep_search",
        "git_diff",
        "git_status",
        "python_navigate",
        "rename_preview",
    }
)

#: Successful tools that count as changing the world.
MODIFICATION_TOOLS = frozenset(
    {
        "create_file",
        "edit_file",
        "rename_apply",
        "staged_apply",
        "run_command",
    }
)

#: Successful tools that count as executing checks. Unknown tool names never
#: qualify here: only an explicit execution tool backs a "tests pass" claim.
TEST_EXECUTION_TOOLS = frozenset(
    {
        "run_command",
        "python_runtime",
        "process_start",
        "process_status",
        "process_stop",
    }
)

_EVIDENCE_BY_CLASS: dict[ClaimClass, frozenset[str]] = {
    "inspection": INSPECTION_TOOLS,
    "modification": MODIFICATION_TOOLS,
    "test_execution": TEST_EXECUTION_TOOLS,
}

#: Words in front of a claim verb that turn it into a request, a negation,
#: or future work rather than a claim about completed verification.
_NON_CLAIM_PRECEDERS = frozenset(
    {
        "please",
        "to",
        "should",
        "must",
        "need",
        "needs",
        "not",
        "never",
        "cannot",
        "can't",
        "couldn't",
        "unable",
        "without",
        "unverified",
        "requires",
        "require",
        "requesting",
    }
)

_CLAIM_PATTERNS: tuple[tuple[ClaimClass, re.Pattern[str]], ...] = (
    (
        "test_execution",
        re.compile(
            r"\btests?\s+(pass|passed|passing|are\s+passing|succeed|succeeded|"
            r"are\s+green|came\s+back\s+(clean|green))\b"
            r"|\btest\s+suite\s+[^.]{0,40}?\b(pass|passed|green|clean)\b"
            r"|\bpytest\b[^.]{0,60}?\b(pass|passed|green|ok\b|0\s+failed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "modification",
        re.compile(
            r"\b(I|we)\s+(created|added|updated|modified|deleted|removed|wrote|"
            r"fixed|implemented|refactored|migrated)\b"
            r"|\b(created|added|updated|modified|deleted|fixed|implemented)\s+"
            r"(the|this|that|a|an|\w+\.(py|md|toml|json|txt|ps1|js|ts))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "inspection",
        re.compile(
            r"\b(verified|confirmed|checked|validated|inspected|reviewed|"
            r"double-checked|re-checked)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class VerificationClaim:
    """One detected claim about completed verification work."""

    claim_class: ClaimClass
    text: str


@dataclass(frozen=True, slots=True)
class GroundednessVerdict:
    """Which report claims are backed by tool evidence."""

    supported: tuple[VerificationClaim, ...]
    unsupported: tuple[VerificationClaim, ...]

    @property
    def ok(self) -> bool:
        return not self.unsupported


def find_verification_claims(report: str) -> tuple[VerificationClaim, ...]:
    """Detect claims about completed verification, skipping non-claims."""
    claims: list[VerificationClaim] = []
    for claim_class, pattern in _CLAIM_PATTERNS:
        for match in pattern.finditer(report):
            start = match.start()
            preceding = report[max(0, start - 60) : start].lower()
            words = re.findall(r"[a-z']+", preceding)[-3:]
            if _NON_CLAIM_PRECEDERS & set(words):
                continue
            claims.append(VerificationClaim(claim_class, match.group(0).strip()))
    return tuple(claims)


def check_groundedness(report: str, tool_results: tuple[ToolResult, ...]) -> GroundednessVerdict:
    """Match each claim against successful tool evidence from the run."""
    claims = find_verification_claims(report)
    if not claims:
        return GroundednessVerdict(supported=(), unsupported=())
    successful = {result.name for result in tool_results if not result.is_error}
    known = set().union(*_EVIDENCE_BY_CLASS.values())
    unknown_successful = bool(successful - known)
    supported: list[VerificationClaim] = []
    unsupported: list[VerificationClaim] = []
    for claim in claims:
        if successful & _EVIDENCE_BY_CLASS[claim.claim_class]:
            supported.append(claim)
        elif claim.claim_class == "inspection" and unknown_successful:
            # An unfamiliar tool still did real work; it can back a generic
            # inspection claim, but never a modification or test claim.
            supported.append(claim)
        else:
            unsupported.append(claim)
    return GroundednessVerdict(supported=tuple(supported), unsupported=tuple(unsupported))
