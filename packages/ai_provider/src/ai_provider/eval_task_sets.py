"""Tier task sets and grader registry for quality evals (need #1).

Smoke probes (capability_eval) answer "can it"; these sets answer "how
well" with mechanical graders. Each route tier gets an explicit task
list reflecting its budget posture (owner answer bd5fa3a2: full scope,
10% of each allowance bucket per cycle, observed-stop):

- ``local``: the full ladder (free, GPU-bound only).
- ``control``: diagnostic variants (T1b builtins control), local only.
- ``allowance``: a sampled subset sized by the runner within the
  per-bucket eval budget (the ObservedEvalThreshold guard stops spend).
- ``metered``: a single minimal probe; execution still needs explicit
  per-budget owner approval every time.

Graders are ``(answer_text) -> bool`` callables. The registry reuses
the ladder's sandboxed checkers plus small generic factories so new
tasks compose grading from named pieces instead of new harness code.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable, Mapping
from typing import Any

from ai_provider.route_eval import (
    TASK_SPECS,
    check_completion,
    check_t1,
    check_t1b,
    check_t2,
    check_t3,
)

Grader = Callable[[str], bool]

GRADERS: dict[str, Grader] = {
    "t0_completion": check_completion,
    "t1_module": check_t1,
    "t1b_module": check_t1b,
    "t2_fix": check_t2,
    "t3_spec": check_t3,
}
"""Named mechanical graders; ladder task ids map to ``<id>_grader`` below."""


def exact_json(expected: Mapping[str, Any]) -> Grader:
    """Grade exact JSON-object equality (schema-probe style answers)."""

    def grade(text: str) -> bool:
        try:
            value = json.loads(text)
        except ValueError:
            return False
        return isinstance(value, dict) and value == dict(expected)

    return grade


def contains_all(*symbols: str) -> Grader:
    """Grade presence of every symbol (weak structural check, not execution)."""

    def grade(text: str) -> bool:
        return all(symbol in text for symbol in symbols)

    return grade


GRADERS["exact_answer_7"] = exact_json({"answer": 7})

TASK_GRADERS: dict[str, str] = {
    task_id: grader_name
    for task_id, grader_name in (
        ("T0", "t0_completion"),
        ("T1", "t1_module"),
        ("T1b", "t1b_module"),
        ("T2", "t2_fix"),
        ("T3", "t3_spec"),
    )
}
"""Ladder task id -> registry grader name (must cover TASK_SPECS)."""

TIER_TASK_SETS: dict[str, tuple[str, ...]] = {
    "local": ("T0", "T1", "T2", "T3"),
    "control": ("T1b",),
    "allowance": ("T0", "T1"),
    "metered": ("T0",),
}
"""Route tier -> task ids in ladder order (budgets enforced by runners)."""


def tasks_for_tier(tier: str) -> tuple[str, ...]:
    """Return the task ids for one tier; unknown tiers fail loudly."""
    try:
        return TIER_TASK_SETS[tier]
    except KeyError:
        raise ValueError(f"unknown eval tier: {tier!r}") from None


def grader_for_task(task_id: str) -> Grader:
    """Return the registry grader for one task id."""
    try:
        name = TASK_GRADERS[task_id]
    except KeyError:
        raise ValueError(f"task {task_id!r} has no registered grader") from None
    return GRADERS[name]


def sample_tasks(task_ids: tuple[str, ...], max_tasks: int, *, seed: int) -> tuple[str, ...]:
    """Deterministically cap a task list for a sampled budget.

    The first id always survives (ladders gate on it); the remainder is a
    seeded shuffle truncated to ``max_tasks``. ``max_tasks <= 0`` keeps
    everything. Runners translate bucket budgets to ``max_tasks`` and let
    the observed-stop guard halt spend; this function only orders and caps.
    """
    if max_tasks <= 0 or len(task_ids) <= max_tasks:
        return task_ids
    rng = random.Random(seed)
    rest = list(task_ids[1:])
    rng.shuffle(rest)
    return (task_ids[0], *rest[: max_tasks - 1])


def check_tier_sets_cover_specs() -> None:
    """Fail loudly when a registered task has no tier or no grader."""
    for task_id in TASK_SPECS:
        if task_id not in TASK_GRADERS:
            raise ValueError(f"task {task_id!r} has no registered grader")
        if not any(task_id in tasks for tasks in TIER_TASK_SETS.values()):
            raise ValueError(f"task {task_id!r} belongs to no tier set")
