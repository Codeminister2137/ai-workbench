"""Tier task sets and grader registry (no inference)."""

from __future__ import annotations

import pytest
from ai_provider import route_eval
from ai_provider.eval_task_sets import (
    GRADERS,
    TASK_GRADERS,
    TIER_TASK_SETS,
    check_tier_sets_cover_specs,
    contains_all,
    exact_json,
    grader_for_task,
    sample_tasks,
    tasks_for_tier,
)


def test_registry_covers_ladder_specs() -> None:
    assert set(TASK_GRADERS) == set(route_eval.TASK_SPECS)
    assert set(TASK_GRADERS.values()) <= set(GRADERS)
    check_tier_sets_cover_specs()


def test_tier_sets_match_budget_posture() -> None:
    assert TIER_TASK_SETS["local"] == ("T0", "T1", "T2", "T3")
    assert TIER_TASK_SETS["control"] == ("T1b",)
    assert TIER_TASK_SETS["allowance"] == ("T0", "T1")
    assert TIER_TASK_SETS["metered"] == ("T0",)
    assert tasks_for_tier("local")[0] == "T0"
    with pytest.raises(ValueError, match="unknown eval tier"):
        tasks_for_tier("platinum")


def test_grader_for_task_resolves_registry() -> None:
    assert grader_for_task("T1") is GRADERS["t1_module"]
    with pytest.raises(ValueError, match="no registered grader"):
        grader_for_task("T9")


def test_sample_tasks_keeps_gate_and_is_deterministic() -> None:
    tasks = ("T0", "T1", "T2", "T3")
    first = sample_tasks(tasks, 2, seed=7)
    assert first[0] == "T0"
    assert len(first) == 2
    assert sample_tasks(tasks, 2, seed=7) == first
    assert sample_tasks(tasks, 0, seed=7) == tasks
    assert sample_tasks(tasks, 9, seed=7) == tasks
    assert sample_tasks(("T0",), 1, seed=7) == ("T0",)


def test_generic_grader_factories() -> None:
    assert exact_json({"answer": 7})('{"answer": 7}')
    assert not exact_json({"answer": 7})('{"answer": "7"}')
    assert not exact_json({"answer": 7})("nope")
    assert contains_all("def clamp", "def retry_delay_ms")("def clamp...\ndef retry_delay_ms...")
    assert not contains_all("def clamp", "def retry_delay_ms")("def clamp...")
