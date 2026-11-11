#!/usr/bin/env python3
"""Opt-in auto-merge for low-risk branches (owner decision: auto-merge B).

Only branches named ``auto/*`` are eligible (explicit opt-in, never default).
Eligible classes: docs-only, test-only, and small fixes (<=3 files, no
dependency manifests, no migration/schema/API-surface signals). Everything
else keeps per-merge briefs.

Pipeline per branch: eligibility -> conflict check -> gate (ruff + scoped
pytest) -> merge --no-ff -> push with retries -> verify rev-list 0 ->
print receipt (the calling agent mails it). Any failure stops with a
nonzero exit and a human-readable reason; nothing is force-pushed, nothing
merges red.

Usage:
    python scripts/auto-merge.py auto/my-docs-fix
    python scripts/auto-merge.py auto/my-docs-fix --check   # classify only
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass

TARGET = "develop"
SMALL_FIX_MAX_FILES = 3
DEPENDENCY_MANIFESTS = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "uv.lock",
    "Pipfile",
    "Pipfile.lock",
}
RISKY_SIGNALS = ("migrations/", "/migrations/", "schema", "alembic", "CHANGELOG")
PYTHON = ".venv/Scripts/python.exe"


@dataclass(frozen=True)
class Classification:
    eligible: bool
    kind: str
    reason: str


def run_git(*args: str) -> str:
    completed = subprocess.run(["git", *args], capture_output=True, text=True, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def changed_files(branch: str, target: str = TARGET) -> list[str]:
    base = run_git("merge-base", target, branch).strip()
    out = run_git("diff", "--name-only", f"{base}...{branch}").strip()
    return [line for line in out.splitlines() if line] if out else []


def classify(files: list[str]) -> Classification:
    """Pure eligibility classifier (unit-tested)."""
    if not files:
        return Classification(False, "empty", "no changes vs develop")
    names = [path.replace("\\", "/") for path in files]
    if any(name.startswith("docs/decisions/") for name in names):
        return Classification(False, "decisions", "decision records need review")
    if all(name.endswith(".md") for name in names):
        return Classification(True, "docs-only", f"{len(names)} markdown files")
    testy = [
        name
        for name in names
        if "/tests/" in f"/{name}" or name.startswith("tests/") or name.endswith("_test.py")
    ]
    if len(testy) == len(names):
        return Classification(True, "test-only", f"{len(names)} test files")
    if len(names) > SMALL_FIX_MAX_FILES:
        return Classification(False, "too-big", f"{len(names)} files > 3")
    basenames = {name.rsplit("/", 1)[-1] for name in names}
    if basenames & DEPENDENCY_MANIFESTS:
        return Classification(False, "dependencies", "dependency manifest touched")
    lowered = [name.lower() for name in names]
    if any(signal in name for name in lowered for signal in RISKY_SIGNALS):
        return Classification(False, "risky", "migration/schema signal in paths")
    return Classification(True, "small-fix", f"{len(names)} files, no risk signals")


def has_conflicts(branch: str, target: str = TARGET) -> bool:
    base = run_git("merge-base", target, branch).strip()
    out = run_git("merge-tree", base, target, branch)
    return any(line.startswith("<<<<<<< ") for line in out.splitlines())


def gate_commands(kind: str, files: list[str]) -> list[list[str]]:
    """Scoped verification per class (fast, deterministic).

    Lint covers only the branch's changed files: a whole-tree ``ruff
    check`` fails on pre-existing violations in untouched areas (notably
    the sibling-tree mirrors under patches/, which the repo's own
    pre-commit config excludes). The pre-push gate still runs whole-tree
    checks with the configured excludes before anything lands.
    """
    ruff = PYTHON.replace("python.exe", "ruff.exe")
    lint = [ruff, "check", "--quiet", *files]
    if kind == "docs-only":
        return [
            lint,
            [
                PYTHON,
                "-m",
                "pytest",
                "tests/test_document_status.py",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
        ]
    if kind == "test-only":
        return [
            lint,
            [PYTHON, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider"],
        ]
    touched = [path for path in files if path.endswith(".py")]
    return [
        lint,
        [PYTHON, "-m", "pytest", *touched, "-q", "-p", "no:cacheprovider"]
        if touched
        else [PYTHON, "-m", "pytest", "tests/test_test_suites.py", "-q", "-p", "no:cacheprovider"],
    ]


def run_gate(commands: list[list[str]]) -> tuple[bool, str]:
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return False, f"gate timeout: {' '.join(command)}"
        if completed.returncode != 0:
            tail = (completed.stdout + completed.stderr).strip().splitlines()[-8:]
            return False, f"gate red: {' '.join(command)}\n" + "\n".join(tail)
    return True, "gate green"


# Full pre-push gate takes ~7 minutes; anything shorter times out the gate.
PUSH_TIMEOUT_SECONDS = 900


def push_with_retries(branch: str, attempts: int = 3) -> str:
    """Push with hook-running retries; never bypasses an unknown gate.

    Retries always run the hooks. Falling back to --no-verify after a
    failure would bypass a gate whose result is unknown (a timeout kills
    it mid-run, a red gate must stop the merge), so transport flakes pay
    for a fresh gate instead of skipping verification.
    """
    last_error = ""
    for _attempt in range(1, attempts + 1):
        try:
            completed = subprocess.run(
                ["git", "push", "origin", branch],
                capture_output=True,
                text=True,
                timeout=PUSH_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            last_error = "push timed out (gate or transport)"
            continue
        if completed.returncode == 0:
            ahead = subprocess.run(
                ["git", "rev-list", "--count", f"{branch}", "--not", f"origin/{branch}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if ahead.returncode == 0 and ahead.stdout.strip() == "0":
                remote = subprocess.run(
                    ["git", "ls-remote", "origin", branch],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                return remote.stdout.strip()
        last_error = (completed.stderr or completed.stdout).strip().splitlines()[-1:]
        last_error = last_error[0] if last_error else f"exit {completed.returncode}"
    raise RuntimeError(f"push failed after {attempts} attempts: {last_error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in auto-merge for low-risk branches.")
    parser.add_argument("branch", help="Branch to merge (must start with auto/)")
    parser.add_argument("--check", action="store_true", help="Classify only, change nothing")
    parser.add_argument("--target", default=TARGET)
    args = parser.parse_args(argv)

    if not args.branch.startswith("auto/"):
        print(f"refused: {args.branch} is not auto-merge opted-in (needs auto/ prefix)")
        return 2
    try:
        files = changed_files(args.branch, args.target)
    except RuntimeError as exc:
        print(f"refused: {exc}")
        return 2
    verdict = classify(files)
    print(f"class: {verdict.kind} eligible={verdict.eligible} ({verdict.reason})")
    if args.check or not verdict.eligible:
        return 0 if verdict.eligible else 3
    try:
        run_git("rev-parse", "--verify", f"origin/{args.branch}")
    except RuntimeError:
        print(f"refused: origin/{args.branch} does not exist (push first)")
        return 2
    if has_conflicts(args.branch, args.target):
        print("refused: merge conflicts with develop (needs a human)")
        return 3
    ok, report = run_gate(gate_commands(verdict.kind, files))
    print(report)
    if not ok:
        return 4
    try:
        run_git("switch", args.target)
        run_git("merge", "--no-ff", args.branch, "-m", f"Auto-merge {args.branch} to {args.target}")
        remote = push_with_retries(args.target)
    except RuntimeError as exc:
        print(f"FAILED: {exc}")
        return 5
    head = run_git("rev-parse", "--short", args.target).strip()
    print(f"merged: {args.branch} -> {args.target}@{head}")
    print(f"remote: {remote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
