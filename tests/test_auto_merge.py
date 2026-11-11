"""Auto-merge classifier: pure, fast, no git side effects."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from auto_merge import classify as classify_fn
from auto_merge import gate_commands, push_with_retries  # noqa: E402


def test_docs_only_eligible() -> None:
    verdict = classify_fn(["docs/a.md", "docs/plans/b.md"])
    assert (verdict.eligible, verdict.kind) == (True, "docs-only")


def test_test_only_eligible() -> None:
    verdict = classify_fn(["tests/test_x.py", "apps/workbench_dashboard/tests/test_y.py"])
    assert (verdict.eligible, verdict.kind) == (True, "test-only")


def test_small_fix_eligible() -> None:
    verdict = classify_fn(["packages/a.py", "tests/test_a.py"])
    assert (verdict.eligible, verdict.kind) == (True, "small-fix")


def test_refusals() -> None:
    assert classify_fn([]).eligible is False
    assert classify_fn(["a.py", "b.py", "c.py", "d.py"]).kind == "too-big"
    assert classify_fn(["pkg/pyproject.toml"]).kind == "dependencies"
    assert classify_fn(["db/migrations/001.sql"]).kind == "risky"
    assert classify_fn(["docs/decisions/ADR-1.md"]).kind == "decisions"


def test_gate_commands_scoped() -> None:
    docs = gate_commands("docs-only", ["docs/a.md"])
    assert any("test_document_status.py" in " ".join(cmd) for cmd in docs)
    tests = gate_commands("test-only", ["tests/test_x.py"])
    assert any("tests/test_x.py" in " ".join(cmd) for cmd in tests)
    fix = gate_commands("small-fix", ["pkg/a.py"])
    assert any("pkg/a.py" in " ".join(cmd) for cmd in fix)


def test_lint_covers_changed_files_only() -> None:
    """Whole-tree ruff fails on untouched mirrors; the gate stays scoped."""
    for kind, files in (
        ("docs-only", ["docs/a.md"]),
        ("test-only", ["tests/test_x.py"]),
        ("small-fix", ["pkg/a.py"]),
    ):
        lint = gate_commands(kind, files)[0]
        assert lint[:3] == [lint[0], "check", "--quiet"]
        assert lint[3:] == files


def test_push_retries_run_hooks_and_never_bypass(monkeypatch) -> None:
    """Timeouts retry with hooks; a red gate stops the merge, never skips it."""
    import subprocess

    calls = []
    script = iter(
        [
            subprocess.TimeoutExpired(cmd=["git", "push"], timeout=900),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="0\n", stderr=""),
            subprocess.CompletedProcess(
                args=[], returncode=0, stdout="abc\trefs/heads/auto/x\n", stderr=""
            ),
        ]
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs.get("timeout")))
        outcome = next(script)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert push_with_retries("auto/x", attempts=3) == "abc\trefs/heads/auto/x"
    pushes = [command for command, _ in calls if command[:2] == ["git", "push"]]
    assert len(pushes) == 2
    assert all("--no-verify" not in command for command in pushes)
    assert all(timeout == 900 for _, timeout in calls if _[:2] == ["git", "push"])


def test_push_gives_up_after_red_gate(monkeypatch) -> None:
    import subprocess

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="hook failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="push failed after 2 attempts"):
        push_with_retries("auto/x", attempts=2)
    assert len([c for c in calls if c[:2] == ["git", "push"]]) == 2
    assert all("--no-verify" not in c for c in calls)
