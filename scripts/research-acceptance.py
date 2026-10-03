"""Opt-in public-source/local-model research plumbing acceptance run."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.orchestrated_runs import SQLiteOrchestratedRunStore
from ai_provider.research_execution import (
    add_research_review_arguments,
    validate_research_review_arguments,
)
from ai_provider.research_runner import main as run_research


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--away-minutes", type=float, default=10)
    parser.add_argument("--max-repair-cycles", type=int, default=3)
    parser.add_argument("--plan", action="store_true", help="Print a plan without starting a run")
    add_research_review_arguments(parser)
    parser.set_defaults(tool_profile="research")
    args = parser.parse_args(argv)
    if not args.model.strip():
        parser.error("Model must not be empty")
    if not math.isfinite(args.away_minutes * 60) or args.away_minutes <= 0:
        parser.error("Away minutes must be positive and finite")
    if args.max_repair_cycles < -1:
        parser.error("Max repair cycles must be -1 (budget bounded) or nonnegative")
    validate_research_review_arguments(args, parser)
    root = Path(__file__).resolve().parents[1]
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    artifact = root / "artifacts" / f"research-acceptance-{stamp}"
    report = artifact / "report.md"
    database = artifact / "runs.sqlite3"
    log = artifact / "assistant.log"
    prompt = """Research Ollama's public tool-calling and thinking contracts for a provider-neutral
research runner. First call search_web with the public query "Ollama tool calling documentation".
Record discovery limits honestly if it fails or finds nothing. Search snippets do not prove
source retrieval. Fetch these two primary sources using fetch_url:
https://docs.ollama.com/capabilities/tool-calling
https://docs.ollama.com/capabilities/thinking
Then write a source-grounded Markdown report using write_research_report. Give the requested
sections substantive coverage; length is advisory and alone never requires repair or filler.
Write an initial report early and repair mandatory validation errors.
Do not fetch more than four sources. After the first valid report, scrutinize it and refine
concrete weaknesses when the controller requests another pass. Avoid filler and repeated fetches.
Use these eight Markdown sections, each nonempty:
1. Executive summary
2. Source map
3. Candidate models, practices, or facts to add/revisit
4. Recommended fields, metrics, or decision criteria
5. Provider/source-specific notes
6. Risks, stale-data warnings, and unknowns
7. Suggested next implementation slice
8. Repair checks performed
Declare every URL in a Source map table with IDs S1/S2, retrieval status fetched/not fetched, and
the actual UTC access date from its fetch receipt. Every candidate entry must have its own
verified/inferred/unknown/stale-risk label and [S1]/[S2] citation, unless explicitly unknown.
Discuss what remains unknown. Report only executed checks; do not claim the validator proves truth.
Do not edit source files or use shell/delegation. Save progress before finishing each attempt.
"""
    worker_arguments = [
        prompt,
        "--repo-root",
        str(root),
        "--mode",
        "implement",
        "--execute",
        "--tool-profile",
        "research",
        "--research-report",
        str(report),
        "--provider",
        "ollama",
        "--model",
        args.model,
        "--privacy",
        "local_only",
        "--cost-policy",
        "local_only",
        "--approval-policy",
        "trusted_local",
        "--orchestrated",
        "--away-minutes",
        str(args.away_minutes),
        "--away-run-db",
        str(database),
        "--max-action-rounds",
        "20",
        "--max-repair-cycles",
        str(args.max_repair_cycles),
        "--timeout-seconds",
        "300",
        "--context-budget-chars",
        "1500",
        "--start-ollama",
        "--log-file",
        str(log),
        "--ollama-log-file",
        str(artifact / "ollama.log"),
    ]
    for name in ("policy", "model", "mode", "output_tokens", "timeout_seconds", "tokenizer_file"):
        value = getattr(args, "research_review_" + name)
        if value is not None:
            worker_arguments.extend(["--research-review-" + name.replace("_", "-"), str(value)])
    if args.plan:
        print(
            json.dumps(
                {
                    "status": "PLANNED",
                    "budget_seconds": args.away_minutes * 60,
                    "worker_arguments": worker_arguments,
                    "artifact_directory": str(artifact),
                    "note": (
                        "No run started; artifact paths are prospective. "
                        "Reserve handoff time separately."
                    ),
                },
                indent=2,
            )
        )
        return 0
    artifact.mkdir(parents=True)
    code = run_research(worker_arguments)
    if code:
        print(f"Acceptance incomplete: exit={code}; inspect {log}")
        return code
    # The acceptance database is private to this invocation, not the normal run database.
    import sqlite3

    with sqlite3.connect(database) as connection:
        run_id = connection.execute("SELECT run_id FROM orchestrated_runs").fetchone()[0]
    stages = {
        stage.name: stage for stage in SQLiteOrchestratedRunStore(database).list_stages(run_id)
    }
    evidence = stages["implementation"].details or {}
    receipts = evidence.get("fetch_receipts", [])
    searches = evidence.get("search_receipts", [])
    if not isinstance(searches, list) or not any(s.get("query_transmitted") for s in searches):
        print("Acceptance incomplete: no actual search query attempt")
        return 1
    if not isinstance(receipts, list) or len(receipts) < 2 or not evidence.get("report_receipts"):
        print("Acceptance failed: missing actual fetch/write receipts")
        return 1
    refinement = (stages["repair"].details or {}).get("research_refinement", {})
    if not isinstance(refinement, dict) or not refinement.get("attempt_count"):
        print("Acceptance incomplete: no executed refinement after structural validation")
        return 1
    print(
        f"Executed refinement cycles: {refinement['attempt_count']}; "
        f"stop_reason={refinement.get('stop_reason')}"
    )
    print(f"Acceptance passed: report={report}; run_id={run_id}; database={database}")
    print("This verifies plumbing and report acceptance; it is not a model-quality evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
