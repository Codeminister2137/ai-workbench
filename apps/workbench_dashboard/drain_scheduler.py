"""Periodic run-drain ticks; off unless the host starts it.

``DrainScheduler`` owns one daemon thread that calls ``tick`` every
``interval_seconds``. Tick failures are counted and remembered, never fatal:
a failing drain must not kill the dashboard. The scheduler has no dashboard
imports so it stays unit-testable; wiring lives in ``dashboard_web_app``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class DrainScheduler:
    """Call ``tick`` on an interval until stopped."""

    def __init__(self, tick: Callable[[], object], interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._tick = tick
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.ticks = 0
        self.errors = 0
        self.last_error: str | None = None

    @property
    def started(self) -> bool:
        """Return True while the scheduler thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start ticking; return False when already started."""
        if self.started:
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop ticking and wait for the thread to finish."""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=max(self._interval, 1.0) + 5.0)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - ticks must never kill the host
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                logger.warning("drain tick failed: %s", self.last_error)
            else:
                self.ticks += 1
