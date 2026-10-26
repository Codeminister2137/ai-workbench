"""Deterministic user-visible closeouts for repo-assistant CLI runs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ai_provider.turn_usage import ACTIVE_USAGE

REPORT_SCOPE = "repository_tool_actions_v1"
REPORT_SCOPE_NOTICE = (
    "Agent narrative describes repository/tool actions. It does not certify absence "
    "of provider inference, host bookkeeping, test artifacts or other host effects. "
    "Host observations take precedence; technical claims still require evidence and review."
)


def observed_inference() -> dict[str, int] | None:
    """Snapshot adapter receipts, without implying a census of host network traffic."""
    ledger = ACTIVE_USAGE.get()
    if ledger is None:
        return None
    return {"adapter_attempts": ledger.attempts, "completed_responses": ledger.responses}


AUXILIARY_RESPONSE_NOTICE = (
    "Auxiliary advice (unverified). This pass does not edit files or run tests; "
    "claims below are not completion or validation evidence."
)

FINAL_RESPONSE_INSTRUCTION = """\
The CLI wraps your final response in this fixed user-visible closeout:
## **SUMMARY**
- Changed: ...
- Validated: ...
- Notes: ...
Do not emit a duplicate summary; answer the request normally and clearly
distinguish proposed or agent-reported changes from independently verified
results. The CLI's validation and execution fields come from recorded evidence,
not from claims in your response.
Your narrative has repository/tool-action scope: statements about no edits or no
network activity refer to your repository/tool actions, not provider inference or
all host effects. State that scope when reporting effects. Explicit broader claims
still need evidence; the scope label does not verify arbitrary technical claims.
The CLI host may create or update session/orchestration databases and logs during
the task, independently of your tools. If mentioning those artifacts, distinguish
host bookkeeping from your own edits. Their presence at your first inspection
does not establish that they predated the task, stayed unchanged, or are unrelated
to the workflow."""


def safe_diagnostic_label(value: object) -> str | None:
    """Accept bounded identifiers, never exception text or multiline diagnostics."""
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/@+\-]{1,160}", value):
        return value
    return None


def safe_fallback_handoff(value: object) -> dict[str, str] | None:
    """Project a handoff onto bounded control facts; omit observations and errors."""
    if not isinstance(value, Mapping):
        return None
    allowed = {
        "status": {"continuation_stopped"},
        "reason": {"deadline_or_no_eligible_compatible_route"},
        "failure_kind": {"usage_limit", "model_overload"},
        "quality_policy": {
            "preserve_quality",
            "task_minimum",
            "emergency_preserve",
            "prefer_quality",
        },
    }
    result = {
        key: item
        for key, choices in allowed.items()
        if isinstance(item := value.get(key), str) and item in choices
    }
    route = safe_diagnostic_label(value.get("failed_route_id"))
    if route is not None:
        result["failed_route_id"] = route
    return result or None


def _validation_summary(details: Mapping[str, object] | None) -> str:
    if details is None:
        return "No separate deterministic validation stage recorded."

    status = str(details.get("validation_status", "not_recorded"))
    results = details.get("results")
    if isinstance(results, list) and results:
        commands = [
            f"{item.get('command', 'unknown command')}: {item.get('status', 'unknown')}"
            for item in results
            if isinstance(item, dict)
        ]
        if commands:
            return f"{status} ({'; '.join(commands)})"

    reason = details.get("skip_reason") or details.get("failure_reason")
    return f"{status} ({reason})" if reason else status


def _agent_outcome(response: str | None) -> str:
    if not response or not response.strip():
        return "No final response was captured; no change summary is available."

    for line in response.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or candidate.startswith("```"):
            continue
        candidate = re.sub(
            r"^(-\s+)?\*\*(Changed|Validated|Notes|Preserved)(?:\*\*\s*:|:\*\*)",
            r"\1\2:",
            candidate,
        )
        for prefix in ("- Changed:", "Changed:"):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix) :].strip()
                break
        if not candidate:
            continue
        candidate = candidate.removeprefix("- ")
        if len(candidate) > 200:
            # Keep full links in the report rather than clipping a destination.
            candidate = (
                "See the agent report below for the linked outcome."
                if "](" in candidate or "][" in candidate
                else candidate[:197].rstrip() + "..."
            )
        return (
            f"Agent-reported outcome: {candidate} "
            "(workspace changes are not independently attributed by the CLI)."
        )
    return "No concise outcome was captured; see the agent report below."


def _scrutiny_finding_lines(scrutiny_details: Mapping[str, object]) -> list[str]:
    """Render the readable parts of a scrutiny report as labelled sections."""

    lines: list[str] = []
    for key, label in (
        ("verdict", "Reviewer verdict"),
        ("issues", "Reviewer issues"),
        ("next_action", "Reviewer next action"),
        ("failure_reason", "Review failure"),
        ("skip_reason", "Review not completed"),
    ):
        value = scrutiny_details.get(key)
        if isinstance(value, str) and value.strip():
            lines.extend([f"#### {label}", value.strip()])
    revision = scrutiny_details.get("revised_response")
    if isinstance(revision, str) and revision.strip().lower() not in {
        "",
        "none",
        "none.",
        "null",
    }:
        lines.extend(
            [
                "#### Reviewer-proposed revision (not applied or independently verified)",
                revision,
            ]
        )
    return lines


def _format_issue_bullets(format_issues: object) -> list[str]:
    """Render parser workarounds as bullets, or nothing when there are none."""

    if not isinstance(format_issues, list) or not format_issues:
        return []
    return [
        "#### Reviewer output was partially unreadable",
        "The reviewer did not produce the exact report shape it was "
        "asked for. What follows is what could be recovered; this is "
        "a limitation of the review, not a finding about the work.",
        *(f"- {issue}" if isinstance(issue, str) else f"- {issue!r}" for issue in format_issues),
    ]


def format_cli_closeout(
    *,
    response_text: str | None,
    status: str,
    execution_status: str,
    validation_details: Mapping[str, object] | None = None,
    scrutiny_details: Mapping[str, object] | None = None,
    scrutiny_policy: str = "advisory",
    fallback_attempts: Sequence[Mapping[str, str]] = (),
    failure_reason: str | None = None,
    provider: str | None = None,
    category: str | None = None,
    cause_kind: str | None = None,
    effective_route_id: str | None = None,
    fallback_handoff: Mapping[str, object] | None = None,
) -> str:
    """Render the fixed CLI summary envelope around any agent's final response."""

    notes = [f"status={status}", f"execution_status={execution_status}"]
    if fallback_attempts:
        attempts = ", ".join(
            f"{attempt.get('route_id', 'unknown route')}:{attempt.get('status', 'unknown')}"
            for attempt in fallback_attempts
        )
        notes.append(f"fallback_attempts={attempts}")
    else:
        notes.append("fallback_attempts=none")
    if failure_reason:
        notes.append(f"failure_reason={failure_reason.replace(chr(10), ' ').strip()}")
        for key, value in (
            ("provider", provider),
            ("category", category),
            ("cause_kind", cause_kind),
        ):
            notes.append(f"{key}={safe_diagnostic_label(value) or 'unknown'}")
    if route := safe_diagnostic_label(effective_route_id):
        notes.append(f"effective_route_id={route}")
    if handoff := safe_fallback_handoff(fallback_handoff):
        notes.append(
            "fallback_handoff=" + ", ".join(f"{key}:{value}" for key, value in handoff.items())
        )

    # ADR-066 separates two very different states that used to be conflated:
    #
    # - The reviewer *reached* a non-pass verdict. Under the advisory policy
    #   (the default) that is recorded and shown but does not gate the outcome,
    #   because advisory was adopted precisely because the gate falsely blocked.
    # - The review never produced a verdict at all — it failed, was skipped, or
    #   the reviewer returned output that could not be read. That is *missing*
    #   review evidence rather than a judgement, so it still prevents an
    #   accepted completion under either policy.
    scrutiny_verdict = scrutiny_details.get("verdict") if scrutiny_details is not None else None
    review_input_changed = (
        scrutiny_details is not None and scrutiny_details.get("input_changed_since_review") is True
    )
    review_never_ran = scrutiny_details is not None and scrutiny_verdict is None
    non_pass_verdict = scrutiny_details is not None and scrutiny_verdict not in (None, "pass")
    unresolved_review = (
        review_input_changed
        or review_never_ran
        or (non_pass_verdict and scrutiny_policy == "required")
    )
    scrutiny_did_not_pass = review_input_changed or (
        scrutiny_verdict != "pass" if scrutiny_details is not None else False
    )
    notes.append(f"scrutiny_policy={scrutiny_policy}")
    if review_input_changed:
        notes.append("repair=incomplete_with_workspace_changes")
    review_lines: list[str] = []
    if scrutiny_did_not_pass:
        assert scrutiny_details is not None
        if unresolved_review:
            notes.append("completion=not_established; scrutiny=unresolved")
            heading = "### Unresolved scrutiny"
            preamble = [
                "The draft below is not an accepted completion report. "
                "Resolve the review findings or missing review before treating "
                "the task as complete.",
                "Review findings are advisory; they are not independent verification.",
            ]
            if review_input_changed:
                preamble.insert(
                    0,
                    "The workspace changed during an incomplete repair. Earlier validation "
                    "and review predate those changes; the retained report may be stale.",
                )
        else:
            heading = "### Scrutiny findings (advisory)"
            preamble = [
                "Scrutiny did not reach a pass verdict. Under the advisory "
                "scrutiny policy these findings are recorded but do not gate the "
                "outcome; read them before treating the work as complete.",
                "Review findings are advisory; they are not independent verification.",
            ]
        review_lines = [heading, *preamble]
        review_lines.extend(_scrutiny_finding_lines(scrutiny_details))
        review_lines.extend(_format_issue_bullets(scrutiny_details.get("format_issues")))
        review_lines.append("")
    elif scrutiny_details is not None:
        # ADR-066: a pass verdict is a pass even when the reviewer's report had
        # recoverable shape problems. The recovered verdict is what counts, but
        # the unreadable remainder is still shown so a missing finding is not
        # silently treated as a finding-free review.
        format_issue_lines = _format_issue_bullets(scrutiny_details.get("format_issues"))
        if format_issue_lines:
            notes.append("scrutiny=pass_with_format_issues")
            review_lines = [
                "### Scrutiny format issues (advisory)",
                "The reviewer reached a pass verdict, but part of its report could "
                "not be read. The recovered verdict is retained; findings that were "
                "lost with the unreadable text cannot be ruled out.",
                *format_issue_lines,
                "",
            ]

    response = response_text.strip() if response_text and response_text.strip() else None
    report = response if response is not None else "No final response was captured."
    # The outer envelope owns this heading. Adjust only a leading duplicate in
    # the display; callers retain the original agent response in session storage.
    report = re.sub(
        r"\A##[ \t]+\*\*SUMMARY\*\*[ \t]*(?:\r?\n|$)",
        "#### Agent summary\n",
        report,
        count=1,
    )
    outcome = (
        "Agent draft retained below; unresolved scrutiny prevents an accepted outcome summary."
        if unresolved_review
        else _agent_outcome(response)
    )
    validation = _validation_summary(validation_details)
    if unresolved_review:
        validation += " (Recorded checks only; this does not verify the draft's other claims.)"
    return "\n".join(
        [
            "## **SUMMARY**",
            f"- Changed: {outcome}",
            f"- Validated: {validation}",
            f"- Notes: {'; '.join(notes)}",
            "",
            *review_lines,
            "### Host observations and report scope",
            (
                "Observed adapter calls in this CLI invocation: "
                f"{inference['adapter_attempts']} attempts, "
                f"{inference['completed_responses']} completed responses."
                if (inference := observed_inference()) is not None
                else "Adapter call observations unavailable; inference counts are unknown."
            ),
            "These receipts are not a network audit; uninstrumented or external-client "
            "inference and other host effects remain unknown.",
            REPORT_SCOPE_NOTICE,
            "",
            "### Agent report — draft with unresolved scrutiny"
            if unresolved_review
            else "### Agent report",
            report,
            "",
        ]
    )
