"""Consolidated OpenCode Go baseline evidence collector.

Runs the isolated-fixture acceptance harnesses for OpenCode Go
``opencode-go/go-kimi-k2.7-code`` and produces a single dated evidence directory. This is
intended to document baseline progress without requiring the owner to run each
script separately.

Run with OPENCODE_API_KEY exported and Ollama running for the auxiliary route:

    ollama serve
    python -m uv run --env-file .env python scripts/opencode-go-baseline-evidence.py

The fixtures deliberately do not contain ``data/pycharm-mcp.json``, so the
runs exercise the IDE-host-independent path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

RUNNERS = (
    # opencode-go-acceptance.py always runs the staged orchestrated workflow.
    ("opencode-go-acceptance.py", []),
    ("opencode-go-coding-chat-acceptance.py", []),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300,
        help="Timeout passed to each sub-harness.",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    root = (
        repo
        / "artifacts"
        / ("opencode-go-baseline-evidence-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    root.mkdir(parents=True)

    results: list[dict[str, object]] = []
    for runner, extra in RUNNERS:
        script = repo / "scripts" / runner
        command = [
            sys.executable,
            str(script),
            "--timeout-seconds",
            str(int(args.timeout_seconds)),
            *extra,
        ]
        print(f"evidence_runner_started: {runner}", flush=True)
        run = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        (root / f"{runner}.stdout.log").write_text(run.stdout, encoding="utf-8")
        (root / f"{runner}.stderr.log").write_text(run.stderr, encoding="utf-8")
        passed = run.returncode == 0
        results.append(
            {
                "runner": runner,
                "passed": passed,
                "exit_code": run.returncode,
            }
        )
        print(f"evidence_runner_finished: {runner} passed={passed}", flush=True)

    summary = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "runners": results,
        "overall_passed": all(r["passed"] for r in results),
    }
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"evidence_artifacts: {root}", flush=True)
    return 0 if summary["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
