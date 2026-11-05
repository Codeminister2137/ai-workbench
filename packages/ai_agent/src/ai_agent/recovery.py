"""Turn-boundary park/resume and write reconcile for agent loops.

Provider-neutral mechanics absorbed from the remote operator: the host can park
on an owner question (``waiting_on_owner``), record the owner's answer at a
turn boundary, and adopt an uncertain write only when freshly inspected bytes
still match. Non-write replay is always refused. This maps to P4 turn-boundary
steering (pause/resume/clarify); staged apply/approve lives with staged edits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal

from ai_agent.contracts import ToolCategory, ToolResult

MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 2000

RecoveryStatus = Literal["ready", "waiting_on_owner", "paused"]


def digest_text(content: str) -> str:
    """Stable hex digest for reconcile comparisons."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PendingOperation:
    """One uncertain operation awaiting reconcile; never auto-replayed."""

    name: str
    arguments: dict[str, Any]
    category: ToolCategory
    call_id: str | None = None


@dataclass(frozen=True, slots=True)
class OwnerAnswer:
    """An owner answer recorded at a turn boundary."""

    text: str


@dataclass(slots=True)
class RecoveryState:
    """Host-owned park/resume state plus one uncertain operation.

    The host parks a question when the loop needs owner input, records the
    answer at the next turn boundary, and tracks an interrupted tool call
    until :meth:`reconcile` adopts or refuses it. Refusals keep the pending
    operation for manual inspection; nothing here replays it.
    """

    _pending: PendingOperation | None = field(default=None, repr=False)
    _parked_question: str | None = field(default=None, repr=False)
    _status: RecoveryStatus = "ready"
    answers: tuple[OwnerAnswer, ...] = ()

    @property
    def status(self) -> RecoveryStatus:
        """Current turn-boundary status."""
        return self._status

    @property
    def pending(self) -> PendingOperation | None:
        """The uncertain operation awaiting reconcile, if any."""
        return self._pending

    @property
    def parked_question(self) -> str | None:
        """The parked owner question, if waiting."""
        return self._parked_question

    @property
    def is_waiting(self) -> bool:
        """Whether the loop is parked on an owner question."""
        return self._status == "waiting_on_owner"

    def park_question(self, question: str) -> str:
        """Park the loop on an owner question; return the stored question."""
        if self._pending is not None:
            raise ValueError("Uncertain operation requires reconciliation first")
        if self._parked_question is not None:
            raise ValueError("An owner question is already parked; answer it first")
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question) > MAX_QUESTION_CHARS
        ):
            raise ValueError("Parked question requires 1-500 characters")
        self._parked_question = question.strip()
        self._status = "waiting_on_owner"
        return self._parked_question

    def answer(self, text: str) -> OwnerAnswer:
        """Record the owner's answer and release the loop as paused."""
        if self._parked_question is None or self._status != "waiting_on_owner":
            raise ValueError("No parked owner question to answer")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_ANSWER_CHARS:
            raise ValueError("Owner answer requires 1-2000 characters")
        recorded = OwnerAnswer(text.strip())
        self.answers = (*self.answers, recorded)
        self._parked_question = None
        self._status = "paused"
        return recorded

    def track_pending(self, operation: PendingOperation) -> None:
        """Record an uncertain operation for later reconcile."""
        if not isinstance(operation, PendingOperation):
            raise TypeError("track_pending requires a PendingOperation")
        if self._pending is not None:
            raise ValueError("Uncertain operation requires reconciliation first")
        self._pending = operation

    def reconcile(self, *, expected_digest: str, actual_digest: str | None) -> ToolResult:
        """Adopt a matching inspected write; refuse mismatches and non-writes.

        ``expected_digest`` is the fingerprint of the uncertain effect and
        ``actual_digest`` is freshly inspected bytes (``None`` when the
        target is missing or unreadable). Adoption clears the pending
        operation; every refusal raises and keeps it for manual inspection.
        """
        pending = self._pending
        if pending is None:
            raise ValueError("No uncertain operation to reconcile")
        if pending.category is not ToolCategory.WRITE:
            raise ValueError("Uncertain non-write operation needs manual inspection")
        if actual_digest is None or actual_digest != expected_digest:
            raise ValueError("Uncertain edit differs; manual inspection required")
        self._pending = None
        self._status = "paused"
        return ToolResult(
            name=pending.name,
            output=f"Adopted inspected write for {pending.name}; digest {actual_digest}.",
            call_id=pending.call_id,
            is_error=False,
            metadata={"digest": actual_digest, "reconciled": True},
        )
