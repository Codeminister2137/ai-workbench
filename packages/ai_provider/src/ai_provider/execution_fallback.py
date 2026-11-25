"""Fallback verdict taxonomy: markers, classifiers and allowance interpreters.

Scope C end-state: the fallback walk lives in
ai_provider.fallback_executor (single executor for drain, chat, relay
and direct CLI). This module keeps the verdict vocabulary both the
executor and the suites share.
"""

from typing import Any

from ai_provider.agent_readiness import (  # noqa: F401 - stable patch point, see below
    check_agent_readiness,
)
from ai_provider.external_agents import ExternalAgentResult

# NOTE (scope C): check_agent_readiness stays imported here (unused locally)
# as the stable readiness patch point. FallbackExecutor resolves readiness
# through this namespace, and the suites patch it here; do not remove.


def external_usage_limit(result: ExternalAgentResult) -> bool:
    """Inspect only failed client error channels, never prompt/tool/final-answer text."""

    failure = result.events.failure_reason if result.events else None
    if result.returncode == 0 and not failure:
        return False
    text = (failure or "") + "\n" + result.stderr
    return explicit_usage_limit(text)


def explicit_usage_limit(text: str) -> bool:
    normalized = text.lower()
    return any(
        marker in normalized
        for marker in (
            "usage_limit_reached",
            "insufficient_quota",
            "quota_exceeded",
            "usage limit",
            "quota exhausted",
            "quota exceeded",
            "exceeded your quota",
            "premium request limit",
            "no remaining credits",
            "rate limit exceeded",
            "resource_exhausted",
            "credit balance is exhausted",
        )
    )


def explicit_model_overload(text: str) -> bool:
    """Recognize temporary availability markers separately from account exhaustion."""
    return any(
        marker in text.lower()
        for marker in (
            "server_overloaded",
            "selected model is at capacity",
            "model is overloaded",
            "server is overloaded",
        )
    )


def external_model_overload(result: ExternalAgentResult) -> bool:
    """Only failed error channels can trigger overload handling, never tool/answer text."""
    failure = result.events.failure_reason if result.events else None
    if result.returncode == 0 and not failure:
        return False
    return explicit_model_overload((failure or "") + "\n" + result.stderr)


_CAPABILITY_REROUTE_MARKERS = (
    "route to a tool-capable model",
    "route to a longer-context model",
)


def explicit_capability_reroute(text: str) -> bool:
    """Recognize known capability reroute messages; never generic retryables."""
    normalized = text.lower()
    return any(marker in normalized for marker in _CAPABILITY_REROUTE_MARKERS)


_LOCAL_FAILURE_MARKERS = (
    "unsupported model",
    "permission denied",
    "permission was denied",
    "auto-denied",
)
"""Failure text proving the request/environment is bad, never the route.

A bad model pin or a local permission refusal is actionable where it
happened: falling through would burn another allowance to mask a local
misconfiguration. Evidence-based list; extend only with observed text.
"""


def explicit_local_failure(text: str) -> bool:
    """Recognize local request/environment failures; never generic errors."""
    normalized = text.lower()
    return any(marker in normalized for marker in _LOCAL_FAILURE_MARKERS)


def external_route_failure(result: ExternalAgentResult) -> bool:
    """True when a failed client never engaged: no work evidence at all.

    A nonzero exit (or failure reason) with zero command/tool/file/web
    events, no final answer and no last message means the route died
    before doing anything — the classic silent-cap shape (observed:
    Kiro monthly cap exits 1 with empty channels). This must fall
    through to the next route, never record "finished". Only presence
    flags and counts are inspected, never prompt/tool/answer content.
    Local request/environment failures (bad pin, permission refusal)
    are terminal and never route failures.
    """

    failure = result.events.failure_reason if result.events else None
    if result.returncode == 0 and not failure:
        return False
    if explicit_local_failure((failure or "") + "\n" + result.stderr):
        return False
    if result.last_message:
        return False
    events = result.events
    if events is None:
        return True
    if events.final_answer:
        return False
    return not (
        events.command_events
        or events.tool_events
        or events.file_change_events
        or events.web_search_events
    )


def classify_external_result(result: ExternalAgentResult) -> str:
    """One verdict for an external-agent result; the single decision point.

    Returns "success", "usage_limit", "model_overload", "capability",
    "route_failure" (failed before doing anything: fall through) or
    "genuine_failure" (failed after engaging: terminal, no spend
    multiplication). Signal markers win over work evidence: a client
    that reports a usage limit after partial work is still limited.
    """

    failure = result.events.failure_reason if result.events else None
    if result.returncode == 0 and not failure:
        return "success"
    if external_usage_limit(result):
        return "usage_limit"
    if external_model_overload(result):
        return "model_overload"
    if explicit_capability_reroute((failure or "") + "\n" + result.stderr):
        return "capability"
    if external_route_failure(result):
        return "route_failure"
    return "genuine_failure"


def _kiro_windows_exhausted(windows: list[dict[str, Any]]) -> bool:
    """Kiro covered-credits semantics: covered==plan means consumed.

    Verified empirically 2026-11-23: the Kiro CLI refuses work when
    covered_credits reaches plan_credits (monthly cap), so "X of Y
    covered in plan" reads as consumed, not remaining, for admission.
    """
    for window in windows:
        if not isinstance(window, dict):
            continue
        if window.get("bucket_id") != "plan_credits":
            continue
        try:
            covered = float(window.get("covered_credits", 0.0))
            plan = float(window.get("plan_credits", 0.0))
        except (TypeError, ValueError):
            continue
        if plan > 0 and covered >= plan:
            return True
    return False


def _codex_windows_exhausted(windows: list[dict[str, Any]]) -> bool:
    """Codex quota semantics: any window at 100% used means refused.

    Settled empirically 2026-11-25: weekly window at 100% 23-25.11
    (primary 5h at 0%) while 0 of 47 codex executions finished (all
    usage_limit verdicts). No counterexample observed.
    """
    for window in windows:
        if not isinstance(window, dict):
            continue
        try:
            used = float(window.get("used_percent", 0.0))
        except (TypeError, ValueError):
            continue
        if used >= 100:
            return True
    return False


ALLOWANCE_EXHAUSTION = {
    "kiro_isolated_v2_usage": _kiro_windows_exhausted,
    "codex_app_server": _codex_windows_exhausted,
}
"""Verified per-source exhaustion interpreters; unknown sources never block."""


def allowance_exhausted(observation: dict[str, Any] | None) -> bool:
    """True when an allowance observation proves no budget remains.

    Only sources with a verified interpreter count; anything unknown,
    malformed or unobserved returns False so admission never blocks
    on uninterpretable data (the "never infer" caution, scoped).
    """
    if not isinstance(observation, dict):
        return False
    if observation.get("status") != "available":
        return False
    interpret = ALLOWANCE_EXHAUSTION.get(str(observation.get("source") or ""))
    if interpret is None:
        return False
    windows = observation.get("windows")
    if not isinstance(windows, list):
        return False
    try:
        return bool(interpret(windows))
    except Exception:  # noqa: BLE001 - interpretation must never break routing
        return False
