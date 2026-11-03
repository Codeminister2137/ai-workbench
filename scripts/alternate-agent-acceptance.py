"""Opt-in CLI coding acceptance on synthetic fixtures; Requesty is free-only.

Run with the workspace environment. Fixtures/logs remain under ignored artifacts/ for
inspection. This is an execution check, not a comparative model-quality evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

ROUTES = (
    "requesty/free-google/gemma-4-31b-it",
    "google/antigravity-gemini-3.1-pro-high",
    "github/copilot-cli-auto",
    "kiro/auto",
)

#: Host variables safe to expose to acceptance children. Route credentials are
#: added per-route; nothing else from the ambient environment is passed through.
BASE_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "LANG",
        "LC_ALL",
    }
)

#: Credential/command keys each route needs. A route's agent child receives ONLY
#: its own keys plus BASE_ENV_ALLOWLIST; other routes' secrets are withheld.
ROUTE_ENV_KEYS = {
    "requesty/free-google/gemma-4-31b-it": ("REQUESTY_API_KEY",),
    "google/antigravity-gemini-3.1-pro-high": ("ANTIGRAVITY_COMMAND",),
    "github/copilot-cli-auto": ("GITHUB_COPILOT_COMMAND",),
    "kiro/auto": ("KIRO_COMMAND",),
}

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


def build_base_env(source: Mapping[str, str]) -> dict[str, str]:
    """Minimal host environment for validation children (no route credentials)."""
    return {name: value for name, value in source.items() if name.upper() in BASE_ENV_ALLOWLIST}


def build_route_env(route: str, source: Mapping[str, str]) -> dict[str, str]:
    """Minimal environment for one route's agent child: host allowlist plus its keys."""
    try:
        keys = ROUTE_ENV_KEYS[route]
    except KeyError:
        raise ValueError(f"Unknown acceptance route: {route!r}") from None
    environment = build_base_env(source)
    for key in keys:
        if key in source:
            environment[key] = source[key]
    return environment


def load_dotenv_secrets(repo: Path) -> dict[str, str]:
    """Read route credentials from the repo .env without mutating os.environ."""
    wanted = {key for keys in ROUTE_ENV_KEYS.values() for key in keys}
    secrets: dict[str, str] = {}
    for line in (repo / ".env").read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() in wanted:
            secrets[name.strip()] = value.strip().strip("\"'")
    return secrets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes", nargs="+", choices=ROUTES, default=list(ROUTES))
    parser.add_argument("--timeout-seconds", type=float, default=180)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    # .env values override ambient ones, as before, but stay out of this process's
    # own os.environ: every child below receives an explicit minimal env instead
    # of inheriting the full parent environment.
    ambient = {**os.environ, **load_dotenv_secrets(repo)}
    root = (
        repo
        / "artifacts"
        / ("alternate-agent-acceptance-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    root.mkdir(parents=True)
    results = []
    for route in args.routes:
        fixture = root / route
        fixture.mkdir()
        (fixture / "math_ops.py").write_text(SOURCE, encoding="utf-8")
        test_file = fixture / "test_math_ops.py"
        test_file.write_text(TESTS, encoding="utf-8")
        (fixture / "AGENTS.md").write_text(
            "Synthetic acceptance fixture. Edit only math_ops.py. Do not alter tests, "
            "inspect outside this directory, use network tools, or delegate.\n",
            encoding="utf-8",
        )
        validation = [sys.executable, "-m", "unittest", "-q"]
        baseline = subprocess.run(
            validation, cwd=fixture, capture_output=True, text=True, env=build_base_env(ambient)
        )
        assert baseline.returncode != 0, "Fixture must fail before the agent edit"
        prompt = (
            "Fix math_ops.add to perform addition. Read the file and use an actual file-edit "
            "tool to fix it; a textual description is insufficient. Edit only math_ops.py. "
            "Do not change tests, delegate, access other directories, or use network tools. "
            "Finish with a brief description of the change."
        )
        command = [
            sys.executable,
            "-m",
            "ai_agent.repo_coding_assistant",
            "--mode",
            "implement",
            prompt,
            "--execute",
            "--repo-root",
            str(fixture),
            "--catalog",
            str(repo / "packages/ai_orchestrator/examples/model_catalog.toml"),
            "--route-id",
            route,
            "--privacy",
            "public_or_low_risk",
            "--cost-policy",
            "free_only" if route.startswith("requesty-") else "allowances_allowed",
            "--approval-policy",
            "trusted_local",
            "--skip-prompt-review",
            "--max-action-rounds",
            "6",
            "--timeout-seconds",
            "90",
        ]
        print(f"acceptance_started: {route}", flush=True)
        failure = None
        try:
            run = subprocess.run(
                command,
                cwd=fixture,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout_seconds,
                env=build_route_env(route, ambient),
            )
            (fixture / "assistant.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            exit_code = run.returncode
        except subprocess.TimeoutExpired:
            exit_code = None
            failure = "acceptance process timed out"
        checked = subprocess.run(
            validation, cwd=fixture, capture_output=True, text=True, env=build_base_env(ambient)
        )
        (fixture / "validation.log").write_text(checked.stdout + checked.stderr, encoding="utf-8")
        changed = (fixture / "math_ops.py").read_text(encoding="utf-8") != SOURCE
        tests_unchanged = test_file.read_text(encoding="utf-8") == TESTS
        passed = exit_code == 0 and changed and tests_unchanged and checked.returncode == 0
        result = {
            "route": route,
            "passed": passed,
            "exit_code": exit_code,
            "source_changed": changed,
            "tests_unchanged": tests_unchanged,
            "validation_exit_code": checked.returncode,
            "failure": failure,
        }
        results.append(result)
        print(json.dumps(result), flush=True)
    (root / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"acceptance_artifacts: {root}", flush=True)
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
