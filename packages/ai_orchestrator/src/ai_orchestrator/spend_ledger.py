"""Finite-grant spend ledger: the P5 allowance-enforcement prototype.

P5 data shapes (``Allowance``/``Reservation``/``TaskSpendRecord``/``PolicyRule``)
with the operator's proven metering mechanics: explicit finite grants loaded
from files (never inferred from a key), fingerprint-bound ledger rows, atomic
reserve-before-dispatch, settle-with-refund-delta, and deny-by-default
activation (no allowances exist until the owner grants one).

Spend order per call: free_daily, then allowance_expiring FIFO by earliest
expiry, then prepaid only with an explicit permission rule. One call bills
exactly one bucket. Metering lives above the provider adapters: adapters
never see grants.

Single-writer: own one ``SpendLedger`` per process (the orchestrator). Methods
are not thread-safe in this prototype.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

GRANT_FILE_MAX_BYTES = 8192
_GRANT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")


class AllowanceKind(StrEnum):
    """P5 bucket kinds in canonical spend order."""

    FREE_DAILY = "free_daily"
    EXPIRING = "allowance_expiring"
    PREPAID = "prepaid"


class ReservationState(StrEnum):
    """Lifecycle of one atomic cost reservation."""

    RESERVED = "reserved"
    COMMITTED = "committed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


@dataclass(slots=True)
class Allowance:
    """One finite grant bucket. Balances move only via reservations."""

    id: str
    provider: str
    kind: AllowanceKind
    balance_cents: int
    granted_cents: int
    granted_at: float
    expires_at: float | None

    def __post_init__(self) -> None:
        """Coerce the kind label; unknown kinds fail closed here."""
        object.__setattr__(self, "kind", AllowanceKind(self.kind))

    def is_expired(self, now: float) -> bool:
        """True once the expiry instant passes; prepaid never expires."""
        return self.expires_at is not None and now >= self.expires_at

    def status(self, now: float) -> str:
        """Derived status for dashboard views: active, exhausted, or expired."""
        if self.is_expired(now):
            return "expired"
        if self.balance_cents <= 0:
            return "exhausted"
        return "active"


@dataclass(slots=True)
class PolicyRule:
    """One prepaid-permission rule. Default global rule blocks prepaid."""

    scope: str = "global"
    prepaid_allowed: bool = False
    max_prepaid_cents_per_day: int | None = None


@dataclass(slots=True)
class Reservation:
    """One atomic hold of estimated cost against one allowance."""

    id: str
    task_id: str
    task_class: str
    allowance_id: str
    allowance_fingerprint: str
    estimated_cents: int
    actual_cents: int | None = None
    state: ReservationState = ReservationState.RESERVED
    created_at: float = 0.0
    settled_at: float | None = None


@dataclass(slots=True)
class TaskSpendRecord:
    """One append-only ledger line per settled call."""

    task_id: str
    task_class: str
    model_id: str
    provider: str
    allowance_id: str | None
    estimated_cents: int
    actual_cents: int
    duration_ms: int
    timestamp: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_source: str = "unavailable"


@dataclass(slots=True)
class Admission:
    """Orchestrator admission verdict for one call or task."""

    decision: str  # admitted | deferred | rejected
    reason: str | None = None
    reservation: Reservation | None = None
    allowance_id: str | None = None
    bucket: str | None = None


def allowance_fingerprint(allowance: Allowance) -> str:
    """Stable digest binding one grant's settings to its ledger rows."""
    canonical = json.dumps(
        {
            "id": allowance.id,
            "provider": allowance.provider,
            "kind": allowance.kind.value,
            "granted_cents": allowance.granted_cents,
            "expires_at": allowance.expires_at,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def allowance_from_file(path: str | Path) -> Allowance:
    """Read one explicit finite grant file; never infer an allowance from a key."""
    path = Path(path)
    if path.stat().st_size > GRANT_FILE_MAX_BYTES:
        raise ValueError("Grant configuration exceeds 8192 bytes")
    configuration = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise ValueError("Grant configuration must be a JSON object")
    if "provider_spend_cap_verified" in configuration:
        raise ValueError(
            "Legacy provider-cap grant refused; explicitly review local spending limits"
        )
    if configuration.get("local_spending_limit_accepted") is not True:
        raise ValueError(
            "Grant needs explicit acceptance of local spending limits "
            "(local_spending_limit_accepted: true)"
        )
    allowance_id = configuration.get("allowance_id")
    provider = configuration.get("provider")
    kind = configuration.get("kind")
    granted_cents = configuration.get("granted_cents")
    if not isinstance(allowance_id, str) or not _GRANT_ID_PATTERN.fullmatch(allowance_id):
        raise ValueError("Grant allowance_id must match [A-Za-z0-9_-]{1,80}")
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("Grant needs a provider")
    try:
        kind_value = AllowanceKind(str(kind))
    except ValueError:
        valid = ", ".join(item.value for item in AllowanceKind)
        raise ValueError(f"Grant kind must be one of: {valid}") from None
    if not isinstance(granted_cents, int) or granted_cents < 0:
        raise ValueError("Grant granted_cents must be a non-negative integer")
    expires_at = configuration.get("expires_at")
    if expires_at is not None and not isinstance(expires_at, (int, float)):
        raise ValueError("Grant expires_at must be a number or null")
    granted_at = configuration.get("granted_at", time.time())
    if not isinstance(granted_at, (int, float)):
        raise ValueError("Grant granted_at must be a number")
    return Allowance(
        id=allowance_id,
        provider=provider.strip(),
        kind=kind_value,
        balance_cents=granted_cents,
        granted_cents=granted_cents,
        granted_at=float(granted_at),
        expires_at=None if expires_at is None else float(expires_at),
    )


POLICY_FILE_MAX_BYTES = 8192
POLICY_RULE_KEYS = frozenset({"scope", "prepaid_allowed", "max_prepaid_cents_per_day"})


def policy_from_file(path: str | Path) -> list[PolicyRule]:
    """Read user prepaid-permission rules; unknown keys fail closed."""
    path = Path(path)
    if path.stat().st_size > POLICY_FILE_MAX_BYTES:
        raise ValueError("Spend policy exceeds 8192 bytes")
    configuration = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise ValueError("Spend policy must be a JSON object")
    unknown_doc = sorted(set(configuration) - {"rules"})
    if unknown_doc:
        raise ValueError(f"Unknown spend policy keys: {unknown_doc}")
    raw_rules = configuration.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError("Spend policy rules must be a list")
    rules: list[PolicyRule] = []
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"Rule #{index} must be an object")
        unknown = sorted(set(raw) - POLICY_RULE_KEYS)
        if unknown:
            raise ValueError(f"Rule #{index} unknown keys: {unknown}")
        scope = raw.get("scope", "global")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError(f"Rule #{index} needs a scope")
        allowed = raw.get("prepaid_allowed", False)
        if not isinstance(allowed, bool):
            raise ValueError(f"Rule #{index} prepaid_allowed must be boolean")
        cap = raw.get("max_prepaid_cents_per_day")
        if cap is not None and (not isinstance(cap, int) or cap < 0):
            raise ValueError(f"Rule #{index} cap must be a non-negative integer")
        rules.append(
            PolicyRule(
                scope=scope,
                prepaid_allowed=allowed,
                max_prepaid_cents_per_day=cap,
            )
        )
    return rules


class SpendLedger:
    """Single-writer P5 spend enforcement for one orchestrator process.

    ``path`` enables SQLite durability: state loads on open and persists
    after every mutation. ``None`` keeps the original in-memory behavior.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        rules: list[PolicyRule] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._rules = list(rules) if rules else [PolicyRule()]
        self._clock = clock
        self._allowances: dict[str, Allowance] = {}
        self._reservations: dict[str, Reservation] = {}
        self._records: list[TaskSpendRecord] = []
        self._reservation_seq = 0
        self._prepaid_spent_by_day: dict[str, int] = {}
        self._path = Path(path) if path is not None else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def _connect(self) -> sqlite3.Connection:
        assert self._path is not None
        # Concurrent readers/writers (server ledger + per-drain ledgers)
        # serialize here; only the server STT ledger mutates balances.
        connection = sqlite3.connect(self._path, timeout=30.0)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS allowances (
                id TEXT PRIMARY KEY, provider TEXT NOT NULL, kind TEXT NOT NULL,
                balance_cents INTEGER NOT NULL, granted_cents INTEGER NOT NULL,
                granted_at REAL NOT NULL, expires_at REAL)
            """
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL, task_class TEXT NOT NULL,
                allowance_id TEXT NOT NULL, allowance_fingerprint TEXT NOT NULL,
                estimated_cents INTEGER NOT NULL, actual_cents INTEGER,
                state TEXT NOT NULL, created_at REAL NOT NULL, settled_at REAL)
            """
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS records (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                task_class TEXT NOT NULL, model_id TEXT NOT NULL, provider TEXT NOT NULL,
                allowance_id TEXT, estimated_cents INTEGER NOT NULL,
                actual_cents INTEGER NOT NULL, duration_ms INTEGER NOT NULL,
                timestamp REAL NOT NULL, input_tokens INTEGER,
                output_tokens INTEGER,
                usage_source TEXT NOT NULL DEFAULT 'unavailable')
            """
        )
        # Pre-token ledgers predate the metering columns; backfill in place.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(records)").fetchall()}
        if "input_tokens" not in columns:
            connection.execute("ALTER TABLE records ADD COLUMN input_tokens INTEGER")
        if "output_tokens" not in columns:
            connection.execute("ALTER TABLE records ADD COLUMN output_tokens INTEGER")
        if "usage_source" not in columns:
            connection.execute(
                "ALTER TABLE records ADD COLUMN usage_source TEXT NOT NULL DEFAULT 'unavailable'"
            )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        return connection

    def _save(self) -> None:
        if self._path is None:
            return
        connection = self._connect()
        with connection:
            connection.execute("DELETE FROM allowances")
            connection.executemany(
                "INSERT INTO allowances VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        row.id,
                        row.provider,
                        row.kind.value,
                        row.balance_cents,
                        row.granted_cents,
                        row.granted_at,
                        row.expires_at,
                    )
                    for row in self._allowances.values()
                ],
            )
            connection.execute("DELETE FROM reservations")
            connection.executemany(
                "INSERT INTO reservations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.id,
                        item.task_id,
                        item.task_class,
                        item.allowance_id,
                        item.allowance_fingerprint,
                        item.estimated_cents,
                        item.actual_cents,
                        item.state.value,
                        item.created_at,
                        item.settled_at,
                    )
                    for item in self._reservations.values()
                ],
            )
            connection.execute("DELETE FROM records")
            connection.executemany(
                "INSERT INTO records (task_id, task_class, model_id, provider,"
                " allowance_id, estimated_cents, actual_cents, duration_ms,"
                " timestamp, input_tokens, output_tokens, usage_source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        record.task_id,
                        record.task_class,
                        record.model_id,
                        record.provider,
                        record.allowance_id,
                        record.estimated_cents,
                        record.actual_cents,
                        record.duration_ms,
                        record.timestamp,
                        record.input_tokens,
                        record.output_tokens,
                        record.usage_source,
                    )
                    for record in self._records
                ],
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta VALUES "
                "('reservation_seq', ?), ('prepaid_spent_by_day', ?)",
                (
                    str(self._reservation_seq),
                    json.dumps(self._prepaid_spent_by_day, sort_keys=True),
                ),
            )
        connection.close()

    def _load(self) -> None:
        assert self._path is not None
        connection = self._connect()
        try:
            for row in connection.execute(
                "SELECT id, provider, kind, balance_cents, granted_cents,"
                " granted_at, expires_at FROM allowances"
            ):
                allowance = Allowance(
                    id=row[0],
                    provider=row[1],
                    kind=row[2],
                    balance_cents=row[3],
                    granted_cents=row[4],
                    granted_at=row[5],
                    expires_at=row[6],
                )
                self._allowances[allowance.id] = allowance
            for row in connection.execute(
                "SELECT id, task_id, task_class, allowance_id,"
                " allowance_fingerprint, estimated_cents, actual_cents, state,"
                " created_at, settled_at FROM reservations"
            ):
                item = Reservation(
                    id=row[0],
                    task_id=row[1],
                    task_class=row[2],
                    allowance_id=row[3],
                    allowance_fingerprint=row[4],
                    estimated_cents=row[5],
                    actual_cents=row[6],
                    state=ReservationState(row[7]),
                    created_at=row[8],
                    settled_at=row[9],
                )
                self._reservations[item.id] = item
            for row in connection.execute(
                "SELECT task_id, task_class, model_id, provider, allowance_id,"
                " estimated_cents, actual_cents, duration_ms, timestamp,"
                " input_tokens, output_tokens, usage_source"
                " FROM records ORDER BY rowid ASC"
            ):
                self._records.append(TaskSpendRecord(*row))
            meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
            self._reservation_seq = int(meta.get("reservation_seq", "0"))
            self._prepaid_spent_by_day = {
                day: int(cents)
                for day, cents in json.loads(meta.get("prepaid_spent_by_day", "{}")).items()
            }
        finally:
            connection.close()

    def add_allowance(self, allowance: Allowance) -> None:
        """Register one grant bucket; invariants fail closed."""
        if allowance.id in self._allowances:
            raise ValueError(f"Duplicate allowance id: {allowance.id}")
        if allowance.balance_cents < 0 or allowance.granted_cents < 0:
            raise ValueError("Allowance balances must be non-negative")
        if allowance.balance_cents > allowance.granted_cents:
            raise ValueError("Allowance balance cannot exceed granted amount")
        self._allowances[allowance.id] = allowance
        self._save()

    def get_allowance(self, allowance_id: str) -> Allowance:
        """Return one live allowance row (the single-writer mutation point)."""
        return self._allowances[allowance_id]

    def records(self) -> tuple[TaskSpendRecord, ...]:
        """Return the append-only spend records oldest-first."""
        return tuple(self._records)

    def _prepaid_permitted(self, provider: str, estimated_cents: int) -> bool:
        """True when any matching rule allows prepaid within its day cap."""
        day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        spent = self._prepaid_spent_by_day.get(day, 0)
        for rule in self._rules:
            if not rule.prepaid_allowed:
                continue
            if rule.scope not in ("global", provider):
                continue
            cap = rule.max_prepaid_cents_per_day
            if cap is not None and spent + estimated_cents > cap:
                continue
            return True
        return False

    def _candidates(self, provider: str) -> list[Allowance]:
        """Spend-ordered usable buckets: free, expiring FIFO, prepaid gated."""
        now = self._clock()
        usable = [
            row
            for row in self._allowances.values()
            if row.provider == provider and not row.is_expired(now) and row.balance_cents > 0
        ]
        free = [row for row in usable if row.kind is AllowanceKind.FREE_DAILY]
        expiring = sorted(
            (row for row in usable if row.kind is AllowanceKind.EXPIRING),
            key=lambda row: row.expires_at if row.expires_at is not None else float("inf"),
        )
        return [*free, *expiring]

    def _hold(
        self, row: Allowance, task_id: str, task_class: str, estimated_cents: int
    ) -> Reservation:
        """Deduct one estimate and record its fingerprint-bound reservation."""
        row.balance_cents -= estimated_cents
        self._reservation_seq += 1
        reservation = Reservation(
            id=f"rsv-{self._reservation_seq}",
            task_id=task_id,
            task_class=task_class,
            allowance_id=row.id,
            allowance_fingerprint=allowance_fingerprint(row),
            estimated_cents=estimated_cents,
            created_at=self._clock(),
        )
        self._reservations[reservation.id] = reservation
        self._save()
        return reservation

    def admit(
        self,
        *,
        task_id: str,
        task_class: str,
        estimated_cents: int,
        provider: str,
    ) -> Admission:
        """Admit one call, atomically reserving its estimate on success.

        Zero-cost local calls admit without a grant. Anything billable needs
        a fitting bucket; prepaid without permission defers, and estimates no
        grant could ever cover reject.
        """
        if estimated_cents < 0:
            raise ValueError("Estimated cost cannot be negative")
        if estimated_cents == 0:
            return Admission(decision="admitted", bucket="local_free")
        for row in self._candidates(provider):
            if row.balance_cents < estimated_cents:
                continue
            reservation = self._hold(row, task_id, task_class, estimated_cents)
            return Admission(
                decision="admitted",
                reservation=reservation,
                allowance_id=row.id,
                bucket=row.kind.value,
            )
        prepaid_exists = any(
            row.provider == provider
            and row.kind is AllowanceKind.PREPAID
            and not row.is_expired(self._clock())
            for row in self._allowances.values()
        )
        if prepaid_exists:
            if self._prepaid_permitted(provider, estimated_cents):
                for row in self._allowances.values():
                    if (
                        row.provider == provider
                        and row.kind is AllowanceKind.PREPAID
                        and not row.is_expired(self._clock())
                        and row.balance_cents >= estimated_cents
                    ):
                        reservation = self._hold(row, task_id, task_class, estimated_cents)
                        return Admission(
                            decision="admitted",
                            reservation=reservation,
                            allowance_id=row.id,
                            bucket=row.kind.value,
                        )
            return Admission(decision="deferred", reason="awaiting_prepaid_permission")
        now = self._clock()
        satisfiable = any(
            row.provider == provider
            and not row.is_expired(now)
            and row.granted_cents >= estimated_cents
            for row in self._allowances.values()
        )
        if satisfiable:
            return Admission(decision="deferred", reason="insufficient_allowance")
        return Admission(decision="rejected", reason="estimate_exceeds_all_grants")

    def settle(
        self,
        reservation_id: str,
        *,
        actual_cents: int,
        model_id: str = "",
        duration_ms: int = 0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        usage_source: str = "unavailable",
    ) -> TaskSpendRecord:
        """Commit one reservation: refund the estimate-actual delta, append the record."""
        if actual_cents < 0:
            raise ValueError("Actual cost cannot be negative")
        reservation = self._reservations.get(reservation_id)
        if reservation is None or reservation.state is not ReservationState.RESERVED:
            raise ValueError(f"Reservation is not open: {reservation_id}")
        row = self._allowances.get(reservation.allowance_id)
        if row is None or row.is_expired(self._clock()):
            reservation.state = ReservationState.EXPIRED
            reservation.settled_at = self._clock()
            raise ValueError("Allowance expired before settlement; estimate kept")
        if allowance_fingerprint(row) != reservation.allowance_fingerprint:
            raise ValueError("Grant changed while reserved; settlement refused")
        if actual_cents > reservation.estimated_cents:
            overrun = actual_cents - reservation.estimated_cents
            row.balance_cents = max(0, row.balance_cents - overrun)
        else:
            row.balance_cents += reservation.estimated_cents - actual_cents
        reservation.actual_cents = actual_cents
        reservation.state = ReservationState.COMMITTED
        reservation.settled_at = self._clock()
        if row.kind is AllowanceKind.PREPAID:
            day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
            self._prepaid_spent_by_day[day] = self._prepaid_spent_by_day.get(day, 0) + actual_cents
        record = TaskSpendRecord(
            task_id=reservation.task_id,
            task_class=reservation.task_class,
            model_id=model_id,
            provider=row.provider,
            allowance_id=row.id,
            estimated_cents=reservation.estimated_cents,
            actual_cents=actual_cents,
            duration_ms=duration_ms,
            timestamp=self._clock(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_source=usage_source,
        )
        self._records.append(record)
        self._save()
        return record

    def refund(self, reservation_id: str) -> Reservation:
        """Cancel one open reservation, restoring its full estimate."""
        reservation = self._reservations.get(reservation_id)
        if reservation is None or reservation.state is not ReservationState.RESERVED:
            raise ValueError(f"Reservation is not open: {reservation_id}")
        row = self._allowances.get(reservation.allowance_id)
        if row is not None:
            row.balance_cents = min(
                row.granted_cents, row.balance_cents + reservation.estimated_cents
            )
        reservation.state = ReservationState.REFUNDED
        reservation.settled_at = self._clock()
        self._save()
        return reservation

    def settle_local(
        self,
        *,
        task_id: str,
        task_class: str,
        model_id: str = "",
        provider: str = "local",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        usage_source: str = "unavailable",
    ) -> TaskSpendRecord:
        """Record one zero-marginal-cost call that admitted without a grant.

        ``model_id``/``provider`` attribute the record (free/allowance routes);
        measured token usage rides along when the caller has it.
        """
        record = TaskSpendRecord(
            task_id=task_id,
            task_class=task_class,
            model_id=model_id,
            provider=provider,
            allowance_id=None,
            estimated_cents=0,
            actual_cents=0,
            duration_ms=0,
            timestamp=self._clock(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_source=usage_source,
        )
        self._records.append(record)
        self._save()
        return record

    def status(self) -> dict[str, object]:
        """Derived dashboard view: remaining by bucket plus open counts."""
        now = self._clock()
        buckets = [
            {
                "id": row.id,
                "provider": row.provider,
                "kind": row.kind.value,
                "balance_cents": row.balance_cents,
                "granted_cents": row.granted_cents,
                "status": row.status(now),
                "expires_at": row.expires_at,
            }
            for row in self._allowances.values()
        ]
        open_count = sum(
            1 for item in self._reservations.values() if item.state is ReservationState.RESERVED
        )
        by_operation: dict[str, dict[str, int]] = {}
        for record in self._records:
            slot = by_operation.setdefault(record.task_class, {"calls": 0, "actual_cents": 0})
            slot["calls"] += 1
            slot["actual_cents"] += record.actual_cents
        day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        return {
            "buckets": buckets,
            "open_reservations": open_count,
            "records": len(self._records),
            "by_operation": by_operation,
            "policy": {
                "spend_order": [
                    "free_daily",
                    "allowance_expiring (soonest first)",
                    "prepaid (only when a rule permits)",
                ],
                "rules": [
                    {
                        "scope": rule.scope,
                        "prepaid_allowed": rule.prepaid_allowed,
                        "max_prepaid_cents_per_day": rule.max_prepaid_cents_per_day,
                    }
                    for rule in self._rules
                ],
                "prepaid_spent_today_cents": self._prepaid_spent_by_day.get(day, 0),
            },
        }


__all__ = [
    "Admission",
    "Allowance",
    "AllowanceKind",
    "PolicyRule",
    "Reservation",
    "ReservationState",
    "SpendLedger",
    "TaskSpendRecord",
    "allowance_fingerprint",
    "allowance_from_file",
    "policy_from_file",
]
