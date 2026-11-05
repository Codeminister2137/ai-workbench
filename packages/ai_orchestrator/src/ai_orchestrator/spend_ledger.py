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


class SpendLedger:
    """Single-writer P5 spend enforcement for one orchestrator process."""

    def __init__(
        self,
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

    def add_allowance(self, allowance: Allowance) -> None:
        """Register one grant bucket; invariants fail closed."""
        if allowance.id in self._allowances:
            raise ValueError(f"Duplicate allowance id: {allowance.id}")
        if allowance.balance_cents < 0 or allowance.granted_cents < 0:
            raise ValueError("Allowance balances must be non-negative")
        if allowance.balance_cents > allowance.granted_cents:
            raise ValueError("Allowance balance cannot exceed granted amount")
        self._allowances[allowance.id] = allowance

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
        )
        self._records.append(record)
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
        return reservation

    def settle_local(self, *, task_id: str, task_class: str) -> TaskSpendRecord:
        """Record one zero-cost local call that admitted without a grant."""
        record = TaskSpendRecord(
            task_id=task_id,
            task_class=task_class,
            model_id="",
            provider="local",
            allowance_id=None,
            estimated_cents=0,
            actual_cents=0,
            duration_ms=0,
            timestamp=self._clock(),
        )
        self._records.append(record)
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
        return {
            "buckets": buckets,
            "open_reservations": open_count,
            "records": len(self._records),
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
]
