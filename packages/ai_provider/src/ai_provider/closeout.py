"""Deterministic user-visible closeouts for repo-assistant CLI runs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

FINAL_RESPONSE_INSTRUCTION = """\
The CLI wraps your final response in this fixed user-visible closeout:
## **SUMMARY**
- Changed: ...
- Validated: ...
- Notes: ...
Do not emit a duplicate summary; answer the request normally and clearly
distinguish proposed or agent-reported changes from independently verified
results. The CLI's validation and execution fields come from recorded evidence,
not from claims in your response."""


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
        for prefix in ("- Changed:", "Changed:"):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix) :].strip()
                break
        if len(candidate) > 200:
            candidate = candidate[:197].rstrip() + "..."
        return (
            f"Agent-reported outcome: {candidate} "
            "(workspace changes are not independently attributed by the CLI)."
        )
    return "No concise outcome was captured; see the agent report below."


def format_cli_closeout(
    *,
    response_text: str | None,
    status: str,
    execution_status: str,
    validation_details: Mapping[str, object] | None = None,
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

    response = response_text.strip() if response_text and response_text.strip() else None
    report = response if response is not None else "No final response was captured."
    return "\n".join(
        [
            "## **SUMMARY**",
            f"- Changed: {_agent_outcome(response)}",
            f"- Validated: {_validation_summary(validation_details)}",
            f"- Notes: {'; '.join(notes)}",
            "",
            "### Agent report",
            report,
            "",
        ]
    )
