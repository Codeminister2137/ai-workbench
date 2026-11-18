"""Profile judges: turn market snapshots into allocation decisions.

The live judge asks the profile's model through a council agent; the
stub judge serves tests and offline evals. Unparseable model output
holds the previous allocation (fail-safe: never trade on confusion).
"""

from __future__ import annotations

import math

from investor.profiles import AllocationDecision, InvestorProfile


def parse_weights(text: str, symbols: tuple[str, ...]) -> dict[str, float]:
    """Parse ``SYMBOL: percent`` lines; unknown symbols and junk dropped.

    Weights normalize to fractions and clamp to [0, 1] per symbol.
    """
    allowed = {symbol.upper() for symbol in symbols}
    weights: dict[str, float] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip().lstrip("-*").strip()
        symbol, separator, percent = line.partition(":")
        if not separator:
            continue
        symbol = symbol.strip().upper()
        if symbol not in allowed:
            continue
        try:
            value = float(percent.strip().rstrip("%")) / 100.0
        except ValueError:
            continue
        if math.isfinite(value):
            weights[symbol] = max(0.0, min(1.0, value))
    return weights


def judge_prompt(profile: InvestorProfile, snapshot: str) -> str:
    """Instruction + market snapshot for one allocation decision."""
    return (
        f"{profile.system_prompt}\n\n"
        f"Risk posture: {profile.risk_posture}; horizon: {profile.horizon}; "
        f"max single position: {profile.max_position_pct}%.\n\n"
        "Current market snapshot (prices oldest to newest):\n"
        f"{snapshot}\n\n"
        "Reply with target allocation only, one per line as SYMBOL: percent "
        "(whole portfolio need not sum to 100; rest stays cash)."
    )


class StubJudge:
    """Deterministic judge for tests: fixed weights per profile name."""

    def __init__(self, weights_by_profile: dict[str, dict[str, float]]):
        self.weights_by_profile = weights_by_profile

    def decide(
        self, profile: InvestorProfile, snapshot: str, symbols: tuple[str, ...]
    ) -> AllocationDecision:
        del snapshot
        weights = {
            symbol: weight
            for symbol, weight in self.weights_by_profile.get(profile.name, {}).items()
            if symbol in symbols
        }
        return AllocationDecision(profile=profile.name, weights=weights, rationale="stub")
