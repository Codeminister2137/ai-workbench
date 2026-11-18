"""Seeded synthetic price series for offline investor evals (no network)."""

from __future__ import annotations

import math
import random


def generate(
    symbols: tuple[str, ...] = ("AAA", "BBB"),
    ticks: int = 60,
    seed: int = 7,
) -> list[dict[str, float]]:
    """Trending + noisy series; deterministic per seed.

    AAA trends up with noise, BBB trends down with noise, so momentum
    and contrarian profiles face genuinely different evidence.
    """
    rng = random.Random(seed)
    series: list[dict[str, float]] = []
    prices = {symbol: 100.0 for symbol in symbols}
    for tick in range(ticks):
        row: dict[str, float] = {}
        for index, symbol in enumerate(symbols):
            drift = 0.004 if index % 2 == 0 else -0.004
            shock = rng.gauss(0.0, 0.02) + 0.01 * math.sin(tick / 5 + index)
            prices[symbol] = max(1.0, prices[symbol] * (1 + drift + shock))
            row[symbol] = round(prices[symbol], 4)
        series.append(row)
    return series
