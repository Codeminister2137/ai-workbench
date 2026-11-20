"""Scoped model callback for the restricted worker inference proxy.

The proxy endpoint (:meth:`reply`) is transport-only: admission, timeouts,
budgets and cancellation live here. The host builds ONE callback per run via
:func:`make_scoped_callback` with a fixed grant (model, token budget, call
limit) and a single pre-resolved credential; the proxy loop injects the
callback into each worker turn.

Works identically whether the proxy runs in an egress-allowlisted container
(decision brief 98654698 option A) or on the host (option B): only the
credential source and the HTTP client wiring differ, never this contract.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_CALL_TIMEOUT_S = 120.0


class CallbackExhausted(RuntimeError):
    """Raised when the run's call or token budget is spent."""


@dataclass(frozen=True)
class ScopedGrant:
    """Fixed per-run inference grant. Immutable once issued."""

    model: str
    max_calls: int
    token_budget: int
    call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S


def make_scoped_callback(
    *,
    grant: ScopedGrant,
    complete: Callable[[str, Sequence[Mapping[str, str]], float], Mapping[str, Any]],
    clock: Callable[[], float] = time.monotonic,
) -> Callable[[str, Sequence[Mapping[str, str]]], dict[str, Any]]:
    """Build a budget-enforcing ``complete(model, messages)`` callback.

    ``complete`` is the raw provider call ``(model, messages, timeout_s) ->
    result`` supplied by the host (it owns the credential and the HTTP
    client). The returned callback enforces, in order: fixed model
    (refuses anything but ``grant.model``), call count, wall-clock timeout
    per call, and cumulative token budget from ``result["usage"]`` totals.
    """
    state = {"calls": 0, "tokens": 0}

    def callback(model: str, messages: Sequence[Mapping[str, str]]) -> dict[str, Any]:
        if model != grant.model:
            raise ValueError(f"callback scoped to {grant.model!r}, got {model!r}")
        if state["calls"] >= grant.max_calls:
            raise CallbackExhausted(
                f"call budget spent ({grant.max_calls} calls for {grant.model})"
            )
        started = clock()
        result = complete(model, messages, grant.call_timeout_s)
        elapsed = clock() - started
        if elapsed > grant.call_timeout_s:
            raise TimeoutError(
                f"provider call took {elapsed:.1f}s, budget was {grant.call_timeout_s:.0f}s"
            )
        usage = result.get("usage") or {}
        total = usage.get("total_tokens")
        if total is None:
            total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        state["tokens"] += int(total or 0)
        if state["tokens"] > grant.token_budget:
            raise CallbackExhausted(
                f"token budget spent ({state['tokens']} > {grant.token_budget})"
            )
        state["calls"] += 1
        return dict(result)

    return callback
