"""Paper-only guards for future connected Investor trials.

No network, no credentials, no orders here: pure fail-closed checks that a
future connected client (slice 2) must pass before any broker call. The paper
host and paper credential names are grounded in the 26.11 paper-account setup
($100k simulated, read-only probe green); anything else fails closed.
Market-data endpoints stay rejected until a read-only exception is reviewed.
Guard messages name hosts and sources, never secret values.
"""

from __future__ import annotations

import math

PAPER_TRADING_HOSTS = ("paper-api.alpaca.markets",)
LIVE_TRADING_HOSTS = ("api.alpaca.markets",)
PAPER_KEY_SOURCE = "ALPACA_PAPER_KEY_ID"
PAPER_SECRET_SOURCE = "ALPACA_PAPER_SECRET"


class PaperGuardError(ValueError):
    """A paper-only guard refused; the message names the violated rule."""


def _split_host(url: str) -> str:
    """Take the host from an https URL without network imports.

    The investor-offline test bans urllib/requests-style imports in this
    package, so authority parsing is manual and fail-closed: https only,
    no userinfo, no IP literals, 443 is the only accepted explicit port.
    """
    text = url.strip()
    scheme, sep, rest = text.partition("://")
    if not sep or scheme.lower() != "https":
        raise PaperGuardError(f"endpoint must use https: {url!r}")
    authority = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not authority:
        raise PaperGuardError(f"endpoint host missing: {url!r}")
    if "@" in authority:
        raise PaperGuardError("endpoint must not embed credentials")
    if authority.startswith("["):
        raise PaperGuardError(f"endpoint host not on the paper allowlist: {authority!r}")
    host, colon, port = authority.partition(":")
    if colon and port != "443":
        raise PaperGuardError(f"endpoint port refused (443 only): {port!r}")
    host = host.lower()
    if not host:
        raise PaperGuardError(f"endpoint host missing: {url!r}")
    return host


def check_endpoint(url: str) -> str:
    """Allow only https URLs on the paper trading host; return the host."""
    host = _split_host(url)
    if host in LIVE_TRADING_HOSTS:
        raise PaperGuardError(f"live trading host refused: {host}")
    if host not in PAPER_TRADING_HOSTS:
        raise PaperGuardError(f"endpoint host not on the paper allowlist: {host}")
    return host


def check_paper_credentials(
    *, key_id: str, key_source: str, secret: str, secret_source: str
) -> None:
    """Require non-empty paper credentials read from the paper-named sources."""
    if key_source != PAPER_KEY_SOURCE:
        raise PaperGuardError(f"key id must come from {PAPER_KEY_SOURCE}: {key_source!r}")
    if secret_source != PAPER_SECRET_SOURCE:
        raise PaperGuardError(f"secret must come from {PAPER_SECRET_SOURCE}: {secret_source!r}")
    if not key_id.strip() or not secret.strip():
        raise PaperGuardError("paper key id and secret must both be non-empty")


def _money(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaperGuardError(f"{name} must be a number: {value!r}")
    if not math.isfinite(value):
        raise PaperGuardError(f"{name} must be finite: {value!r}")
    return float(value)


def check_cost(*, notional: float, max_notional: float, fees: float = 0.0) -> None:
    """Keep a simulated order within its notional cap (boundary passes)."""
    notional = _money("notional", notional)
    max_notional = _money("max_notional", max_notional)
    fees = _money("fees", fees)
    if max_notional <= 0:
        raise PaperGuardError(f"max_notional must be positive: {max_notional!r}")
    if notional < 0 or fees < 0:
        raise PaperGuardError("notional and fees must be non-negative")
    if notional + fees > max_notional:
        raise PaperGuardError(f"notional {notional} + fees {fees} exceeds cap {max_notional}")
