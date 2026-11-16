"""Agent-executed E2E checks: extraction allowlist and execution shape."""

from __future__ import annotations

from pathlib import Path

import e2e_agent_checks


def test_extract_command_allows_pytest_and_help() -> None:
    assert (
        e2e_agent_checks.extract_command("Run `.venv/Scripts/python.exe -m pytest x -q` now")
        == ".venv/Scripts/python.exe -m pytest x -q"
    )
    assert e2e_agent_checks.extract_command("Try `ruff --help` first") == "ruff --help"


def test_extract_command_rejects_prose_and_shell() -> None:
    assert e2e_agent_checks.extract_command("Run the scoped pytest") is None
    assert e2e_agent_checks.extract_command("No backticks here") is None
    assert e2e_agent_checks.extract_command("Run `pytest x & del y`") is None
    assert e2e_agent_checks.extract_command("Run `x; y --help`") is None
    assert e2e_agent_checks.extract_command("Run `$(evil) --help`") is None


def test_execute_check_uses_runner_and_truncates(tmp_path: Path) -> None:
    seen: dict = {}

    def fake_runner(argv, repo_root):
        seen["argv"] = list(argv)
        seen["root"] = repo_root
        return 3, "o" * 9000

    result = e2e_agent_checks.execute_check(
        "Run `.venv/Scripts/python.exe -m pytest x -q`", tmp_path, runner=fake_runner
    )
    assert result["command"] == ".venv/Scripts/python.exe -m pytest x -q"
    assert result["exit_code"] == 3
    assert len(result["output"]) == e2e_agent_checks.EVIDENCE_CHARS
    assert seen["argv"][0] == ".venv/Scripts/python.exe"
    assert seen["root"] == tmp_path


def test_execute_check_refuses_unrunnable(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="no exact runnable command"):
        e2e_agent_checks.execute_check("Just look at it", tmp_path)
