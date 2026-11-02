"""Owner-funded finite judge pool: explicit amount, disabled until granted.

A judge pool is one finite owner-approved allowance (request count plus USD
cap) shared by judge subjects. This module is the inert slice only: it parses
an explicit pool configuration, keeps admission disabled until a grant is
attached, and reuses the shared-ledger reservation accounting in
``Store.reserve_allowance``. It is NOT wired into the hosted app, deployment
or Modal entry point, reads no environment, and activates nothing. The pool
amount and any activation both need explicit owner approval (see DESIGN.md).
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from remote_operator.control import digest
from remote_operator.store import Store

GRANT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")
MODEL_PATTERN = re.compile(r"muse-[a-z0-9.-]+")
SUBJECT_PREFIX = "judge-"
MAX_REQUESTS_LIMIT = 100


class PoolDisabled(ValueError):
    """The funded judge path is disabled: no pool grant is attached."""

    def __init__(self, detail="Judge pool is disabled; no pool grant is attached"):
        super().__init__(detail)


@dataclass(frozen=True)
class JudgePoolConfig:
    """Explicit pool amount. Every field is required; there are no defaults.

    ``approved_usd`` is a decimal string so USD parsing matches the existing
    allowance ledger exactly. ``expires_at`` is epoch seconds. The model names
    the server route the pool may fund; contributor/training access is refused.
    """

    grant_id: str
    model: str
    expires_at: float
    max_requests: int
    approved_usd: str

    def check(self, *, now=None):
        """Validate every field; raises ValueError on anything unusable."""
        current = time.time() if now is None else now
        if not isinstance(self.grant_id, str) or not GRANT_ID_PATTERN.fullmatch(self.grant_id):
            raise ValueError("Pool grant_id must match [A-Za-z0-9_-]{1,80}")
        if (
            not isinstance(self.model, str)
            or not MODEL_PATTERN.fullmatch(self.model)
            or "contributor" in self.model
        ):
            raise ValueError("Pool model must name a non-contributor muse-* route")
        if not isinstance(self.expires_at, (int, float)) or not math.isfinite(self.expires_at):
            raise ValueError("Pool expires_at must be a finite epoch timestamp")
        if self.expires_at <= current:
            raise ValueError("Pool grant expired")
        if type(self.max_requests) is not int or not 1 <= self.max_requests <= MAX_REQUESTS_LIMIT:
            raise ValueError("Pool max_requests must be an integer between 1 and 100")
        try:
            budget = (
                Decimal(self.approved_usd) if isinstance(self.approved_usd, str) else Decimal("nan")
            )
        except InvalidOperation:
            raise ValueError("Pool approved_usd must be a decimal string") from None
        if not budget.is_finite() or budget <= 0:
            raise ValueError("Pool approved_usd must be positive and finite")

    def fingerprint(self):
        """Canonical digest pinning these exact pool settings in the ledger."""
        return digest(json.dumps(asdict(self), sort_keys=True))


def pool_config_from_mapping(mapping):
    """Build a validated config from an explicit mapping; never infer amounts.

    Every amount field must be present. Raises ValueError naming the missing
    or invalid field. The caller supplies the mapping (for example parsed
    JSON); this function reads no environment and applies no defaults.
    """
    if not isinstance(mapping, dict):
        raise TypeError("Pool configuration must be a mapping")
    missing = [
        name
        for name in ("grant_id", "model", "expires_at", "max_requests", "approved_usd")
        if name not in mapping
    ]
    if missing:
        raise ValueError("Pool configuration is missing: " + ", ".join(sorted(missing)))
    config = JudgePoolConfig(
        grant_id=mapping["grant_id"],
        model=mapping["model"],
        expires_at=mapping["expires_at"],
        max_requests=mapping["max_requests"],
        approved_usd=mapping["approved_usd"],
    )
    config.check()
    return config


class JudgePool:
    """Admit judge subjects against one shared finite pool ledger.

    The pool holds at most one grant. Until ``attach_grant`` stores a validated
    config, ``effective`` returns None, ``reserve`` raises ``PoolDisabled`` and
    ``status`` reports disabled, so the funded judge path stays off. The ledger
    is one shared ``Store`` (one pool file for all judges); every reservation
    reuses ``Store.reserve_allowance``, inheriting fingerprint pinning,
    exhaustion refusal and consumed-on-failure semantics. Single-writer
    deployments pass their volume commit as the ledger's ``after_commit``.
    """

    def __init__(self, ledger: Store):
        self._ledger = ledger
        self._grant = None
        self._lock = threading.RLock()

    def attach_grant(self, config: JudgePoolConfig):
        """Store a validated pool grant; refuses to change consumed settings."""
        config.check()
        with self._lock:
            if self._grant is not None and self._grant.fingerprint() != config.fingerprint():
                raise ValueError("Consumed pool settings cannot be changed")
            self._grant = config
            return config

    def effective(self, subject: str, *, now=None):
        """Return the pool grant for a judge subject, or None when unusable.

        Anonymous visitors always read None. A missing, expired or
        future-dated grant reads as None so callers fall back to the existing
        unfunded path instead of raising inside admission.
        """
        if not isinstance(subject, str) or not subject.startswith(SUBJECT_PREFIX):
            return None
        with self._lock:
            grant = self._grant
        if grant is None:
            return None
        current = time.time() if now is None else now
        if (
            not isinstance(grant.expires_at, (int, float))
            or not math.isfinite(grant.expires_at)
            or grant.expires_at <= current
        ):
            return None
        return grant

    def reserve(self, subject: str, reservation_usd: str):
        """Consume one shared pool request before sending; judges only.

        Raises ``PoolDisabled`` when no usable grant is attached and the
        ledger's ``ValueError`` when the pool is exhausted or its settings
        changed after consumption. Failed calls remain consumed, exactly as in
        the per-subject ledger.
        """
        admitted = self.effective(subject)
        if admitted is None:
            raise PoolDisabled()
        return self._ledger.reserve_allowance(
            admitted.grant_id,
            admitted.fingerprint(),
            admitted.max_requests,
            reservation_usd,
            admitted.approved_usd,
        )

    def status(self):
        """Return the shared pool allowance view without consuming a request."""
        with self._lock:
            grant = self._grant
        if grant is None:
            return {"enabled": False, "scope": "judge_pool"}
        return {
            "enabled": True,
            "scope": "judge_pool",
            "model": grant.model,
            "expires_at": grant.expires_at,
            **self._ledger.allowance_status(
                grant.grant_id,
                grant.fingerprint(),
                grant.max_requests,
                grant.approved_usd,
            ),
        }
