"""Pure time admission for explicitly started foreground tasks; no queue or store."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class ScheduledTaskStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    """A required allocation is a budget, never a success or cancellation promise."""

    task_id: str
    required_seconds: float
    status: ScheduledTaskStatus = ScheduledTaskStatus.PLANNED

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("Task ID must not be empty")
        if (
            isinstance(self.required_seconds, bool)
            or not math.isfinite(self.required_seconds)
            or self.required_seconds <= 0
        ):
            raise ValueError("Required task allocation must be positive and finite")


@dataclass(frozen=True, slots=True)
class TaskAdmission:
    admitted: bool
    reason: str
    remaining_seconds: float
    deadline: float | None = None


def admit_task(
    task: ScheduledTask,
    *,
    explicitly_started: bool,
    window_deadline: float,
    now: float,
    constraints_satisfied: bool,
) -> TaskAdmission:
    """Recheck one selected task without mutating its state or choosing ordering.

    Deadline and now must share a monotonic clock. Execution adapters still enforce
    privacy/cost/approval constraints; this policy never authorizes those itself.
    A caller reserves handoff time before supplying the execution-window deadline.
    """
    if not math.isfinite(window_deadline) or not math.isfinite(now):
        raise ValueError("Window deadline and current time must be finite")
    remaining = max(0.0, window_deadline - now)
    if not explicitly_started:
        return TaskAdmission(False, "Explicit start required; task remains planned", remaining)
    if task.status is not ScheduledTaskStatus.PLANNED:
        return TaskAdmission(False, "Only planned tasks are eligible to start", remaining)
    if not constraints_satisfied:
        return TaskAdmission(False, "Execution constraints are not satisfied", remaining)
    if task.required_seconds > remaining:
        return TaskAdmission(
            False, "Required allocation does not fit; task remains planned", remaining
        )
    return TaskAdmission(True, "Required allocation fits", remaining, now + task.required_seconds)
