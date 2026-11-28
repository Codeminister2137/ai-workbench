"""Bounded paper-trading loop (owner A on 472cea09; ADR-093).

Offline-pure: no network imports (see test_investor_stays_offline). A
BrokerTransport is injected; the Alpaca-paper HTTPS transport lives outside
this package (apps/ai_council/alpaca_paper.py). Every round journals exactly
one decision via investor.replay; loop-level submits, rejects and errors
attach as outcome assessments on the immutable decision. Any guard trip or
journal failure halts the loop (kill-switch): the halt is journaled and no
later invocation submits again on that run.

Day-scoped by design: one run_day call performs a single decision round and
derives trial state (day count, submitted orders, halt markers) from the
journal, so separate daily invocations need no daemon or sidecar state.
Market-notional orders need no price feed, keeping market-data endpoints
rejected per the slice-1 guards.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from storage import ConversationStore

from investor.guards import PaperGuardError, check_cost, check_endpoint
from investor.profiles import InvestorProfile
from investor.replay import Observation, Proposal, assess, decisions, outcomes, record_decision

DUST_NOTIONAL = 1.0


@dataclass(frozen=True)
class LoopBounds:
    """Owner-A trial bounds; anything outside fails closed and journals."""

    max_orders_per_day: int = 5
    max_notional_per_order: float = 1000.0
    max_open_exposure: float = 5000.0
    universe: tuple[str, ...] = ("SPY", "QQQ")
    max_days: int = 5


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str  # "buy" | "sell"
    notional: float


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: str
    notional: float
    avg_price: float


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    market_value: float


class BrokerTransport(Protocol):
    """Minimal broker surface the loop needs; implemented offline or HTTPS."""

    endpoint_url: str

    def cash(self) -> float:
        """Withdrawable cash; non-negative finite dollars."""
        ...  # pragma: no cover - protocol

    def positions(self) -> list[Position]:
        """Current open positions."""
        ...  # pragma: no cover - protocol

    def submit(self, intent: OrderIntent) -> Fill:
        """Fill a market-notional order; raise on broker refusal."""
        ...  # pragma: no cover - protocol


@dataclass
class DayReport:
    """Plain outcome of one run_day call; the journal is the audit trail."""

    date: str
    decision_id: str = ""
    submitted: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    held_reason: str = ""
    halted: bool = False
    halt_reason: str = ""


class OfflineBroker:
    """Deterministic fills at configured prices; no network, no secrets."""

    def __init__(
        self,
        prices: dict[str, float],
        *,
        cash: float = 100000.0,
        endpoint_url: str = "https://paper-api.alpaca.markets",
    ) -> None:
        check_endpoint(endpoint_url)
        if cash < 0 or not math.isfinite(cash):
            raise PaperGuardError(f"offline cash must be non-negative finite: {cash!r}")
        for symbol, price in prices.items():
            if not price or price <= 0 or not math.isfinite(price):
                raise PaperGuardError(f"offline price must be positive finite: {symbol!r}")
        self.endpoint_url = endpoint_url
        self._prices = dict(prices)
        self._cash = float(cash)
        self._shares: dict[str, float] = {}

    def cash(self) -> float:
        return self._cash

    def positions(self) -> list[Position]:
        return [
            Position(symbol, qty, qty * self._prices[symbol])
            for symbol, qty in sorted(self._shares.items())
            if qty > 0
        ]

    def submit(self, intent: OrderIntent) -> Fill:
        price = self._prices.get(intent.symbol.upper())
        if price is None:
            raise PaperGuardError(f"offline broker has no price for {intent.symbol!r}")
        if intent.side == "buy":
            if intent.notional > self._cash:
                raise PaperGuardError("offline broker refuses: insufficient cash")
            self._cash -= intent.notional
            self._shares[intent.symbol] = (
                self._shares.get(intent.symbol, 0.0) + intent.notional / price
            )
        elif intent.side == "sell":
            held = self._shares.get(intent.symbol, 0.0) * price
            if intent.notional - held > DUST_NOTIONAL:
                raise PaperGuardError("offline broker refuses: short sale")
            notional = min(intent.notional, held)
            self._cash += notional
            self._shares[intent.symbol] = max(0.0, (held - notional) / price)
            return Fill(intent.symbol, intent.side, notional, price)
        else:
            raise PaperGuardError(f"unknown side: {intent.side!r}")
        return Fill(intent.symbol, intent.side, intent.notional, price)


def _day_key(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware time required")
    return value.astimezone(UTC).date().isoformat()


def _assess_safely(
    store: ConversationStore, decision_id: str, at: datetime, outcome: str, lessons: str = ""
) -> bool:
    try:
        assess(store, decision_id, at, outcome, lessons)
    except Exception:
        return False
    return True


def _prior_halt(store: ConversationStore, run_id: str) -> str:
    """Return the first journaled halt marker for the run, or ''."""
    for record in decisions(store, run_id):
        for entry in outcomes(store, record["id"]):
            text = str(entry.get("outcome") or "")
            if text.startswith("halted:"):
                return text
    return ""


def _submitted_today(store: ConversationStore, run_id: str, today: str) -> int:
    """Count journaled submits assessed today across the run's decisions."""
    count = 0
    for record in decisions(store, run_id):
        for entry in outcomes(store, record["id"]):
            text = str(entry.get("outcome") or "")
            assessed = str(entry.get("assessed_at") or "")
            if text.startswith("submitted:") and assessed[:10] == today:
                count += 1
    return count


