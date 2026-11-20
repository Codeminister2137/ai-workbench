"""Sequential eval allowance observations; not a guaranteed consumption cap.

One guard belongs to one provider/account and cycle. Callers must retain it
across that cycle, supply all applicable windows, and bound each operation.
The first reading is the baseline: shared usage since then counts toward evals.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import TypeVar

from ai_provider.allowance_windows import AllowanceWindow

T = TypeVar("T")


class EvalThresholdStop(RuntimeError):
    """No further calls may be admitted by this guard."""


class ObservedEvalThreshold:
    """Stop at an observed ten percentage-point increase in any window.

    Readers must perform a fresh read on every invocation, never return cached
    observations. Reset changes and decreasing usage stop this cycle rather
    than silently granting a new budget. This object is sequential, not shared
    between threads or workers. Missing post-call evidence cannot undo a call.
    """

    def __init__(self) -> None:
        self._baseline: dict[tuple[str, str, str, str], float] = {}
        self._last: dict[tuple[str, str, str, str], float] = {}
        self.stopped = False
        self._running = False

    def _observe(self, windows: Sequence[AllowanceWindow], now: datetime) -> None:
        values = {}
        if now.tzinfo is None:
            raise ValueError("Observation time must be timezone aware")
        for window in windows:
            used = window.used_percent
            reset = datetime.fromisoformat(window.resets_at_utc or "")
            if (
                reset.tzinfo is None
                or reset <= now
                or used is None
                or not math.isfinite(used)
                or not 0 <= used <= 100
            ):
                raise ValueError("Missing, expired or invalid allowance observation")
            key = (window.provider, window.bucket_id, window.window, reset.isoformat())
            if key in values:
                raise ValueError("Duplicate allowance window")
            values[key] = used
        if not values:
            raise ValueError("Missing allowance windows")
        if not self._baseline:
            self._baseline = values.copy()
        if values.keys() != self._baseline.keys():
            raise ValueError("Allowance windows or cycle changed")
        if any(value < self._last.get(key, value) for key, value in values.items()):
            raise ValueError("Allowance usage decreased; cycle accounting uncertain")
        self._last = values
        if any(value - self._baseline[key] >= 10 for key, value in values.items()):
            raise EvalThresholdStop("Observed eval threshold reached (overshoot possible)")

    def run(
        self,
        operation: Callable[[], T],
        read: Callable[[], Sequence[AllowanceWindow]],
        *,
        clock: Callable[[], datetime],
        max_read_age: timedelta,
    ) -> T:
        """Read before/after one bounded call; latch any failure until new review.

        max_read_age bounds acquisition duration, not provider reporting delay.
        A fresh request can still return delayed provider measurements.
        """
        if self.stopped or self._running:
            raise EvalThresholdStop("Guard stopped or a call is already running")
        self._running = True

        def observe() -> None:
            started = clock()
            windows = read()
            finished = clock()
            if (
                max_read_age <= timedelta(0)
                or not timedelta(0) <= finished - started <= max_read_age
            ):
                raise ValueError("Stale allowance read")
            self._observe(windows, finished)

        try:
            observe()
            try:
                return operation()
            finally:
                observe()
        except Exception:
            self.stopped = True
            raise
        finally:
            self._running = False
