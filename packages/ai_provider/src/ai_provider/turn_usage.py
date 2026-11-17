"""Transient numeric observations for one CLI invocation, including failed calls."""

from __future__ import annotations

import math
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

from ai_provider.contracts import (
    AIResponse,
    AIStreamEvent,
    AIStreamFinal,
    UsageMetadata,
    UsageSource,
)


@dataclass(slots=True)
class TurnUsage:
    """Store numbers only (attribution rides alongside, never as receipts).

    An attempted call without a receipt reports no numbers. Attempts count
    adapter invocations, including admission/transport failures, rather
    than claiming that every invocation reached the provider.
    """

    attempts: int = 0
    responses: int = 0
    calls: list[dict[str, int | float]] = field(default_factory=list)
    call_meta: list[dict[str, str]] = field(default_factory=list)
    report_printed: bool = False

    def record(self, usage: UsageMetadata, index: int) -> None:
        if usage.source is not UsageSource.PROVIDER_REPORTED:
            return
        for name in ("input_tokens", "output_tokens", "total_tokens", "reported_cost_usd"):
            value = getattr(usage, name)
            if (
                type(value) in (int, float)
                and value >= 0
                and (type(value) is int or math.isfinite(value))
                and (name == "reported_cost_usd" or type(value) is int)
            ):
                self.calls[index][name] = value

    def summary(self) -> dict[str, Any]:
        merged: list[dict[str, Any]] = []
        for index, call in enumerate(self.calls):
            entry: dict[str, Any] = dict(call)
            if index < len(self.call_meta):
                entry.update(self.call_meta[index])
            merged.append(entry)
        result: dict[str, Any] = {
            "attempts": self.attempts,
            "responses": self.responses,
            "calls": merged,
            "scope": "cli_invocation_provider_calls",
        }
        for name in ("input_tokens", "output_tokens", "total_tokens", "reported_cost_usd"):
            values = [call[name] for call in self.calls if name in call]
            try:
                known_sum = (
                    (math.fsum(values) if name == "reported_cost_usd" else sum(values))
                    if values
                    else None
                )
            except OverflowError:
                known_sum = None
            result[name] = {
                "known_sum": known_sum,
                "observed_calls": len(values),
                "coverage": "complete"
                if known_sum is not None
                and self.responses == self.attempts
                and len(values) == self.attempts
                else "partial"
                if values
                else "unknown",
            }
        return result


ACTIVE_USAGE: ContextVar[TurnUsage | None] = ContextVar("turn_usage", default=None)
_ACTIVE_CALL: ContextVar[tuple[TurnUsage, int] | None] = ContextVar("usage_call", default=None)


def _identity_from_call(args: tuple) -> dict[str, str]:
    """Best-effort adapter identity: never raises, never blocks inference."""
    meta: dict[str, str] = {}
    try:
        first = args[0] if args else None
        config = getattr(first, "config", None)
        provider = getattr(config, "provider", None)
        provider = getattr(provider, "value", provider)
        model = None
        for arg in args[1:]:
            candidate = getattr(arg, "model", None)
            if isinstance(candidate, str) and candidate:
                model = candidate
                break
        if model is None:
            candidate = getattr(config, "model", None)
            if isinstance(candidate, str) and candidate:
                model = candidate
        if provider is not None:
            meta["provider"] = str(provider)
        if model is not None:
            meta["model"] = model
    except Exception:  # noqa: BLE001 - attribution is best-effort
        pass
    return meta


def _track_call(ledger: TurnUsage, args: tuple) -> None:
    ledger.attempts += 1
    ledger.calls.append({})
    ledger.call_meta.append(_identity_from_call(args))


def observe_usage(usage: UsageMetadata) -> None:
    """Update the active call's numeric receipt, even before response decoding fails."""
    call = _ACTIVE_CALL.get()
    if call is not None:
        call[0].record(usage, call[1])


def usage_scope[**P, T](function: Callable[P, T]) -> Callable[P, T]:
    """Give each invocation (including each coding-chat turn) an isolated ledger."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        token = ACTIVE_USAGE.set(TurnUsage())
        try:
            return function(*args, **kwargs)
        finally:
            ACTIVE_USAGE.reset(token)

    return wrapped


def measured_calls(
    sink: Callable[[dict[str, Any], dict[str, Any]], None],
    context: dict[str, Any] | None = None,
):
    """Scope adapter calls and flush their summary to ``sink`` on exit.

    The sink (e.g. a spend-ledger recorder) receives (summary, context).
    A failing sink writes to stderr and never breaks the wrapped calls.
    """

    @contextmanager
    def _scope():
        token = ACTIVE_USAGE.set(TurnUsage())
        try:
            yield
        finally:
            ledger = ACTIVE_USAGE.get()
            ACTIVE_USAGE.reset(token)
            if ledger is not None:
                try:
                    sink(ledger.summary(), dict(context or {}))
                except Exception as exc:  # noqa: BLE001 - telemetry never breaks calls
                    print(f"usage sink failed: {exc}", file=sys.stderr)

    return _scope()


def observe_completion[**P](function: Callable[P, AIResponse]) -> Callable[P, AIResponse]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> AIResponse:
        ledger = ACTIVE_USAGE.get()
        if ledger is not None:
            _track_call(ledger, tuple(args))
        token = _ACTIVE_CALL.set((ledger, len(ledger.calls) - 1) if ledger else None)
        try:
            response = function(*args, **kwargs)
            observe_usage(response.usage)
            if ledger is not None:
                ledger.responses += 1
            return response
        finally:
            _ACTIVE_CALL.reset(token)

    return wrapped


def observe_stream[**P](
    function: Callable[P, Iterator[AIStreamEvent]],
) -> Callable[P, Iterator[AIStreamEvent]]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> Iterator[AIStreamEvent]:
        ledger = ACTIVE_USAGE.get()
        if ledger is not None:
            _track_call(ledger, tuple(args))
        index = len(ledger.calls) - 1 if ledger else 0
        iterator = function(*args, **kwargs)
        try:
            while True:
                # Never leave call-local context active while yielding to a caller.
                token = _ACTIVE_CALL.set((ledger, index) if ledger else None)
                try:
                    event = next(iterator)
                    if ledger is not None and isinstance(event, AIStreamFinal):
                        observe_usage(event.response.usage)
                        ledger.responses += 1
                except StopIteration:
                    return
                finally:
                    _ACTIVE_CALL.reset(token)
                yield event
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                close()

    return wrapped
