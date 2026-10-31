"""Derive fallback inputs from live route evidence.

`fallback_candidates` accepts a caller-supplied ``priority`` order and an
``unavailable_route_ids`` set, both documented as observed-allowance inputs.
This module builds those inputs from provider-level sweep observations
(reachability) and micro-evaluation outcomes (pass/fail), e.g. the
``route_probe`` / ``route_eval`` snapshots.

The bridge consumes plain data (no provider imports: the Orchestrator owns
neutral local contracts). Provider-level evidence applies to catalog routes
by ``provider/`` prefix. Only proven-good routes are prioritized; failed or
unknown routes keep their existing recommender rank behind them, and only
positively unreachable providers are excluded. Empty evidence changes
nothing.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any


@dataclasses.dataclass(frozen=True)
class RouteEvidence:
    """One provider-level observation: reachable sweep + optional eval."""

    route: str
    reachable: bool
    passed_eval: bool | None = None


def _provider(route_id: str) -> str:
    return route_id.split("/", 1)[0] if "/" in route_id else route_id


def merge_probe_eval(
    probes: Sequence[Mapping[str, Any]], evals: Sequence[Mapping[str, Any]]
) -> list[RouteEvidence]:
    """Join sweep rows (route/reachable) with eval rows (route/passed)."""
    verdict: dict[str, bool] = {}
    for row in evals:
        route = row.get("route")
        passed = row.get("passed")
        if isinstance(route, str) and isinstance(passed, bool) and not row.get("error"):
            verdict[route] = passed
    merged = []
    seen = set()
    for row in probes:
        route = row.get("route")
        reachable = row.get("reachable")
        if not isinstance(route, str) or not isinstance(reachable, bool):
            continue
        seen.add(route)
        merged.append(RouteEvidence(route, reachable, verdict.get(route)))
    for route, passed in verdict.items():
        # An eval verdict proves the route answers even without a sweep row
        # (e.g. inference-only keys with no list endpoint).
        if route not in seen:
            merged.append(RouteEvidence(route, True, passed))
    return merged


def priority_routes(
    evidence: Sequence[RouteEvidence], catalog_route_ids: Sequence[str]
) -> tuple[str, ...]:
    """Catalog routes ordered by evidence: eval-passed, then reachable.

    Failed, unreachable, and unknown providers stay unlisted so the
    existing recommender rank continues to order them behind the listed
    routes. Catalog order is preserved within each group.
    """
    by_provider = {item.route: item for item in evidence}

    def rank(route_id: str) -> int | None:
        item = by_provider.get(_provider(route_id))
        if item is None or not item.reachable:
            return None
        if item.passed_eval is True:
            return 0
        if item.passed_eval is None:
            return 1
        return None

    ranked = sorted(
        (route_id for route_id in catalog_route_ids if rank(route_id) is not None),
        key=lambda route_id: rank(route_id),  # type: ignore[arg-type]
    )
    return tuple(ranked)


def unavailable_routes(
    evidence: Sequence[RouteEvidence], catalog_route_ids: Sequence[str]
) -> frozenset[str]:
    """Catalog routes under positively unreachable providers."""
    down = {item.route for item in evidence if not item.reachable}
    return frozenset(route_id for route_id in catalog_route_ids if _provider(route_id) in down)
