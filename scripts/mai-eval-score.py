"""Score the Mai eval seed v0 against recorded runs (read-only, CPU-only).

Usage: .venv/Scripts/python.exe scripts/mai-eval-score.py [--data-dir DIR]
Prints per-task verdicts plus charter metrics. Recovery-cost and
cost/task print as TBD with reasons until their joins exist. Live
re-execution is out of scope (GPU-bound future slice).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Score the seed from the run store; exit 0 with an honest table."""
    parser = argparse.ArgumentParser(description="Score Mai eval seed v0.")
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    data_dir = args.data_dir or (repo / "apps" / "workbench_dashboard" / "data")
    sys.path.insert(0, str(repo / "packages" / "ai_agent" / "src"))
    from ai_agent.eval_scoring import score_seed
    from ai_agent.eval_seed import get_seed

    runs_by_prefix: dict[str, dict] = {}
    for path in glob.glob(str(data_dir / "runs" / "*.json")):
        try:
            record = json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError):
            continue
        if isinstance(record, dict) and record.get("id"):
            runs_by_prefix[str(record["id"])[:8]] = record
    report = score_seed(runs_by_prefix, get_seed())
    print(
        f"tasks: {report['tasks']} decided: {report['decided']} "
        f"success_rate: {report['success_rate']}"
    )
    print(f"verdicts: {report['verdicts']}")
    print("recovery_cost: TBD (needs triage join) | cost/task: TBD (needs ledger join)")
    for row in report["results"]:
        print(
            f"  #{row['seed_id']:02d} {row['run_ref']} {row['verdict']:7s} "
            f"{'; '.join(row['reasons'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
