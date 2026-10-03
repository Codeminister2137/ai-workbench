"""User-start and time-fit contracts without persistence or executor decisions."""

from dataclasses import replace

import pytest
from ai_orchestrator.scheduling import ScheduledTask, ScheduledTaskStatus, admit_task


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf"), True])
def test_positive_finite_task_allocation_is_mandatory(duration):
    with pytest.raises(ValueError):
        ScheduledTask("evaluation", duration)


def test_no_start_and_non_fitting_work_remain_planned():
    task = ScheduledTask("representative-review-evaluation", 90 * 60)
    result = admit_task(
        task, explicitly_started=False, window_deadline=10000, now=0, constraints_satisfied=True
    )
    assert not result.admitted and result.deadline is None
    result = admit_task(
        task, explicitly_started=True, window_deadline=5000, now=0, constraints_satisfied=True
    )
    assert not result.admitted
    assert task.required_seconds == 5400 and task.status is ScheduledTaskStatus.PLANNED


def test_exact_fit_and_recheck_before_next_task():
    task = ScheduledTask("test", 60)
    result = admit_task(
        task, explicitly_started=True, window_deadline=160, now=100, constraints_satisfied=True
    )
    assert result.admitted and result.deadline == 160
    assert task.status is ScheduledTaskStatus.PLANNED
    result = admit_task(
        task, explicitly_started=True, window_deadline=160, now=101, constraints_satisfied=True
    )
    assert not result.admitted and result.remaining_seconds == 59


def test_execution_constraints_and_status_never_follow_from_time_fit():
    task = ScheduledTask("test", 60)
    assert not admit_task(
        task, explicitly_started=True, window_deadline=160, now=100, constraints_satisfied=False
    ).admitted
    for status in ScheduledTaskStatus:
        if status is not ScheduledTaskStatus.PLANNED:
            assert not admit_task(
                replace(task, status=status),
                explicitly_started=True,
                window_deadline=160,
                now=100,
                constraints_satisfied=True,
            ).admitted


def test_expired_window_and_invalid_clock():
    task = ScheduledTask("test", 60)
    assert (
        admit_task(
            task, explicitly_started=True, window_deadline=0, now=1, constraints_satisfied=True
        ).remaining_seconds
        == 0
    )
    with pytest.raises(ValueError, match="finite"):
        admit_task(
            task,
            explicitly_started=True,
            window_deadline=float("nan"),
            now=0,
            constraints_satisfied=True,
        )
