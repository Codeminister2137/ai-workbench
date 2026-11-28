"""Alpaca paper broker transport for the investor loop (slice 2).

Single-broker adapter per ADR-093: paper host only, credentials from the
paper-named sources only. Guard checks run at construction and before every
call; secrets never appear in errors, records, or assessments. Plain urllib,
no third-party HTTP client. Submit uses market-notional orders so no price
feed (and no market-data exception) is needed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from investor.guards import (
    PAPER_KEY_SOURCE,
    PAPER_SECRET_SOURCE,
    PaperGuardError,
    check_endpoint,
    check_paper_credentials,
)
from investor.loop import Fill, OrderIntent, Position


class PaperBrokerError(PaperGuardError):
    """The paper broker refused or failed; status only, never secrets."""


class HttpsTransport:
    """Alpaca paper REST transport implementing the loop's broker protocol."""

    def __init__(
        self,
        *,
        key_id: str,
        key_source: str,
        secret: str,
        secret_source: str,
        endpoint_url: str = "https://paper-api.alpaca.markets",
        timeout: float = 20.0,
    ) -> None:
        check_endpoint(endpoint_url)
        check_paper_credentials(
            key_id=key_id, key_source=key_source, secret=secret, secret_source=secret_source
        )
        self.endpoint_url = endpoint_url.rstrip("/")
        self._key_id = key_id
        self._secret = secret
        self._timeout = timeout

    @property
    def credential_sources(self) -> tuple[str, str]:
        return (PAPER_KEY_SOURCE, PAPER_SECRET_SOURCE)

    def _request(self, method: str, path: str, payload: dict | None = None) -> object:
        check_endpoint(self.endpoint_url)
        body = None
        headers = {
            "APCA-API-KEY-ID": self._key_id,
            "APCA-API-SECRET-KEY": self._secret,
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.endpoint_url + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise PaperBrokerError(f"paper broker HTTP {exc.code} on {path}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PaperBrokerError(f"paper broker unreachable ({type(exc).__name__})") from None
        try:
            return json.loads(raw) if raw.strip() else None
        except ValueError:
            raise PaperBrokerError(f"paper broker bad JSON on {path}") from None

    def cash(self) -> float:
        account = self._request("GET", "/v2/account")
        if not isinstance(account, dict):
            raise PaperBrokerError("paper broker account shape invalid")
        try:
            value = float(account.get("cash", 0.0))
        except (TypeError, ValueError):
            raise PaperBrokerError("paper broker cash not a number") from None
        if value < 0:
            raise PaperBrokerError("paper broker cash negative")
        return value

    def positions(self) -> list[Position]:
        rows = self._request("GET", "/v2/positions")
        if not isinstance(rows, list):
            raise PaperBrokerError("paper broker positions shape invalid")
        out: list[Position] = []
        for row in rows:
            if not isinstance(row, dict):
                raise PaperBrokerError("paper broker position shape invalid")
            try:
                out.append(
                    Position(
                        symbol=str(row["symbol"]).upper(),
                        qty=float(row["qty"]),
                        market_value=float(row["market_value"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                raise PaperBrokerError("paper broker position fields invalid") from None
        return out

    def submit(self, intent: OrderIntent) -> Fill:
        if intent.side not in ("buy", "sell"):
            raise PaperGuardError(f"unknown side: {intent.side!r}")
        if intent.notional <= 0:
            raise PaperGuardError(f"notional must be positive: {intent.notional!r}")
        order = self._request(
            "POST",
            "/v2/orders",
            {
                "symbol": intent.symbol.upper(),
                "notional": round(intent.notional, 2),
                "side": intent.side,
                "type": "market",
                "time_in_force": "day",
            },
        )
        if not isinstance(order, dict):
            raise PaperBrokerError("paper broker order shape invalid")
        try:
            filled_qty = float(order.get("filled_qty") or 0.0)
            avg_price = float(order.get("filled_avg_price") or 0.0)
        except (TypeError, ValueError):
            raise PaperBrokerError("paper broker fill fields invalid") from None
        if filled_qty <= 0 or avg_price <= 0:
            raise PaperBrokerError(
                f"paper broker left {intent.symbol} unfilled (status {order.get('status')!r})"
            )
        return Fill(intent.symbol, intent.side, filled_qty * avg_price, avg_price)
