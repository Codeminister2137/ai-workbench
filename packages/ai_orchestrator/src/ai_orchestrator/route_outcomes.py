"""Route outcome records: the data flywheel behind quality grades.

Every CLI run appends one JSON line (route, task shape, success, effort).
`quality_adjustments` turns recent outcomes into conservative recommender
input: routes with repeated recent failures are demoted one quality step.
Grades are never boosted from outcomes (no feedback inflation), and empty
or missing evidence changes nothing.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

OUTCOMES_FILENAME = "route-outcomes.jsonl"


@dataclass(frozen=True, slots=True)
class RouteOutcome:
    """One finished CLI run from the router's point of view."""

    route_id: str
    mode: str
    success: bool
    tool_calls: int
    iterations: int
    finished_at: float
    input_tokens: int | None = None
    output_tokens: int | None = None


def append_outcome(path: str | Path, outcome: RouteOutcome) -> None:
    """Append one outcome line, creating parent directories as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(outcome), sort_keys=True) + "\n")


def load_outcomes(
    path: str | Path, *, window_hours: float = 72.0, limit: int = 500
) -> tuple[RouteOutcome, ...]:
    """Load recent outcomes newest-first; missing/corrupt files yield none."""
    target = Path(path)
    if not target.is_file():
        return ()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return ()
    cutoff = time.time() - window_hours * 3600
    outcomes: list[RouteOutcome] = []
    for line in reversed(lines):
        try:
            row = json.loads(line)
            outcome = RouteOutcome(
                route_id=str(row["route_id"]),
                mode=str(row["mode"]),
                success=bool(row["success"]),
                tool_calls=int(row["tool_calls"]),
                iterations=int(row["iterations"]),
                finished_at=float(row["finished_at"]),
                input_tokens=row.get("input_tokens"),
                output_tokens=row.get("output_tokens"),
            )
        except (ValueError, TypeError, KeyError):
            continue
        if outcome.finished_at >= cutoff:
            outcomes.append(outcome)
    return tuple(outcomes)


def quality_adjustments(
    outcomes: tuple[RouteOutcome, ...] | list[RouteOutcome],
    *,
    min_runs: int = 3,
) -> dict[str, int]:
    """Demote routes with repeated recent failures; never boost.

    A route with at least ``min_runs`` recent outcomes and zero successes
    drops one quality step. Everything else keeps its catalog grade, so a
    thin or mixed record cannot inflate or trash routing.
    """
    by_route: dict[str, list[bool]] = {}
    for outcome in outcomes:
        by_route.setdefault(outcome.route_id, []).append(outcome.success)
    adjustments: dict[str, int] = {}
    for route_id, successes in by_route.items():
        if len(successes) >= min_runs and not any(successes):
            adjustments[route_id] = -1
    return adjustments


def load_quality_adjustments(
    path: str | Path, *, window_hours: float = 72.0, min_runs: int = 3
) -> Mapping[str, int]:
    """Read an outcomes file and compute demotions; failures yield none."""
    try:
        return quality_adjustments(
            load_outcomes(path, window_hours=window_hours), min_runs=min_runs
        )
    except OSError:
        return {}
