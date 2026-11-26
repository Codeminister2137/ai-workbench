"""Eval seed integrity + rubric scorer (fixture runs, no inference)."""

from __future__ import annotations

from ai_agent.eval_scoring import score_run, score_seed
from ai_agent.eval_seed import get_seed


def test_seed_has_24_unique_tasks() -> None:
    seed = get_seed()
    assert len(seed) == 24
    assert len({task.seed_id for task in seed}) == 24
    assert len({task.run_ref for task in seed}) == 24
    assert all(len(task.run_ref) == 8 for task in seed)
    assert all(task.kind in ("starve", "infra", "completed") for task in seed)
    assert all(task.oracle.strip() for task in seed)


def test_scorer_verdicts() -> None:
    assert score_run({"status": "completed"})["verdict"] == "PASS"
    spin = score_run({"status": "failed", "error": "Agent loop exceeded max_iterations=25"})
    assert spin["verdict"] == "SPIN"
    for error in ("kimi 400 bad request", "ProviderError: auth", "compaction overflow"):
        assert score_run({"status": "failed", "error": error})["verdict"] == "ERROR"
    ambiguous = score_run({"status": "failed", "error": "External agent timed out after 180s"})
    assert ambiguous["verdict"] == "unknown"
    assert score_run({"status": "failed", "error": "weird"})["verdict"] == "unknown"
    assert score_run({"status": "queued"})["verdict"] == "unknown"


def test_seed_scoring_counts_and_missing() -> None:
    seed = get_seed()
    report = score_seed(
        {
            "15e52c0c": {"status": "failed", "error": "exceeded max_iterations=25"},
            "09b0ece8": {"status": "failed", "error": "kimi 400"},
            "b8e7de5d": {"status": "completed"},
        },
        seed,
    )
    assert report["tasks"] == 24
    assert report["decided"] == 3
    assert report["success_rate"] == 1 / 3
    assert report["verdicts"]["unknown"] == 21
    by_id = {row["seed_id"]: row for row in report["results"]}
    assert by_id[1]["verdict"] == "SPIN"
    assert by_id[15]["verdict"] == "ERROR"
    assert by_id[20]["verdict"] == "PASS"
