"""Synthesis quality eval: run the council over fixed questions, score verdicts.

Usage (from apps/ai_council):
    python -m evals.run_synthesis_eval --record      # run + write baseline
    python -m evals.run_synthesis_eval --compare     # run + diff vs baseline

Needs local Ollama with the configured models. Exits nonzero when any
question errors or, in compare mode, when overall regresses > 0.10.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from config import CouncilConfig  # noqa: E402
from council import LocalCouncil  # noqa: E402
from domain import CouncilMember  # noqa: E402
from storage import ConversationStore  # noqa: E402

from evals.score import aggregate, score_question  # noqa: E402

BASELINE_PATH = HERE / "baselines" / "synthesis-v1.json"
REGRESS_TOLERANCE = 0.10


def load_suite() -> dict:
    return json.loads((HERE / "synthesis_questions.json").read_text(encoding="utf-8"))


def run_suite(store_dir: Path) -> dict[str, dict]:
    """Execute every question; returns {qid: {verdict, error}} (never raises per item)."""
    suite = load_suite()
    members = [
        CouncilMember(
            name=entry["name"],
            model=entry["model"],
            system_prompt=entry["system_prompt"],
            temperature=entry.get("temperature", 0.4),
        )
        for entry in suite["members"]
    ]
    config = CouncilConfig(
        ollama_base_url=None,
        default_conversation="eval",
        members=members,
        max_rounds=3,
    )
    store = ConversationStore(store_dir / "council.sqlite3")
    council = LocalCouncil(config, store)
    results: dict[str, dict] = {}
    try:
        for question in suite["questions"]:
            try:
                answers = council.ask(
                    question["prompt"], conversation_name=question["id"], rounds=3
                )
                synthesis = next(
                    (
                        a
                        for a in reversed(answers)
                        if str(a.get("member", "")).endswith(":synthesis")
                    ),
                    {},
                )
                results[question["id"]] = {
                    "verdict": synthesis.get("verdict", {}),
                    "answer": synthesis.get("answer", ""),
                    "error": synthesis.get("error"),
                }
            except Exception as exc:  # noqa: BLE001 - one bad question must not kill the run
                results[question["id"]] = {"verdict": {}, "answer": "", "error": str(exc)[:300]}
    finally:
        store.close()
    return results


def score_results(results: dict[str, dict]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    suite = load_suite()
    members = [entry["name"] for entry in suite["members"]]
    refs = {question["id"]: question["references"] for question in suite["questions"]}
    per_question = {
        qid: score_question(outcome.get("verdict") or {}, members, refs.get(qid, []))
        for qid, outcome in results.items()
    }
    return per_question, aggregate(per_question)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Council synthesis quality eval.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true", help="Run and write the baseline.")
    mode.add_argument("--compare", action="store_true", help="Run and diff against the baseline.")
    parser.add_argument("--runs-dir", default=str(HERE / "runs"))
    args = parser.parse_args(argv)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    run_dir = Path(args.runs_dir) / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    results = run_suite(run_dir)
    per_question, totals = score_results(results)
    payload = {"stamp": stamp, "per_question": per_question, "totals": totals, "results": results}
    (run_dir / "report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"totals": totals, "report": str(run_dir / "report.json")}, indent=2))
    if any(outcome.get("error") for outcome in results.values()):
        print("eval errors present", file=sys.stderr)
        return 2
    if args.record:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(
            json.dumps({"totals": totals, "per_question": per_question}, indent=2), encoding="utf-8"
        )
        print(f"baseline written to {BASELINE_PATH}")
        return 0
    try:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("no baseline; run --record first", file=sys.stderr)
        return 2
    delta = totals["overall"] - float(baseline.get("totals", {}).get("overall", 0.0))
    print(f"overall delta vs baseline: {delta:+.3f}")
    return 0 if delta >= -REGRESS_TOLERANCE else 1


if __name__ == "__main__":
    raise SystemExit(main())
