"""Bounded investor loop: offline-harness proofs, no network, no secrets."""

from __future__ import annotations

import json
import urllib.error
from datetime import UTC, datetime, timedelta
from email.message import Message

import pytest
from alpaca_paper import HttpsTransport, PaperBrokerError
from investor.guards import PaperGuardError
from investor.loop import (
    BrokerTransport,
    DayReport,
    Fill,
    LoopBounds,
    OfflineBroker,
    OrderIntent,
    Position,
    run_day,
)
from investor.profiles import InvestorProfile
from investor.replay import Observation, Proposal, assess, decisions, outcomes
from storage import ConversationStore

NOW = datetime(2026, 11, 30, 10, 0, tzinfo=UTC)
PRICES = {"SPY": 500.0, "QQQ": 400.0, "AAA": 100.0}
BOUNDS = LoopBounds(
    max_orders_per_day=5,
    max_notional_per_order=1000.0,
    max_open_exposure=5000.0,
    universe=("SPY", "QQQ"),
    max_days=5,
)


def _profile() -> InvestorProfile:
    return InvestorProfile(
        name="tester",
        model="fixture",
        temperature=0.0,
        system_prompt="test",
        risk_posture="balanced",
        horizon="short_term",
    )


def _obs(prices: dict[str, float] | None = None) -> list[Observation]:
    return [Observation(NOW, "fixture:loop", dict(prices or PRICES))]


def _store(tmp_path, name: str = "loop.db") -> ConversationStore:
    return ConversationStore(tmp_path / name)


def _propose(weights: dict[str, float]):
    def _go(profile, seen) -> Proposal:
        assert profile.name == "tester"
        assert len(seen) == 1
        return Proposal(weights=dict(weights), rationale="test", uncertainty="low")

    return _go


def _round(store, weights, transport=None, *, bounds=BOUNDS, at=NOW, obs=None):
    return run_day(
        store,
        "run-loop",
        _profile(),
        bounds,
        transport or OfflineBroker(PRICES),
        _propose(weights),
        obs if obs is not None else _obs(),
        at,
        profile_version="p1",
        prompt_version="q1",
    )


def test_submit_within_bounds_journals_fill(tmp_path) -> None:
    broker = OfflineBroker(PRICES)
    report = _round(_store(tmp_path), {"SPY": 0.005}, broker)
    assert report.submitted == ["SPY buy 500.00 @ 500.00"]
    assert report.rejected == [] and not report.halted
    assert broker.cash() == pytest.approx(100000.0 - 500.0)
    assert broker.positions()[0].market_value == pytest.approx(500.0)


def test_submitted_assessment_links_decision(tmp_path) -> None:
    store = _store(tmp_path)
    report = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES))
    assert [o["outcome"] for o in outcomes(store, report.decision_id)] == [
        "submitted: SPY buy 500.00 @ 500.00"
    ]


def test_outside_universe_rejected_without_submit(tmp_path) -> None:
    store = _store(tmp_path)
    broker = OfflineBroker(PRICES)
    report = _round(store, {"AAA": 0.005}, broker)
    assert report.submitted == []
    assert report.rejected == ["AAA: outside universe"]
    assert broker.cash() == pytest.approx(100000.0)
    assert "rejected: universe: AAA" in [o["outcome"] for o in outcomes(store, report.decision_id)]


def test_per_order_cap_rejected(tmp_path) -> None:
    store = _store(tmp_path)
    report = _round(store, {"SPY": 0.05}, OfflineBroker(PRICES))
    assert report.submitted == []
    assert report.rejected == ["SPY: exceeds per-order cap"]
    assert "rejected: per-order-cap: SPY" in [
        o["outcome"] for o in outcomes(store, report.decision_id)
    ]


def test_per_order_boundary_passes(tmp_path) -> None:
    report = _round(_store(tmp_path), {"SPY": 0.01}, OfflineBroker(PRICES))
    assert report.submitted == ["SPY buy 1000.00 @ 500.00"]


def test_day_cap_holds_second_round(tmp_path) -> None:
    store = _store(tmp_path)
    bounds = LoopBounds(
        max_orders_per_day=1, max_notional_per_order=1000.0, max_open_exposure=5000.0
    )
    first = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES), bounds=bounds)
    assert len(first.submitted) == 1
    second = _round(store, {"QQQ": 0.005}, OfflineBroker(PRICES), bounds=bounds)
    assert second.submitted == []
    assert second.held_reason == "day order cap reached"
    assert decisions(store, "run-loop")[-1]["status"] == "hold"


def test_exposure_cap_rejected(tmp_path) -> None:
    store = _store(tmp_path)
    bounds = LoopBounds(
        max_orders_per_day=5, max_notional_per_order=1000.0, max_open_exposure=1500.0
    )
    broker = OfflineBroker(PRICES)
    _round(store, {"SPY": 0.01}, broker, bounds=bounds)
    report = _round(store, {"SPY": 0.01, "QQQ": 0.01}, broker, bounds=bounds)
    assert report.submitted == []
    assert report.rejected == ["QQQ: exposure cap reached"]


