"""Claim-file drain over file-backed queued runs.

Adapted from remote-operator ``supervisor_runner.py`` mechanics — atomic
claim, never-replay reconcile, receipts mirrored back — onto P6 shapes:
runs are ``runs/{id}.json`` files, approval is the linked inbox decision,
and execution is an injected callable. The real ``AgentLoop`` wiring is a
later integration; this module never imports or calls loop execution.

Approval rule (fail-closed): a queued run executes only when its linked
inbox record carries a recorded approval answer (``Approve``, or
``Schedule it`` for NL proposal orders) with status ``answered``
or ``closed`` (close is archival and answers are immutable after close, so a
close preceding the drain pass must not strand an approval), or when the run
is marked with a preapproved ``approval_mode`` (``owner-filed``,
``e2e-followup``, ``agent-queue``).
Open, rejected,
closed-without-answer, missing, or unreadable approvals leave the run parked:
never executed, never deleted. Paused runs resume without re-approval. The
refusal path is an explicit ``Reject`` answer (or run cancellation), never a
bare close.

The drain assumes a single worker. Concurrent drains race benignly on the
atomic claim rename (the loser skips), but cancellation and approval
checks are check-then-act without a transaction.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ai_agent.run_reports import (
    render_run_report,
    render_shareable_report,
    report_has_substance,
)
from ai_agent.run_tracking import (
    TERMINAL_RUN_STATUSES,
    append_run_event,
    ensure_run_not_cancelled,
    run_cancelled,
)

APPROVAL_ANSWER = "Approve"
APPROVAL_ANSWERS = frozenset({APPROVAL_ANSWER, "Schedule it"})
CLAIM_SUFFIX = ".json.claim"
PREAPPROVED_MODES = frozenset({"owner-filed", "e2e-followup", "agent-queue"})
TMP_SUFFIX = ".json.tmp"

Executor = Callable[[dict], dict]
InboxGet = Callable[[str], dict | None]
InboxNote = Callable[[str, str], None]
TerminalHook = Callable[[dict], None]
ShipCompleted = Callable[[dict], dict]

NEEDS_ATTENTION = "needs-attention"
REPORT_NOTE_CHARS = 2000

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _append_receipt(run: dict, receipt: dict) -> None:
    receipts = run.get("receipts")
    if not isinstance(receipts, list):
        receipts = []
        run["receipts"] = receipts
    receipts.append(receipt)


def _completion_note(run: dict) -> str:
    """Human-readable completion findings for the linked inbox item.

    Leads with the run title (never a bare id) plus the summary or
    session output excerpt; the full report stays on the run record.
    """
    raw_title = run.get("title")
    title = raw_title if isinstance(raw_title, str) else "untitled"
    raw_id = run.get("id")
    run_id = raw_id if isinstance(raw_id, str) else "?"
    findings = ""
    receipts = run.get("receipts")
    if isinstance(receipts, list):
        for entry in reversed(receipts):
            if not isinstance(entry, dict):
                continue
            for key in ("summary", "stdout_tail"):
                candidate = entry.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    findings = candidate.strip()
                    break
            if findings:
                break
    if len(findings) > REPORT_NOTE_CHARS:
        findings = findings[:REPORT_NOTE_CHARS] + "\n[... full findings on the run record]"
    return (
        f"Run '{title}' ({run_id[:8]}) completed.\n\nFindings:\n{findings or '(see run report)'}\n"
    )


class RunDrain:
    """Drain queued runs from ``runs_dir`` against injected inbox and executor.

    ``get_inbox`` maps an inbox id to its record (or None when absent);
    ``executor`` maps a run record to its receipt dict. A receipt selects
    the outcome through its ``status`` (``completed`` when absent,
    ``failed`` or ``paused`` on request); anything else fails the run.
    ``on_terminal`` is an optional observer for terminal outcomes
    (completed/failed/cancelled); it never breaks the drain.
    ``inbox_note`` posts the completion findings back to the linked
    inbox item (report-or-escalate: a linked run whose note cannot be
    delivered escalates instead of reading ``completed``).
    ``ship_completed`` preserves a completed run's worktree edits
    (commit on the run branch) and schedules the merge; a shipper
    failure escalates the same way, so completed work is never
    silently left uncommitted.
    """

    def __init__(
        self,
        *,
        runs_dir: Path,
        get_inbox: InboxGet,
        executor: Executor,
        now: Callable[[], float] | None = None,
        on_terminal: TerminalHook | None = None,
        worker_epoch: str | None = None,
        inbox_note: InboxNote | None = None,
        output_evidence: Callable[[str], bool] | None = None,
        ship_completed: ShipCompleted | None = None,
    ) -> None:
        self._runs_dir = runs_dir
        self._get_inbox = get_inbox
        self._executor = executor
        self._now = now or time.time
        self._on_terminal = on_terminal
        self._worker_epoch = worker_epoch
        self._inbox_note = inbox_note
        self._output_evidence = output_evidence
        self._ship_completed = ship_completed

    def _notify_terminal(self, run: dict, status: str) -> None:
        if self._on_terminal is None:
            return
        summary = {
            "run_id": str(run.get("id", "?")),
            "status": status,
            "title": run.get("title"),
            "error": run.get("error"),
        }
        try:
            self._on_terminal(summary)
        except Exception as exc:
            logger.warning("terminal hook failed for run %s: %s", summary["run_id"], exc)

    def _iso_now(self) -> str:
        return datetime.fromtimestamp(self._now(), UTC).isoformat()

    def _write_json(self, path: Path, payload: dict) -> None:
        tmp = path.with_suffix(TMP_SUFFIX)
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _publish(self, path: Path, claim: Path, run: dict) -> None:
        self._write_json(path, run)
        try:
            claim.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _release(path: Path, claim: Path) -> None:
        """Return an unprocessed claim; never masks the real outcome."""
        if not claim.exists():
            return
        try:
            if path.exists():
                claim.unlink()
            else:
                claim.rename(path)
        except OSError:
            pass

    def _approval_allows(self, run: dict) -> tuple[bool, str]:
        if run.get("approval_mode") in PREAPPROVED_MODES:
            return True, f"preapproved ({run.get('approval_mode')})"
        inbox_id = run.get("inbox_id")
        if not inbox_id or not isinstance(inbox_id, str):
            return False, "run has no linked inbox approval"
        try:
            record = self._get_inbox(inbox_id)
        except Exception as exc:
            return False, f"approval lookup failed: {exc}"
        if record is None:
            return False, "linked approval not found"
        status = record.get("status")
        answer = record.get("answer")
        if answer in APPROVAL_ANSWERS and status in ("answered", "closed"):
            return True, "approved"
        if status == "open":
            return False, "awaiting owner approval"
        if status == "answered":
            return False, f"owner answered {answer!r}"
        return False, f"approval is {status}"

    def drain(self, *, max_runs: int = 10) -> list[dict]:
        """Run up to ``max_runs`` queued/paused runs, oldest first; one worker only."""
        if type(max_runs) is not int or not 1 <= max_runs <= 100:
            raise ValueError("max_runs must be an integer between 1 and 100")
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        outcomes = []
        started = 0
        pending: list[tuple[str, Path, dict]] = []
        for path in sorted(self._runs_dir.glob("*.json")):
            run = _read_json(path)
            if run is None or run.get("status") not in {"queued", "paused"}:
                continue
            pending.append((str(run.get("created_at_utc") or ""), path, run))
        pending.sort(key=lambda entry: (entry[0], entry[1].name))
        for _, path, run in pending:
            if started >= max_runs:
                break
            # Cancelled runs bypass approval: they must reach terminal
            # state via the claim path instead of parking forever.
            if run.get("status") == "queued" and not run_cancelled(run):
                allowed, reason = self._approval_allows(run)
                if not allowed:
                    outcomes.append(
                        {
                            "run_id": run.get("id", path.stem),
                            "status": "queued",
                            "action": "parked",
                            "reason": reason,
                        }
                    )
                    continue
            started += 1
            outcomes.append(self._run_claimed(path))
        return outcomes

    def reconcile(self, epoch: str | None = None) -> list[dict]:
        """Release stale claims and requeue interrupted runs; never replays.

        With an ``epoch`` (the reconciler's own worker epoch), only runs
        from a different epoch — provably dead workers — are requeued; a
        run stamped with the live epoch is left alone so reconcile can
        never double-execute a running worker. Without an epoch, every
        ``running`` run requeues (legacy boot behavior).

        Interruption cap (owner decision 2026-11-18): a dead-worker run
        interrupted twice with no output evidence (per the optional
        ``output_evidence`` callback) is cancelled with a terminal note
        instead of requeued forever. Without the callback every
        interruption requeues, preserving the old behavior.
        """
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        outcomes = []
        for claim in sorted(self._runs_dir.glob(f"*{CLAIM_SUFFIX}")):
            run_id = claim.name[: -len(CLAIM_SUFFIX)]
            path = self._runs_dir / f"{run_id}.json"
            if path.exists():
                try:
                    claim.unlink()
                except OSError as exc:
                    outcomes.append(
                        {"run_id": run_id, "action": "skipped", "reason": f"stale claim: {exc}"}
                    )
                    continue
                outcomes.append({"run_id": run_id, "action": "cleaned"})
            else:
                try:
                    claim.rename(path)
                except OSError as exc:
                    outcomes.append(
                        {"run_id": run_id, "action": "skipped", "reason": f"stale claim: {exc}"}
                    )
                    continue
                outcomes.append(
                    {"run_id": run_id, "action": "released", "reason": "stale claim restored"}
                )
        for path in sorted(self._runs_dir.glob("*.json")):
            run = _read_json(path)
            if run is None or run.get("status") != "running":
                continue
            run_id = run.get("id", path.stem)
            if epoch is not None and run.get("worker_epoch") == epoch:
                outcomes.append(
                    {"run_id": run_id, "action": "skipped", "reason": "live worker epoch"}
                )
                continue
            evidence = {
                "reason": "interrupted worker",
                "attempts": run.get("attempts", 0),
                "last_updated_at_utc": run.get("updated_at_utc"),
                "worker_epoch": run.get("worker_epoch"),
                "reconciled_by_epoch": epoch,
            }
            interruptions = int(run.get("interruptions", 0) or 0) + 1
            run["interruptions"] = interruptions
            if interruptions >= 5:
                cancel_reason = "interrupted repeatedly"
            elif interruptions >= 2 and not self._has_output(run_id, run):
                cancel_reason = "no output evidence"
            else:
                cancel_reason = ""
            if cancel_reason:
                run["status"] = "cancelled"
                run["error"] = (
                    f"cancelled by supervisor: {cancel_reason}; "
                    "see the run-progress log and events for what the worker left behind"
                )
                run["updated_at_utc"] = self._iso_now()
                append_run_event(run, "run_cancelled", evidence)
                self._write_json(path, run)
                self._notify_terminal(run, "cancelled")
                outcomes.append({"run_id": run_id, "action": "cancelled", "reason": cancel_reason})
                continue
            run["status"] = "queued"
            run["note"] = "Interrupted run reconciled; will resume"
            run["updated_at_utc"] = self._iso_now()
            append_run_event(run, "run_requeued", evidence)
            self._write_json(path, run)
            outcomes.append({"run_id": run_id, "action": "requeued"})
        return outcomes

    def _has_output(self, run_id: str, run: dict) -> bool:
        """True when a run left usable output (receipts or streamed lines)."""
        receipts = run.get("receipts")
        if isinstance(receipts, list) and any(
            isinstance(entry, dict)
            and (str(entry.get("stdout_tail") or "").strip() or entry.get("staged"))
            for entry in receipts
        ):
            return True
        if self._output_evidence is None:
            return True
        try:
            return bool(self._output_evidence(run_id))
        except Exception:  # noqa: BLE001 - evidence probe failure keeps the retry
            return True

    def _run_claimed(self, path: Path) -> dict:
        run_id = path.stem
        claim = path.with_suffix(CLAIM_SUFFIX)
        try:
            path.rename(claim)
        except FileNotFoundError:
            return {
                "run_id": run_id,
                "status": "unknown",
                "action": "skipped",
                "reason": "run file vanished",
            }
        except OSError:
            return {
                "run_id": run_id,
                "status": "unknown",
                "action": "skipped",
                "reason": "run is claimed by another worker",
            }
        try:
            run = _read_json(claim)
            if run is None:
                return {
                    "run_id": run_id,
                    "status": "unknown",
                    "action": "skipped",
                    "reason": "unreadable run file",
                }
            run_id = str(run.get("id", run_id))
            status = run.get("status")
            if status in TERMINAL_RUN_STATUSES:
                return {
                    "run_id": run_id,
                    "status": status,
                    "action": "skipped",
                    "reason": "terminal runs never replay",
                }
            if status not in {"queued", "paused"}:
                return {
                    "run_id": run_id,
                    "status": status,
                    "action": "skipped",
                    "reason": f"unexpected status {status!r}",
                }
            try:
                ensure_run_not_cancelled(run)
            except ValueError:
                run["status"] = "cancelled"
                run["finished_at_utc"] = self._iso_now()
                run["updated_at_utc"] = run["finished_at_utc"]
                append_run_event(
                    run, "run_cancelled", {"reason": "cancel raced execution; never executed"}
                )
                self._publish(path, claim, run)
                self._notify_terminal(run, "cancelled")
                return {"run_id": run_id, "status": "cancelled"}
            if status == "queued":
                allowed, reason = self._approval_allows(run)
                if not allowed:
                    return {
                        "run_id": run_id,
                        "status": "queued",
                        "action": "parked",
                        "reason": reason,
                    }
            run["status"] = "running"
            run["attempts"] = int(run.get("attempts", 0)) + 1
            run["updated_at_utc"] = self._iso_now()
            if self._worker_epoch is not None:
                run["worker_epoch"] = self._worker_epoch
            append_run_event(run, "run_started", {"attempt": run["attempts"]})
            self._write_json(claim, run)
            try:
                receipt = self._executor(dict(run))
            except Exception as exc:
                return self._finish(
                    path, claim, run, "failed", error=f"{type(exc).__name__}: {exc}"
                )
            if not isinstance(receipt, dict):
                return self._finish(
                    path,
                    claim,
                    run,
                    "failed",
                    error=f"Executor returned non-dict receipt: {type(receipt).__name__}",
                )
            outcome = receipt.get("status", "completed")
            if outcome not in {"completed", "failed", "paused"}:
                return self._finish(
                    path,
                    claim,
                    run,
                    "failed",
                    error=f"Unexpected receipt status: {outcome!r}",
                    receipt=receipt,
                )
            if outcome == "paused":
                run["status"] = "paused"
                run["note"] = "Executor paused; resumes on the next drain"
                run["updated_at_utc"] = self._iso_now()
                _append_receipt(run, receipt)
                append_run_event(run, "run_paused", {})
                self._publish(path, claim, run)
                return {"run_id": run_id, "status": "paused"}
            error = receipt.get("error") if outcome == "failed" else None
            if error is not None and not isinstance(error, str):
                error = str(error)
            return self._finish(path, claim, run, outcome, error=error or None, receipt=receipt)
        finally:
            self._release(path, claim)

    def _finish(
        self,
        path: Path,
        claim: Path,
        run: dict,
        status: str,
        *,
        error: str | None,
        receipt: dict | None = None,
    ) -> dict:
        run["status"] = status
        run["finished_at_utc"] = self._iso_now()
        run["updated_at_utc"] = run["finished_at_utc"]
        if error is not None:
            run["error"] = error[:1000]
        else:
            run.pop("error", None)
        if receipt is not None:
            _append_receipt(run, receipt)
            staged = receipt.get("staged")
            if isinstance(staged, list):
                run["staged"] = staged
        else:
            _append_receipt(
                run,
                {
                    "status": status,
                    "error": error,
                    "source": "drain",
                    "at_utc": run["finished_at_utc"],
                },
            )
        run.setdefault("report", render_run_report(run))
        run.setdefault("shareable_report", render_shareable_report(run))
        if status == "completed" and not report_has_substance(run):
            status = NEEDS_ATTENTION
            run["status"] = status
            error = (
                "completed but the report is hollow: no summary, session "
                "output, staged files, owner tasks, or tool calls"
            )
            run["error"] = error
        if status == "completed":
            linked = run.get("inbox_id") or run.get("bridged_from")
            if linked and isinstance(linked, str) and self._inbox_note is not None:
                try:
                    self._inbox_note(linked, _completion_note(run))
                except Exception as exc:
                    status = NEEDS_ATTENTION
                    run["status"] = status
                    error = f"completion write-back failed: {exc}"
                    run["error"] = error
        if status == "completed" and self._ship_completed is not None:
            try:
                shipment = self._ship_completed(dict(run))
            except Exception as exc:
                status = NEEDS_ATTENTION
                run["status"] = status
                error = f"completion ship failed: {type(exc).__name__}: {exc}"
                run["error"] = error[:1000]
            else:
                run["shipment"] = shipment if isinstance(shipment, dict) else {"ok": True}
                if not run["shipment"].get("committed", True):
                    status = NEEDS_ATTENTION
                    run["status"] = status
                    error = f"completion ship reported uncommitted: {run['shipment']}"
                    run["error"] = error[:1000]
        append_run_event(run, "run_finished", {"status": status})
        self._publish(path, claim, run)
        self._notify_terminal(run, status)
        return {"run_id": run.get("id", path.stem), "status": status}
