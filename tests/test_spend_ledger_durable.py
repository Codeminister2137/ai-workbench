"""Durable ledger: SQLite round-trip + attributed local settle."""

from __future__ import annotations

from ai_orchestrator.spend_ledger import (
    Allowance,
    AllowanceKind,
    SpendLedger,
)


def _grant(**overrides) -> Allowance:
    values = {
        "id": "g1",
        "provider": "meta",
        "kind": AllowanceKind.EXPIRING,
        "balance_cents": 100,
        "granted_cents": 100,
        "granted_at": 1000.0,
        "expires_at": 2000.0,
    }
    values.update(overrides)
    return Allowance(**values)


def test_round_trip_preserves_state(tmp_path) -> None:
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, clock=lambda: 1500.0)
    ledger.add_allowance(_grant())
    admission = ledger.admit(task_id="t1", task_class="run", estimated_cents=30, provider="meta")
    assert admission.reservation is not None
    ledger.settle(admission.reservation.id, actual_cents=20, model_id="m", duration_ms=5)
    ledger.settle_local(task_id="t2", task_class="run", model_id="m2", provider="ollama")

    reopened = SpendLedger(path, clock=lambda: 1500.0)
    assert reopened.get_allowance("g1").balance_cents == 80
    records = reopened.records()
    assert len(records) == 2
    assert records[0].actual_cents == 20
    assert (records[1].model_id, records[1].provider) == ("m2", "ollama")
    # Sequence continues past the persisted counter (no id reuse).
    followup = reopened.admit(task_id="t3", task_class="run", estimated_cents=10, provider="meta")
    assert followup.reservation is not None
    assert followup.reservation.id == "rsv-2"


def test_memory_mode_unchanged_without_path() -> None:
    ledger = SpendLedger(clock=lambda: 1500.0)
    ledger.add_allowance(_grant())
    ledger.settle_local(task_id="t1", task_class="run")
    assert ledger.get_allowance("g1").balance_cents == 100
    assert len(ledger.records()) == 1


def test_attributed_settle_defaults() -> None:
    ledger = SpendLedger()
    record = ledger.settle_local(task_id="t1", task_class="run")
    assert (record.model_id, record.provider) == ("", "local")
