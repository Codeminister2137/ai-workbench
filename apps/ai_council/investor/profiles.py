"""Investor profiles: distinct council-backed paper-trading strategies.

Paper trading only: profiles emit allocation decisions evaluated against
price series. This module has no broker, orders, or network integration.
ADR-092 selects Alpaca paper as the first broker; ADR-093 defines the
autonomous paper research policy. Connected execution remains future work.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InvestorProfile:
    """One distinct investor: identity + decision prompt + risk posture."""

    name: str
    model: str
    temperature: float
    system_prompt: str
    risk_posture: str  # conservative | balanced | aggressive
    horizon: str  # short_term | long_term
    max_position_pct: float = 100.0


CONTRARIAN_PROMPT = (
    "You are a contrarian investor. Favor out-of-favor assets with intact "
    "fundamentals, small positions, long holding periods. Never chase a rally."
)

MOMENTUM_PROMPT = (
    "You are a momentum investor. Favor confirmed trends with tight "
    "invalidation levels, larger positions, short holding periods. Never "
    "catch a falling knife."
)

VALUE_PROMPT = (
    "You are a value investor. Favor steady cash-generating assets at fair "
    "prices, diversified positions, long holding periods. Never overtrade."
)


def default_profiles(model: str = "qwen3:14b") -> tuple[InvestorProfile, ...]:
    """Three starter profiles, distinct by prompt, posture, and horizon."""
    return (
        InvestorProfile(
            name="contrarian",
            model=model,
            temperature=0.3,
            system_prompt=CONTRARIAN_PROMPT,
            risk_posture="conservative",
            horizon="long_term",
            max_position_pct=25.0,
        ),
        InvestorProfile(
            name="momentum",
            model=model,
            temperature=0.5,
            system_prompt=MOMENTUM_PROMPT,
            risk_posture="aggressive",
            horizon="short_term",
            max_position_pct=60.0,
        ),
        InvestorProfile(
            name="value",
            model=model,
            temperature=0.2,
            system_prompt=VALUE_PROMPT,
            risk_posture="balanced",
            horizon="long_term",
            max_position_pct=40.0,
        ),
    )


@dataclass(frozen=True)
class AllocationDecision:
    """One profile's verdict for one tick: target weights per symbol."""

    profile: str
    weights: dict[str, float] = field(default_factory=dict)
    rationale: str = ""