def test_full_closeout_sell(tmp_path) -> None:
    store = _store(tmp_path)
    broker = OfflineBroker(PRICES)
    broker.submit(OrderIntent("SPY", "buy", 500.0))
    report = _round(store, {"SPY": 0.0}, broker)
    assert report.submitted == ["SPY sell 500.00 @ 500.00"]
    over = _round(store, {"SPY": 0.0}, broker)
    assert over.submitted == []  # dust: nothing left to sell


def test_offline_broker_refuses_short_sale() -> None:
    broker = OfflineBroker(PRICES)
    with pytest.raises(PaperGuardError, match="short sale"):
        broker.submit(OrderIntent("SPY", "sell", 500.0))


def test_dust_skipped_silently(tmp_path) -> None:
    store = _store(tmp_path)
    broker = OfflineBroker(PRICES)
    report = _round(store, {"SPY": 0.000001}, broker)
    assert report.submitted == [] and report.rejected == []
    assert outcomes(store, report.decision_id) == []


def test_hold_proposal_submits_nothing(tmp_path) -> None:
    store = _store(tmp_path)
    report = _round(store, {}, OfflineBroker(PRICES))
    assert report.submitted == [] and report.held_reason.startswith("decision hold")


def test_rejected_proposal_submits_nothing(tmp_path) -> None:
    store = _store(tmp_path)
    report = _round(store, {"SPY": 2.0}, OfflineBroker(PRICES))
    assert report.submitted == [] and report.held_reason.startswith("decision rejected")


def test_failed_deliberation_journals_and_holds(tmp_path) -> None:
    store = _store(tmp_path)

    def _boom(profile, seen) -> Proposal:
        raise RuntimeError("model blew up")

    report = run_day(
        store,
        "run-loop",
        _profile(),
        BOUNDS,
        OfflineBroker(PRICES),
        _boom,
        _obs(),
        NOW,
        profile_version="p1",
        prompt_version="q1",
    )
    assert report.submitted == [] and report.held_reason == "decision failed: RuntimeError"


def test_bad_endpoint_halts_and_stays_halted(tmp_path) -> None:
    store = _store(tmp_path)

    class _Bad(BrokerTransport):
        endpoint_url = "https://example.com"

        def cash(self) -> float:
            raise AssertionError("unreachable")

        def positions(self) -> list[Position]:
            raise AssertionError("unreachable")

        def submit(self, intent: OrderIntent) -> Fill:
            raise AssertionError("must not submit past the guard")

    first = _round(store, {"SPY": 0.005}, _Bad())
    assert first.halted and first.submitted == []
    assert "halted: guard" in first.halt_reason
    second = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES))
    assert second.halted and second.submitted == []
    assert decisions(store, "run-loop")[-1]["status"] == "hold"


def test_broker_guard_error_halts(tmp_path) -> None:
    store = _store(tmp_path)

    class _Down(BrokerTransport):
        endpoint_url = "https://paper-api.alpaca.markets"

        def cash(self) -> float:
            return 100000.0

        def positions(self) -> list[Position]:
            return []

        def submit(self, intent: OrderIntent) -> Fill:
            raise PaperBrokerError("paper broker HTTP 500 on /v2/orders")

    report = _round(store, {"SPY": 0.005}, _Down())
    assert report.halted and report.submitted == []
    assert report.halt_reason == "halted: guard: paper broker HTTP 500 on /v2/orders"


def test_broker_unexpected_error_halts(tmp_path) -> None:
    store = _store(tmp_path)

    class _Buggy(BrokerTransport):
        endpoint_url = "https://paper-api.alpaca.markets"

        def cash(self) -> float:
            return 100000.0

        def positions(self) -> list[Position]:
            return []

        def submit(self, intent: OrderIntent) -> Fill:
            raise RuntimeError("connector bug")

    report = _round(store, {"SPY": 0.005}, _Buggy())
    assert report.halted and report.submitted == []
    assert report.halt_reason == "halted: broker: RuntimeError"


def test_trial_day_limit_halts(tmp_path) -> None:
    store = _store(tmp_path)
    bounds = LoopBounds(
        max_orders_per_day=5,
        max_notional_per_order=1000.0,
        max_open_exposure=5000.0,
        max_days=1,
    )
    first = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES), bounds=bounds)
    assert not first.halted
    day2 = NOW + timedelta(days=1)
    obs2 = [Observation(day2, "fixture:loop", dict(PRICES))]
    second = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES), bounds=bounds, at=day2, obs=obs2)
    assert second.halted and second.submitted == []
    assert second.halt_reason == "halted: trial day limit reached"


