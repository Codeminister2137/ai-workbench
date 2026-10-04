"""Opt-in public-source/local-model research plumbing acceptance run."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.research_acceptance import RESEARCH_ACCEPTANCE_PROMPT, check_acceptance
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
    prompt = RESEARCH_ACCEPTANCE_PROMPT
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
    return check_acceptance(database, report)


if __name__ == "__main__":
    raise SystemExit(main())
