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


def test_measured_tokens_round_trip(tmp_path) -> None:
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, clock=lambda: 1500.0)
    ledger.add_allowance(_grant())
    admission = ledger.admit(task_id="t1", task_class="run", estimated_cents=30, provider="meta")
    assert admission.reservation is not None
    ledger.settle(
        admission.reservation.id,
        actual_cents=20,
        model_id="m",
        input_tokens=100,
        output_tokens=10,
        usage_source="provider_reported",
    )
    ledger.settle_local(task_id="t2", task_class="run", input_tokens=5, usage_source="estimated")

    reopened = SpendLedger(path, clock=lambda: 1500.0)
    records = reopened.records()
    assert (records[0].input_tokens, records[0].output_tokens) == (100, 10)
    assert records[0].usage_source == "provider_reported"
    assert (records[1].input_tokens, records[1].output_tokens) == (5, None)
    assert records[1].usage_source == "estimated"


def test_pre_token_schema_migrates_in_place(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE allowances (id TEXT PRIMARY KEY, provider TEXT NOT NULL,"
        " kind TEXT NOT NULL, balance_cents INTEGER NOT NULL,"
        " granted_cents INTEGER NOT NULL, granted_at REAL NOT NULL, expires_at REAL)"
    )
    connection.execute(
        "CREATE TABLE reservations (id TEXT PRIMARY KEY, task_id TEXT NOT NULL,"
        " task_class TEXT NOT NULL, allowance_id TEXT NOT NULL,"
        " allowance_fingerprint TEXT NOT NULL, estimated_cents INTEGER NOT NULL,"
        " actual_cents INTEGER, state TEXT NOT NULL, created_at REAL NOT NULL,"
        " settled_at REAL)"
    )
    connection.execute(
        "CREATE TABLE records (rowid INTEGER PRIMARY KEY AUTOINCREMENT,"
        " task_id TEXT NOT NULL, task_class TEXT NOT NULL, model_id TEXT NOT NULL,"
        " provider TEXT NOT NULL, allowance_id TEXT, estimated_cents INTEGER NOT NULL,"
        " actual_cents INTEGER NOT NULL, duration_ms INTEGER NOT NULL,"
        " timestamp REAL NOT NULL)"
    )
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        "INSERT INTO records (task_id, task_class, model_id, provider, allowance_id,"
        " estimated_cents, actual_cents, duration_ms, timestamp)"
        " VALUES ('t0', 'run', 'm', 'meta', 'g1', 30, 20, 5, 1400.0)"
    )
    connection.commit()
    connection.close()

    ledger = SpendLedger(path, clock=lambda: 1500.0)
    (record,) = ledger.records()
    assert record.task_id == "t0"
    assert (record.input_tokens, record.output_tokens) == (None, None)
    assert record.usage_source == "unavailable"
    # New writes use the migrated columns.
    ledger.settle_local(task_id="t1", task_class="run", input_tokens=7, output_tokens=3)
    reopened = SpendLedger(path, clock=lambda: 1500.0)
    assert len(reopened.records()) == 2
    assert (reopened.records()[1].input_tokens, reopened.records()[1].output_tokens) == (7, 3)