def test_journal_failure_halts_without_submit(tmp_path) -> None:
    store = _store(tmp_path)
    report = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES), obs=[])
    assert report.halted and report.submitted == []
    assert report.halt_reason == "journal failed: ValueError"
    assert report.decision_id == ""


def test_offline_deterministic(tmp_path) -> None:
    one = _round(_store(tmp_path, "a.db"), {"SPY": 0.005, "QQQ": 0.0025}, OfflineBroker(PRICES))
    two = _round(_store(tmp_path, "b.db"), {"SPY": 0.005, "QQQ": 0.0025}, OfflineBroker(PRICES))
    assert one.submitted == two.submitted
    assert one.submitted == ["QQQ buy 250.00 @ 400.00", "SPY buy 500.00 @ 500.00"]


def test_offline_rejects_live_host() -> None:
    with pytest.raises(PaperGuardError):
        OfflineBroker(PRICES, endpoint_url="https://api.alpaca.markets")


def test_outcomes_reader_round_trip(tmp_path) -> None:
    store = _store(tmp_path)
    report = _round(store, {"SPY": 0.005}, OfflineBroker(PRICES))
    assess(store, report.decision_id, NOW, "reviewed: ok", "none")
    assert [o["outcome"] for o in outcomes(store, report.decision_id)][-1] == "reviewed: ok"


def test_transport_constructor_validates() -> None:
    with pytest.raises(PaperGuardError):
        HttpsTransport(key_id="k", key_source="WRONG", secret="s", secret_source="S")
    with pytest.raises(PaperGuardError):
        HttpsTransport(
            key_id="k",
            key_source="ALPACA_PAPER_KEY_ID",
            secret="s",
            secret_source="ALPACA_PAPER_SECRET",
            endpoint_url="https://api.alpaca.markets",
        )
    with pytest.raises(PaperGuardError):
        HttpsTransport(
            key_id=" ",
            key_source="ALPACA_PAPER_KEY_ID",
            secret="s",
            secret_source="ALPACA_PAPER_SECRET",
        )


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _transport(monkeypatch, payload: object, seen: dict) -> HttpsTransport:
    def _fake(request, timeout=None):
        seen["url"] = request.full_url
        seen["data"] = json.loads(request.data.decode("utf-8")) if request.data else None
        seen["key"] = request.get_header("Apca-api-key-id")
        return _FakeResponse(payload)

    monkeypatch.setattr("alpaca_paper.urllib.request.urlopen", _fake)
    return HttpsTransport(
        key_id="KEY",
        key_source="ALPACA_PAPER_KEY_ID",
        secret="SECRET",
        secret_source="ALPACA_PAPER_SECRET",
    )


def test_transport_cash_and_positions(monkeypatch, tmp_path) -> None:
    seen: dict = {}
    transport = _transport(monkeypatch, {"cash": "12000.50"}, seen)
    assert transport.cash() == pytest.approx(12000.50)
    assert seen["url"].endswith("/v2/account")
    transport = _transport(
        monkeypatch,
        [{"symbol": "spy", "qty": "2", "market_value": "1000.00"}],
        seen,
    )
    assert transport.positions() == [Position("SPY", 2.0, 1000.0)]


def test_transport_submit_shape(monkeypatch, tmp_path) -> None:
    seen: dict = {}
    transport = _transport(
        monkeypatch,
        {"filled_qty": "2", "filled_avg_price": "500.00", "status": "filled"},
        seen,
    )
    fill = transport.submit(OrderIntent("SPY", "buy", 1000.0))
    assert fill == Fill("SPY", "buy", 1000.0, 500.0)
    assert seen["url"].endswith("/v2/orders")
    assert seen["data"] == {
        "symbol": "SPY",
        "notional": 1000.0,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }
    assert seen["key"] == "KEY"


def test_transport_http_error_hides_secrets(monkeypatch, tmp_path) -> None:
    def _boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", Message(), None)

    monkeypatch.setattr("alpaca_paper.urllib.request.urlopen", _boom)
    transport = HttpsTransport(
        key_id="KEY",
        key_source="ALPACA_PAPER_KEY_ID",
        secret="SECRET",
        secret_source="ALPACA_PAPER_SECRET",
    )
    with pytest.raises(PaperBrokerError, match="HTTP 401") as excinfo:
        transport.cash()
    assert "SECRET" not in str(excinfo.value)


def test_transport_unfilled_order_refused(monkeypatch, tmp_path) -> None:
    seen: dict = {}
    transport = _transport(
        monkeypatch, {"filled_qty": "0", "filled_avg_price": None, "status": "held"}, seen
    )
    with pytest.raises(PaperBrokerError, match="unfilled"):
        transport.submit(OrderIntent("SPY", "buy", 100.0))


def test_loop_reports_are_plain_and_complete(tmp_path) -> None:
    report = _round(_store(tmp_path), {"SPY": 0.005}, OfflineBroker(PRICES))
    assert isinstance(report, DayReport)
    assert report.date == "2026-11-30" and report.decision_id and not report.halted
