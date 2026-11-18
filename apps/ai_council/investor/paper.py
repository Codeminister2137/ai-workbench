"""Deterministic paper portfolios over price series (no models, no network).

The evaluator replays allocation decisions tick by tick and reports
returns, volatility, max drawdown, and turnover per profile so profiles
can be compared on identical data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PriceTick:
    symbol: str
    close: float


@dataclass
class PaperPortfolio:
    """Cash + share ledger rebalanced to target weights each tick."""

    cash: float = 10000.0
    shares: dict[str, float] = field(default_factory=dict)
    equity_curve: list[float] = field(default_factory=list)
    turnover: float = 0.0

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(
            self.shares.get(symbol, 0.0) * price for symbol, price in prices.items()
        )

    def rebalance(self, weights: dict[str, float], prices: dict[str, float]) -> None:
        total = self.equity(prices)
        if total <= 0:
            return
        for symbol, weight in weights.items():
            price = prices.get(symbol)
            if price is None or price <= 0:
                continue
            target_value = total * max(0.0, min(1.0, weight))
            current_value = self.shares.get(symbol, 0.0) * price
            delta_value = target_value - current_value
            self.shares[symbol] = self.shares.get(symbol, 0.0) + delta_value / price
            self.cash -= delta_value
            self.turnover += abs(delta_value)
        self.equity_curve.append(self.equity(prices))


def max_drawdown(equity_curve: list[float]) -> float:
    """Worst peak-to-trough fraction; 0.0 for empty/flat curves."""
    peak = 0.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def volatility(returns: list[float]) -> float:
    """Population standard deviation of per-tick returns."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    return math.sqrt(sum((item - mean) ** 2 for item in returns) / len(returns))


@dataclass(frozen=True)
class ProfileResult:
    profile: str
    total_return: float
    volatility: float
    max_drawdown: float
    turnover: float
    ticks: int


def evaluate(
    prices_by_tick: list[dict[str, float]],
    decisions_by_tick: list[dict[str, dict[str, float]]],
) -> dict[str, ProfileResult]:
    """Replay profiles over ticks; returns per-profile results.

    ``decisions_by_tick[tick][profile]`` maps to target weights. Ticks
    without a profile decision keep the previous allocation.
    """
    portfolios: dict[str, PaperPortfolio] = {}
    for tick, prices in enumerate(prices_by_tick):
        decisions = decisions_by_tick[tick] if tick < len(decisions_by_tick) else {}
        for profile, weights in decisions.items():
            portfolios.setdefault(profile, PaperPortfolio()).rebalance(weights, prices)
        for profile, portfolio in portfolios.items():
            if profile not in decisions:
                portfolio.equity_curve.append(portfolio.equity(prices))
    results: dict[str, ProfileResult] = {}
    for profile, portfolio in portfolios.items():
        curve = portfolio.equity_curve
        start = curve[0] if curve else 0.0
        end = curve[-1] if curve else 0.0
        total_return = (end - start) / start if start > 0 else 0.0
        returns = [
            (curve[i] - curve[i - 1]) / curve[i - 1]
            for i in range(1, len(curve))
            if curve[i - 1] > 0
        ]
        results[profile] = ProfileResult(
            profile=profile,
            total_return=total_return,
            volatility=volatility(returns),
            max_drawdown=max_drawdown(curve),
            turnover=portfolio.turnover,
            ticks=len(curve),
        )
    return results
