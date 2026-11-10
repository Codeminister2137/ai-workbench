"""OpenCode Go live CLI acceptance harness.

Runs a small synthetic coding task against the OpenCode Go ``opencode-go/go-kimi-k2.7-code``
route and validates that the model edits the source file and the fixture tests
pass. This is an execution check, not a comparative model-quality evaluation.

The harness uses ``--orchestrated`` so it exercises the staged away-work
workflow (prompt review, planning, auxiliary panel, implementation, validation,
scrutiny, repair, final handoff). The auxiliary panel and scrutiny stages use
the default derived local route, which is Ollama ``deepseek-coder-v2:16b`` in
the example catalog. Start Ollama before running for a full end-to-end pass:

    ollama serve
    python -m uv run --env-file .env python scripts/opencode-go-acceptance.py

Run with OPENCODE_API_KEY exported in the environment. The harness uses an
isolated fixture directory so the live run cannot affect repository files outside
``artifacts/``. Fixture setup and post-run judgement go through
``bounded-acceptance-controller.py`` (prepare + coherence gate before launch,
validation gate after); both gates are offline and credential-free.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=300,
        help="Total wall-clock timeout for the agent invocation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Set up the fixture and run baseline validation without invoking the agent.",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    root = (
        repo
        / "artifacts"
        / ("opencode-go-acceptance-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    root.mkdir(parents=True)
    fixture = root / ROUTE.replace("/", "-")
    fixture.mkdir()
    controller = root / "controller"

    write_go_fixture(fixture)
    if prepare_controller(repo, fixture, controller) != 0:
        print("acceptance_fixture_error: controller preparation refused", flush=True)
        return 1
    coherence = run_gate(controller / "coherence.py", [])
    sys.stdout.write(coherence.stdout)
    if coherence.returncode != 0:
        print("acceptance_fixture_error: coherence gate refused", flush=True)
        return 1

    source_file = fixture / "math_ops.py"
    test_file = fixture / "test_math_ops.py"
    validation = [sys.executable, "-m", "pytest", "-q"]

    if args.dry_run:
        print("acceptance_dry_run: fixture ready", flush=True)
        print(f"acceptance_artifacts: {root}", flush=True)
        return 0

    if not _ollama_reachable():
        print(
            "acceptance_warning: Ollama does not appear to be running on "
            "localhost:11434; auxiliary_panel and scrutiny stages will fail. "
            "Start 'ollama serve' before this harness for a full staged pass.",
            flush=True,
        )

    prompt = (
        "Fix math_ops.add to perform addition. Read the file and use an actual "
        "file-edit tool to fix it; a textual description is insufficient. Edit "
        "only math_ops.py. Do not change tests, delegate, access other "
        "directories, or use network tools. After editing, run the tests with "
        "pytest and finish with a brief description of the change."
    )
    command = [
        sys.executable,
        "-m",
        "ai_agent.repo_coding_assistant",
        "--mode",
        "implement",
        "--repo-root",
        str(fixture),
        "--route-id",
        ROUTE,
        "--cost-policy",
        "allowances_allowed",
        "--fallback-quality-policy",
        "preserve_quality",
        "--approval-policy",
        "trusted_local",
        "--privacy",
        "public_or_low_risk",
        "--away-minutes",
        "15",
        "--orchestrated",
        "--max-repair-cycles",
        "2",
        "--max-action-rounds",
        "6",
        "--validation-timeout-seconds",
        "300",
        "--command-timeout-seconds",
        "60",
        "--execute",
        "--apply-actions",
        "--log-file",
        str(root / "transcript.log"),
        prompt,
    ]

    print(f"acceptance_started: {ROUTE}", flush=True)
    failure = None
    try:
        run = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout_seconds,
        )
        (root / "assistant.log").write_text(run.stdout + run.stderr, encoding="utf-8")
        exit_code = run.returncode
    except subprocess.TimeoutExpired:
        exit_code = None
        failure = "acceptance process timed out"

    checked = subprocess.run(validation, cwd=fixture, capture_output=True, text=True)
    (root / "validation.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")
    gate = run_gate(controller / "validate.py", ["--run-dir", str(fixture)])
    (root / "controller_validation.log").write_text(gate.stdout + gate.stderr, encoding="utf-8")

    changed = source_file.read_text(encoding="utf-8") != SOURCE
    tests_unchanged = test_file.read_text(encoding="utf-8") == TESTS
    controller_valid = gate.returncode == 0
    passed = (
        exit_code == 0
        and changed
        and tests_unchanged
        and checked.returncode == 0
        and controller_valid
    )
    result = {
        "route": ROUTE,
        "passed": passed,
        "exit_code": exit_code,
        "source_changed": changed,
        "tests_unchanged": tests_unchanged,
        "validation_exit_code": checked.returncode,
        "controller_valid": controller_valid,
        "failure": failure,
    }
    (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    print(f"acceptance_artifacts: {root}", flush=True)
    return 0 if passed else 1


CONTROLLER_SCRIPT = "bounded-acceptance-controller.py"


def write_go_fixture(fixture: Path) -> None:
    """Write the seeded-bug fixture files (offline, deterministic)."""
    (fixture / "math_ops.py").write_text(SOURCE, encoding="utf-8")
    (fixture / "test_math_ops.py").write_text(TESTS, encoding="utf-8")
    (fixture / "AGENTS.md").write_text(
        "Synthetic acceptance fixture. Edit only math_ops.py. Do not alter tests, "
        "inspect outside this directory, use network tools, or delegate.\n",
        encoding="utf-8",
    )


def prepare_controller(repo: Path, fixture: Path, controller: Path) -> int:
    """Prepare the bounded controller for this fixture (offline, no credential)."""
    script = repo / "scripts" / CONTROLLER_SCRIPT
    run = subprocess.run(
        [
            sys.executable,
            str(script),
            "prepare",
            "--route-id",
            ROUTE,
            "--fixture-dir",
            str(fixture),
            "--controller-dir",
            str(controller),
            "--editable",
            "math_ops.py",
            "--frozen",
            "test_math_ops.py",
            "--frozen",
            "AGENTS.md",
            "--bound",
            "max_action_rounds=6",
            "--bound",
            "max_repair_cycles=2",
        ],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    return run.returncode


def run_gate(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one controller gate script (offline, no credential)."""
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


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
