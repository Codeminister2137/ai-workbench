"""OpenCode Go coding-chat continuity acceptance.

Runs a two-turn coding-chat conversation against the OpenCode Go
``opencode-go/go-kimi-k2.7-code`` route and checks continuation through the same
saved session and completion of the task. This is a continuity check, not a
comparative model-quality evaluation.

Run with OPENCODE_API_KEY exported and Ollama running for the derived local
auxiliary route, e.g.:

    ollama serve
    python -m uv run --env-file .env python scripts/opencode-go-coding-chat-acceptance.py

The harness creates its fixture under ``artifacts/``. The fixture instructions
restrict edits; the directory itself is not an operating-system sandbox.
"""

from __future__ import annotations

import argparse
import builtins
import contextlib
import io
import json
import math
import subprocess
import sys
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from ai_agent import repo_coding_assistant as cli

ROUTE = "opencode-go/go-kimi-k2.7-code"
SOURCE = "def add(a, b):\n    return a - b\n"
TESTS = """import unittest
from math_ops import add


class AddTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative(self):
        self.assertEqual(add(-2, -3), -5)

    def test_zero(self):
        self.assertEqual(add(0, 7), 7)


if __name__ == "__main__":
    unittest.main()
"""

TURN_ONE = (
    "Read math_ops.py and explain the defect in add(a, b). Do not edit the file yet; "
    "wait for my follow-up confirmation."
)
TURN_TWO = (
    "Please go ahead and fix the defect by editing math_ops.py, then run pytest "
    "to verify all tests pass. Report the change briefly."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300,
        help="Total wall-clock timeout for each CLI invocation.",
    )
    args = parser.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be finite and greater than zero")

    repo = Path(__file__).resolve().parents[1]
    root = (
        repo
        / "artifacts"
        / ("opencode-go-coding-chat-acceptance-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    root.mkdir(parents=True)
    fixture = root / ROUTE.replace("/", "-")
    fixture.mkdir()

    source_file = fixture / "math_ops.py"
    source_file.write_text(SOURCE, encoding="utf-8")
    test_file = fixture / "test_math_ops.py"
    test_file.write_text(TESTS, encoding="utf-8")
    (fixture / "AGENTS.md").write_text(
        "Synthetic acceptance fixture. Edit only math_ops.py. Do not alter tests, "
        "inspect outside this directory, use network tools, or delegate.\n",
        encoding="utf-8",
    )

    # Ignore fixture bytecode from earlier/model-side validation. A same-size
    # edit within one timestamp tick must still execute the current source.
    validation = [
        sys.executable,
        "-B",
        "-X",
        f"pycache_prefix={root / 'host-validation-cache'}",
        "-m",
        "pytest",
        "-q",
    ]
    baseline = subprocess.run(
        validation, cwd=fixture, capture_output=True, text=True, timeout=args.timeout_seconds
    )
    (root / "baseline-validation.log").write_text(
        baseline.stdout + baseline.stderr, encoding="utf-8"
    )
    if baseline.returncode == 0:
        print("acceptance_fixture_error: fixture must fail before the agent edit", flush=True)
        return 1

    if not _ollama_reachable():
        print(
            "acceptance_warning: Ollama does not appear to be running on "
            "localhost:11434; the auxiliary route may fail if the staged workflow "
            "is enabled.",
            flush=True,
        )

    original_input = builtins.input
    original_stdin = sys.stdin
    owner_inputs = deque(["/exit"])

    def scripted_input(prompt: str = "") -> str:
        if owner_inputs:
            return owner_inputs.popleft()
        return "/exit"

    builtins.input = scripted_input
    # Non-tty stdin forces CodingChatInput.read to use input() instead of the
    # terminal poll loop, so the scripted answers are delivered.
    sys.stdin = io.StringIO("/exit\n")

    invocation = [
        "--mode",
        "coding-chat",
        "--execute",
        "--repo-root",
        str(fixture),
        "--route-id",
        ROUTE,
        "--cost-policy",
        "allowances_allowed",
        "--privacy",
        "public_or_low_risk",
        "--approval-policy",
        "trusted_local",
        "--skip-prompt-review",
        "--coding-session",
        "new",
        "--coding-session-db",
        str(root / "session.sqlite3"),
        "--coding-chat-history-budget-chars",
        "5000",
        "--max-action-rounds",
        "6",
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--turn-timeout-seconds",
        str(args.timeout_seconds),
        TURN_ONE,
    ]

    def _replace_arg(args: list[str], flag: str, value: str) -> None:
        """Replace the value following ``flag`` in a copied argument list."""
        idx = args.index(flag)
        args[idx + 1] = value

    log = io.StringIO()
    statuses = []
    started = time.monotonic()
    session_id: str | None = None
    first_turn_source_unchanged = False
    first_turn_tests_unchanged = False
    failure_reason = None
    print(f"acceptance_started: {ROUTE}", flush=True)
    try:
        with contextlib.redirect_stdout(log):
            statuses.append(cli.main(invocation))
            first_turn_source_unchanged = source_file.read_text(encoding="utf-8") == SOURCE
            first_turn_tests_unchanged = test_file.read_text(encoding="utf-8") == TESTS
            # Capture the created session id from the first run's output.
            for line in log.getvalue().splitlines():
                if line.startswith("coding_session_id:"):
                    session_id = line.split(":", 1)[1].strip()
                    break
            if statuses[0] != 0:
                failure_reason = "First CLI turn failed; follow-up was not submitted"
            elif not first_turn_source_unchanged or not first_turn_tests_unchanged:
                failure_reason = "First turn changed protected source or tests before confirmation"
            elif not session_id:
                failure_reason = "First turn did not emit a coding_session_id"
            else:
                # The initial prompt already submits TURN_TWO. Queue only exit;
                # queuing TURN_TWO as well would execute the follow-up twice.
                owner_inputs.clear()
                owner_inputs.append("/exit")
                _replace_arg(invocation, "--coding-session", session_id)
                invocation[-1] = TURN_TWO
                statuses.append(cli.main(invocation))
    finally:
        builtins.input = original_input
        sys.stdin = original_stdin
        (root / "assistant.log").write_text(log.getvalue(), encoding="utf-8")

    changed = source_file.read_text(encoding="utf-8") != SOURCE
    tests_unchanged = test_file.read_text(encoding="utf-8") == TESTS
    checked = None
    if len(statuses) == 2 and all(status == 0 for status in statuses) and tests_unchanged:
        checked = subprocess.run(
            validation, cwd=fixture, capture_output=True, text=True, timeout=args.timeout_seconds
        )
        (root / "validation.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")

    passed = (
        len(statuses) == 2
        and all(s == 0 for s in statuses)
        and first_turn_source_unchanged
        and first_turn_tests_unchanged
        and changed
        and tests_unchanged
        and checked is not None
        and checked.returncode == 0
    )
    if not passed and failure_reason is None:
        if statuses[-1] != 0:
            failure_reason = "Follow-up CLI turn failed"
        elif not tests_unchanged:
            failure_reason = "Follow-up changed protected tests; validation was not executed"
        elif not changed:
            failure_reason = "Follow-up did not change the defective source"
        else:
            failure_reason = "Final host validation failed"
    result = {
        "route": ROUTE,
        "passed": passed,
        "statuses": statuses,
        "session_id": session_id,
        "first_turn_source_unchanged": first_turn_source_unchanged,
        "first_turn_tests_unchanged": first_turn_tests_unchanged,
        "failure_reason": failure_reason,
        "continuations": "automated acceptance continuations, not physical owner approval",
        "source_changed": changed,
        "tests_unchanged": tests_unchanged,
        "validation_exit_code": checked.returncode if checked is not None else None,
        "elapsed_seconds": time.monotonic() - started,
    }
    (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    print(f"acceptance_artifacts: {root}", flush=True)
    return 0 if passed else 1


def _ollama_reachable() -> bool:
    """Return True if the Ollama API appears to be responding on localhost."""

    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:11434/", timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
