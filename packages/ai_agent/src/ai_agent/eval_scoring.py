"""Charter rubric scorer over RECORDED runs (no live inference).

Verdicts per docs/plans/mai-program-20261125.md: PASS (completes
without backstop cap/error), SPIN (max-iterations cap hit),
ERROR (provider/400/compaction infra failure). Unknown errors yield
``unknown`` — never forced into a verdict.

Honest limitations (v0): PASS on a completed run assumes the accepted
outcome (outcome acceptance still needs a human/exec check); SPIN does
not yet count file effects (needs receipt tool-call counts); triage
and ledger joins for recovery-cost/cost-task live in the CLI layer.
Live re-execution of seed tasks is a future slice (GPU-bound).
"""

from __future__ import annotations

from typing import Any

SPIN_MARKERS = ("max_iterations", "max-iterations")
ERROR_MARKERS = ("400", "providererror", "provider", "compaction", "overflow")
# Inactivity timeouts are deliberately unlisted: per build_retrying_executor
# they are transient often enough, so they score unknown (spin-or-transient),
# never forced into SPIN or ERROR.


def score_run(run: dict[str, Any]) -> dict[str, Any]:
    """Score one recorded run record; pure function of its fields."""
    status = str(run.get("status") or "")
    error = str(run.get("error") or "")
    blob = error.lower()
    reasons: list[str] = []
    if status == "completed":
        return {"verdict": "PASS", "reasons": ["status completed (outcome acceptance unchecked)"]}
    if any(marker in blob for marker in SPIN_MARKERS):
        reasons.append("backstop cap marker in error text")
        return {"verdict": "SPIN", "reasons": reasons}
    if any(marker in blob for marker in ERROR_MARKERS):
        reasons.append("infra marker in error text")
        return {"verdict": "ERROR", "reasons": reasons}
    if status in ("failed", "cancelled", "closed"):
        return {"verdict": "unknown", "reasons": [f"terminal status {status} without known marker"]}
    return {"verdict": "unknown", "reasons": [f"non-terminal status {status or 'missing'}"]}


def score_seed(
    runs_by_prefix: dict[str, dict[str, Any]],
    seed: Any,
) -> dict[str, Any]:
    """Score seed tasks against reference runs; aggregate charter metrics.

    ``runs_by_prefix`` maps 8-hex run prefix to the run record. Missing
    records score ``unknown`` with an explicit reason (never skipped
    silently, never zero-filled).
    """
    from ai_agent.eval_seed import SeedTask

    results: list[dict[str, Any]] = []
    for task in seed:
        assert isinstance(task, SeedTask)
        run = runs_by_prefix.get(task.run_ref)
        if run is None:
            results.append(
                {
                    "seed_id": task.seed_id,
                    "run_ref": task.run_ref,
                    "verdict": "unknown",
                    "reasons": ["no run record for this prefix"],
                }
            )
            continue
        scored = score_run(run)
        results.append(
            {
                "seed_id": task.seed_id,
                "run_ref": task.run_ref,
                "verdict": scored["verdict"],
                "reasons": scored["reasons"],
            }
        )
    decided = [r for r in results if r["verdict"] in ("PASS", "SPIN", "ERROR")]
    passes = [r for r in decided if r["verdict"] == "PASS"]
    return {
        "tasks": len(results),
        "decided": len(decided),
        "success_rate": (len(passes) / len(decided)) if decided else None,
        "verdicts": {
            v: sum(1 for r in results if r["verdict"] == v)
            for v in ("PASS", "SPIN", "ERROR", "unknown")
        },
        "results": results,
    }
