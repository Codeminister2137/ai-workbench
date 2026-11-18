from __future__ import annotations

from investor.fixtures import generate
from investor.judge import StubJudge, judge_prompt, parse_weights
from investor.paper import evaluate, max_drawdown, volatility
from investor.profiles import AllocationDecision, default_profiles


def test_profiles_are_distinct() -> None:
    profiles = default_profiles()
    assert len(profiles) == 3
    assert len({p.system_prompt for p in profiles}) == 3
    assert len({(p.risk_posture, p.horizon) for p in profiles}) == 3
    assert all(0 < p.max_position_pct <= 100 for p in profiles)


def test_parse_weights_strict() -> None:
    weights = parse_weights("AAA: 50\n- BBB: 25%\nCCC: 99\njunk line\nDDD: xx", ("AAA", "BBB"))
    assert weights == {"AAA": 0.5, "BBB": 0.25}


def test_fixtures_deterministic() -> None:
    first = generate(symbols=("AAA", "BBB"), ticks=10, seed=7)
    second = generate(symbols=("AAA", "BBB"), ticks=10, seed=7)
    assert first == second
    assert len(first) == 10
    assert first[0]["AAA"] > 0


def test_evaluate_compares_profiles() -> None:
    prices = generate(symbols=("AAA", "BBB"), ticks=20, seed=7)
    judges = StubJudge({"bull": {"AAA": 1.0}, "bear": {"BBB": 1.0}})
    decisions = [
        {
            name: judges.decide(type("P", (), {"name": name})(), "", ("AAA", "BBB")).weights
            for name in ("bull", "bear")
        }
        for _ in prices
    ]
    results = evaluate(prices, decisions)
    assert set(results) == {"bull", "bear"}
    assert results["bull"].total_return > results["bear"].total_return
    assert results["bull"].ticks == 20
    assert results["bull"].turnover > 0


def test_drawdown_and_volatility() -> None:
    assert max_drawdown([100.0, 120.0, 90.0, 110.0]) == 0.25
    assert max_drawdown([]) == 0.0
    assert volatility([0.01, -0.01]) > 0
    assert volatility([0.05]) == 0.0


def test_judge_prompt_carries_profile() -> None:
    (profile,) = default_profiles()[:1]
    prompt = judge_prompt(profile, "AAA: 100 -> 101")
    assert profile.system_prompt in prompt
    assert profile.risk_posture in prompt
    assert "SYMBOL: percent" in prompt


def test_allocation_decision_defaults() -> None:
    decision = AllocationDecision(profile="x")
    assert decision.weights == {}
    assert decision.rationale == ""


def test_investor_stays_offline() -> None:
    """Paper trading only: investor modules import no network clients."""
    import pathlib
    import re

    banned = re.compile(
        r"^\s*(import|from)\s+(urllib|requests|httpx|socket|http\.|smtplib)\b", re.M
    )
    root = pathlib.Path(__file__).resolve().parents[1] / "investor"
    for path in sorted(root.glob("*.py")):
        assert not banned.search(path.read_text(encoding="utf-8")), path.name
