"""Claim-file drain over file-backed queued runs.

Adapted from remote-operator ``supervisor_runner.py`` mechanics — atomic
claim, never-replay reconcile, receipts mirrored back — onto P6 shapes:
runs are ``runs/{id}.json`` files, approval is the linked inbox decision,
and execution is an injected callable. The real ``AgentLoop`` wiring is a
later integration; this module never imports or calls loop execution.

Approval rule (fail-closed): a queued run executes only when its linked
inbox record carries a recorded ``Approve`` answer with status ``answered``
or ``closed`` (close is archival and answers are immutable after close, so a
close preceding the drain pass must not strand an approval). Open, rejected,
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
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ai_agent.run_tracking import (
    TERMINAL_RUN_STATUSES,
    append_run_event,
    ensure_run_not_cancelled,
)

APPROVAL_ANSWER = "Approve"
CLAIM_SUFFIX = ".json.claim"
TMP_SUFFIX = ".json.tmp"

Executor = Callable[[dict], dict]
InboxGet = Callable[[str], dict | None]


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


class RunDrain:
    """Drain queued runs from ``runs_dir`` against injected inbox and executor.

    ``get_inbox`` maps an inbox id to its record (or None when absent);
    ``executor`` maps a run record to its receipt dict. A receipt selects
    the outcome through its ``status`` (``completed`` when absent,
    ``failed`` or ``paused`` on request); anything else fails the run.
    """

    def __init__(
        self,
        *,
        runs_dir: Path,
        get_inbox: InboxGet,
        executor: Executor,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._runs_dir = runs_dir
        self._get_inbox = get_inbox
        self._executor = executor
        self._now = now or time.time

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
        if answer == APPROVAL_ANSWER and status in ("answered", "closed"):
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
        for path in sorted(self._runs_dir.glob("*.json")):
            if started >= max_runs:
                break
            run = _read_json(path)
            if run is None or run.get("status") not in {"queued", "paused"}:
                continue
            if run.get("status") == "queued":
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

    def reconcile(self) -> list[dict]:
        """Release stale claims and requeue interrupted runs; never replays."""
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
            run["status"] = "queued"
            run["note"] = "Interrupted run reconciled; will resume"
            run["updated_at_utc"] = self._iso_now()
            append_run_event(run, "run_requeued", {"reason": "interrupted worker"})
            self._write_json(path, run)
            outcomes.append({"run_id": run_id, "action": "requeued"})
        return outcomes

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
            if status == "queued":
                allowed, reason = self._approval_allows(run)
                if not allowed:
                    return {
                        "run_id": run_id,
                        "status": "queued",
                        "action": "parked",
                        "reason": reason,
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
                return {"run_id": run_id, "status": "cancelled"}
            run["status"] = "running"
            run["attempts"] = int(run.get("attempts", 0)) + 1
            run["updated_at_utc"] = self._iso_now()
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
        append_run_event(run, "run_finished", {"status": status})
        self._publish(path, claim, run)
        return {"run_id": run.get("id", path.stem), "status": status}
