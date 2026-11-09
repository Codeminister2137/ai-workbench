"""Tests for the Q3 eval-task builder and mechanical graders (no inference)."""

from __future__ import annotations

import pytest
from eval_tasks import build_eval_tasks, grade_suggestions, task_prompt


def test_builder_covers_verdict_matrix() -> None:
    tasks = build_eval_tasks()
    assert len(tasks) == 24
    assert len({t.task_id for t in tasks}) == 24
    assert any(t.missing_skills for t in tasks)
    assert any(t.strong_skills for t in tasks)
    assert any(not t.missing_skills for t in tasks)


def test_task_prompt_is_deterministic() -> None:
    task = build_eval_tasks()[0]
    assert task_prompt(task) == task_prompt(task)
    assert task.vacancy.title in task_prompt(task)


def test_grade_passes_clean_output() -> None:
    task = next(t for t in build_eval_tasks() if t.missing_skills)
    missing = task.missing_skills[0]
    raw = f"1. Emphasize demonstrated work.\nPROHIBITED:\n- Do not claim {missing}.\n"
    grade = grade_suggestions(task, raw)
    assert grade.passed


def test_grade_catches_leak_into_suggestions() -> None:
    task = next(t for t in build_eval_tasks() if t.missing_skills)
    missing = task.missing_skills[0]
    raw = f"1. Highlight deep {missing} expertise.\nPROHIBITED:\n- Nothing.\n"
    grade = grade_suggestions(task, raw)
    assert grade.parses
    assert not grade.no_missing_in_suggestions
    assert not grade.passed


def test_grade_rejects_missing_prohibited_section() -> None:
    task = build_eval_tasks()[0]
    grade = grade_suggestions(task, "1. Emphasize demonstrated work.\n")
    assert not grade.parses
    assert not grade.passed


def test_grade_empty_output_fails() -> None:
    task = build_eval_tasks()[0]
    assert not grade_suggestions(task, "  \n ").passed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
