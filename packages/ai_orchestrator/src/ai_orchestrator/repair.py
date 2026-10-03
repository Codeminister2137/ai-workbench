"""Deterministic progress policy for supervised repair attempts."""


def repair_progress(*, state_changed: bool, failure_changed: bool) -> str:
    """Classify observed changes, rather than assistant claims or tool-call counts."""
    if state_changed:
        return "state_changed"
    if failure_changed:
        return "failure_changed"
    return "no_progress"


def review_reserve_seconds(budget_seconds: float, *, cap_seconds: float = 120.0) -> float:
    """Reserve ten percent of a run with a caller-selected review/handoff cap."""
    return min(cap_seconds, max(0.0, budget_seconds * 0.1))
