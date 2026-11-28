"""Offline, injected decision recording and replay in the Council store."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import uuid4

from storage import ConversationStore

from investor.paper import ProfileResult, evaluate
from investor.profiles import InvestorProfile


@dataclass(frozen=True)
class Observation:
    observed_at: datetime
    source: str
    prices: dict[str, float]


@dataclass(frozen=True)
class Proposal:
    weights: dict[str, float]
    rationale: str
    uncertainty: str
    alternatives: tuple[str, ...] = ()


def _aware(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware time required")
    return value.astimezone(UTC).isoformat()


def decisions(store: ConversationStore, run_id: str) -> list[dict]:
    """Read immutable originals in recording order, without later outcomes."""
    return [
        json.loads(row[0])
        for row in store.connection.execute(
            "SELECT record FROM investor_decisions WHERE run_id = ? ORDER BY rowid", (run_id,)
        )
    ]


def record_decision(
    store: ConversationStore,
    run_id: str,
    profile: InvestorProfile,
    observations: Sequence[Observation],
    decision_at: datetime,
    deliberate: Callable[[InvestorProfile, tuple[Observation, ...]], Proposal],
    *,
    profile_version: str,
    prompt_version: str,
) -> str:
    """Give injected deliberation only information available at decision time.

    Empty weights mean hold, never liquidation. Rejected and failed decisions
    preserve their status without applying allocations. Callback failures store
    only the exception class; arbitrary exception messages may contain secrets.
    """
    timestamp = _aware(decision_at)
    visible = [
        Observation(o.observed_at, o.source, dict(o.prices))
        for o in observations
        if _aware(o.observed_at) <= timestamp
    ]
    visible.sort(key=lambda o: o.observed_at)
    if not visible or not run_id or not profile_version or not prompt_version:
        raise ValueError("visible observations and explicit versions/run required")
    for o in visible:
        if not o.prices or any(not math.isfinite(p) or p <= 0 for p in o.prices.values()):
            raise ValueError("positive finite fixture prices required")
    record = {
        "id": uuid4().hex,
        "schema_version": 1,
        "run_id": run_id,
        "profile": asdict(profile),
        "profile_version": profile_version,
        "prompt_version": prompt_version,
        "decision_at": timestamp,
        "observations": [
            {"observed_at": _aware(o.observed_at), "source": o.source, "prices": dict(o.prices)}
            for o in visible
        ],
        "weights": {},
        "rationale": "",
        "uncertainty": "",
        "alternatives": [],
        "status": "failed",
        "risk_checks": [],
        "reason": "",
        "fill_assumptions": "fractional shares at fixture price; no fees/slippage; hold retains shares",
    }
    try:
        # A fresh copy protects recorded evidence from callback mutation.
        proposal = deliberate(
            profile, tuple(Observation(o.observed_at, o.source, dict(o.prices)) for o in visible)
        )
        weights = dict(proposal.weights)
        record.update(
            weights=weights,
            rationale=proposal.rationale,
            uncertainty=proposal.uncertainty,
            alternatives=list(proposal.alternatives),
        )
        valid = (
            math.isfinite(profile.max_position_pct)
            and 0 < profile.max_position_pct <= 100
            and all(
                s in visible[-1].prices
                and math.isfinite(w)
                and 0 <= w <= profile.max_position_pct / 100
                for s, w in weights.items()
            )
            and sum(weights.values()) <= 1.0
        )
        record["risk_checks"] = [
            "allocation limits passed" if valid else "allocation limits failed"
        ]
        record["status"] = "accepted" if valid and weights else "hold" if valid else "rejected"
        record["reason"] = (
            "target allocation" if valid and weights else "hold" if valid else "risk limit"
        )
        # Reject non-finite proposals without writing nonstandard JSON numbers.
        json.dumps(record, allow_nan=False)
    except Exception as exc:
        record.update(status="failed", weights={}, reason=type(exc).__name__)
    with store.connection:
        store.connection.execute(
            "INSERT INTO investor_decisions(id, run_id, record) VALUES (?, ?, ?)",
            (record["id"], run_id, json.dumps(record, allow_nan=False)),
        )
    return record["id"]


def outcomes(store: ConversationStore, decision_id: str) -> list[dict]:
    """Read outcome assessments linked to one decision, in recording order."""
    return [
        json.loads(row[0])
        for row in store.connection.execute(
            "SELECT record FROM investor_outcomes WHERE decision_id = ? ORDER BY rowid",
            (decision_id,),
        )
    ]


def assess(
    store: ConversationStore, decision_id: str, assessed_at: datetime, outcome: str, lessons: str
) -> None:
    """Append a later assessment without changing original evidence."""
    timestamp = _aware(assessed_at)
    row = store.connection.execute(
        "SELECT record FROM investor_decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    if row is None or timestamp < json.loads(row[0])["decision_at"]:
        raise ValueError("assessment requires an existing earlier decision")
    with store.connection:
        store.connection.execute(
            "INSERT INTO investor_outcomes(decision_id, record) VALUES (?, ?)",
            (
                decision_id,
                json.dumps({"assessed_at": timestamp, "outcome": outcome, "lessons": lessons}),
            ),
        )


def replay(store: ConversationStore, run_id: str) -> dict[str, ProfileResult]:
    """Replay saved decisions without invoking deliberation or reading assessments."""
    records = decisions(store, run_id)
    ticks: dict[str, list[dict]] = {}
    for record in records:
        ticks.setdefault(record["decision_at"], []).append(record)
    prices, allocations = [], []
    universe: set[str] | None = None
    for timestamp in sorted(ticks):
        entries = ticks[timestamp]
        snapshot = entries[0]["observations"][-1]["prices"]
        if universe is None:
            universe = set(snapshot)
        elif set(snapshot) != universe:
            raise ValueError("fixture symbol universe must remain fixed")
        if any(e["observations"] != entries[0]["observations"] for e in entries):
            raise ValueError("profiles must share identical fixture snapshots")
        if len({e["profile"]["name"] for e in entries}) != len(entries):
            raise ValueError("duplicate profile at decision time")
        prices.append(snapshot)
        allocations.append(
            {
                e["profile"]["name"]: (
                    {s: e["weights"].get(s, 0.0) for s in snapshot}
                    if e["status"] == "accepted"
                    else {}
                )
                for e in entries
            }
        )
    return evaluate(prices, allocations)