def _hold(
    store: ConversationStore,
    run_id: str,
    profile: InvestorProfile,
    observations: list[Observation],
    decision_at: datetime,
    reason: str,
    *,
    profile_version: str,
    prompt_version: str,
) -> str:
    def _stay_out(_profile: InvestorProfile, _seen: tuple[Observation, ...]) -> Proposal:
        return Proposal(weights={}, rationale=reason, uncertainty="n/a")

    return record_decision(
        store,
        run_id,
        profile,
        observations,
        decision_at,
        _stay_out,
        profile_version=profile_version,
        prompt_version=prompt_version,
    )


def run_day(
    store: ConversationStore,
    run_id: str,
    profile: InvestorProfile,
    bounds: LoopBounds,
    transport: BrokerTransport,
    deliberate: Callable[[InvestorProfile, tuple[Observation, ...]], Proposal],
    observations: list[Observation],
    decision_at: datetime,
    *,
    profile_version: str,
    prompt_version: str,
) -> DayReport:
    """Run one bounded decision round for the trial day containing decision_at.

    Journals exactly one decision per call. Returns halted (with the journaled
    reason) instead of raising when the trial is over, a prior halt exists, a
    guard trips, the broker refuses, or the journal itself fails.
    """
    today = _day_key(decision_at)
    report = DayReport(date=today)
    try:
        prior = decisions(store, run_id)
    except Exception as exc:
        report.halted = True
        report.halt_reason = f"journal unreadable: {type(exc).__name__}"
        return report
    halted_before = _prior_halt(store, run_id)
    if halted_before:
        try:
            report.decision_id = _hold(
                store,
                run_id,
                profile,
                observations,
                decision_at,
                f"loop halted earlier: {halted_before}",
                profile_version=profile_version,
                prompt_version=prompt_version,
            )
        except Exception as exc:
            report.halted = True
            report.halt_reason = f"journal failed: {type(exc).__name__}"
            return report
        report.halted = True
        report.halt_reason = halted_before
        return report
    distinct_days = {str(r.get("decision_at") or "")[:10] for r in prior}
    if len(distinct_days) >= bounds.max_days and today not in distinct_days:
        try:
            report.decision_id = _hold(
                store,
                run_id,
                profile,
                observations,
                decision_at,
                f"trial day limit reached ({bounds.max_days} days)",
                profile_version=profile_version,
                prompt_version=prompt_version,
            )
        except Exception as exc:
            report.halted = True
            report.halt_reason = f"journal failed: {type(exc).__name__}"
            return report
        _assess_safely(store, report.decision_id, decision_at, "halted: trial day limit reached")
        report.halted = True
        report.halt_reason = "halted: trial day limit reached"
        return report
    remaining = bounds.max_orders_per_day - _submitted_today(store, run_id, today)
    if remaining <= 0:
        try:
            report.decision_id = _hold(
                store,
                run_id,
                profile,
                observations,
                decision_at,
                f"day order cap reached ({bounds.max_orders_per_day}/day)",
                profile_version=profile_version,
                prompt_version=prompt_version,
            )
        except Exception as exc:
            report.halted = True
            report.halt_reason = f"journal failed: {type(exc).__name__}"
            return report
        report.held_reason = "day order cap reached"
        return report
    try:
        decision_id = record_decision(
            store,
            run_id,
            profile,
            observations,
            decision_at,
            deliberate,
            profile_version=profile_version,
            prompt_version=prompt_version,
        )
    except Exception as exc:
        report.halted = True
        report.halt_reason = f"journal failed: {type(exc).__name__}"
        return report
    report.decision_id = decision_id
    try:
        record = next(r for r in decisions(store, run_id) if r["id"] == decision_id)
    except Exception as exc:
        report.halted = True
        report.halt_reason = f"journal failed: {type(exc).__name__}"
        return report
    if record["status"] != "accepted":
        report.held_reason = f"decision {record['status']}: {record['reason']}"
        return report
    try:
        check_endpoint(transport.endpoint_url)
        cash = transport.cash()
        held = {p.symbol: p for p in transport.positions()}
    except PaperGuardError as exc:
        _assess_safely(store, decision_id, decision_at, f"rejected: guard: {exc}")
        _assess_safely(store, decision_id, decision_at, f"halted: guard: {exc}")
        report.halted = True
        report.halt_reason = f"halted: guard: {exc}"
        return report
    except Exception as exc:
        _assess_safely(store, decision_id, decision_at, f"error: {type(exc).__name__}")
        _assess_safely(store, decision_id, decision_at, f"halted: transport: {type(exc).__name__}")
        report.halted = True
        report.halt_reason = f"halted: transport: {type(exc).__name__}"
        return report
    if not math.isfinite(cash) or cash < 0:
        _assess_safely(store, decision_id, decision_at, "rejected: guard: bad cash")
        _assess_safely(store, decision_id, decision_at, "halted: guard: bad cash")
        report.halted = True
        report.halt_reason = "halted: guard: bad cash"
        return report
    equity = cash + sum(p.market_value for p in held.values())
    exposure = sum(abs(p.market_value) for p in held.values())
    intents: list[OrderIntent] = []
    for symbol in sorted(record["weights"]):
        weight = record["weights"][symbol]
        if symbol not in bounds.universe:
            report.rejected.append(f"{symbol}: outside universe")
            _assess_safely(store, decision_id, decision_at, f"rejected: universe: {symbol}")
            continue
        delta = weight * equity - held.get(symbol, Position(symbol, 0.0, 0.0)).market_value
        if abs(delta) < DUST_NOTIONAL:
            continue
        intents.append(OrderIntent(symbol, "buy" if delta > 0 else "sell", abs(delta)))
    for intent in intents:
        if remaining <= 0:
            report.rejected.append(f"{intent.symbol}: day order cap reached")
            _assess_safely(store, decision_id, decision_at, "rejected: day-cap: " + intent.symbol)
            continue
        if intent.notional > bounds.max_notional_per_order:
            report.rejected.append(f"{intent.symbol}: exceeds per-order cap")
            _assess_safely(
                store, decision_id, decision_at, f"rejected: per-order-cap: {intent.symbol}"
            )
            continue
        if (
            intent.side == "sell"
            and intent.notional
            - held.get(intent.symbol, Position(intent.symbol, 0.0, 0.0)).market_value
            > DUST_NOTIONAL
        ):
            report.rejected.append(f"{intent.symbol}: short sale refused")
            _assess_safely(
                store, decision_id, decision_at, f"rejected: short-sale: {intent.symbol}"
            )
            continue
        if intent.side == "buy" and exposure + intent.notional > bounds.max_open_exposure:
            report.rejected.append(f"{intent.symbol}: exposure cap reached")
            _assess_safely(
                store, decision_id, decision_at, f"rejected: exposure-cap: {intent.symbol}"
            )
            continue
        try:
            check_cost(notional=intent.notional, max_notional=bounds.max_notional_per_order)
            fill = transport.submit(intent)
        except PaperGuardError as exc:
            report.rejected.append(f"{intent.symbol}: guard: {exc}")
            _assess_safely(store, decision_id, decision_at, f"rejected: guard: {exc}")
            _assess_safely(store, decision_id, decision_at, f"halted: guard: {exc}")
            report.halted = True
            report.halt_reason = f"halted: guard: {exc}"
            return report
        except Exception as exc:
            report.rejected.append(f"{intent.symbol}: broker: {type(exc).__name__}")
            _assess_safely(store, decision_id, decision_at, f"error: {type(exc).__name__}")
            _assess_safely(store, decision_id, decision_at, f"halted: broker: {type(exc).__name__}")
            report.halted = True
            report.halt_reason = f"halted: broker: {type(exc).__name__}"
            return report
        if intent.side == "buy":
            exposure += fill.notional
        else:
            exposure = max(0.0, exposure - fill.notional)
        remaining -= 1
        label = f"{fill.symbol} {fill.side} {fill.notional:.2f} @ {fill.avg_price:.2f}"
        report.submitted.append(label)
        _assess_safely(store, decision_id, decision_at, f"submitted: {label}")
    return report
