"""Slim supervisor instructions: budget, handbook exclusion, delegation state."""

from pathlib import Path

import pytest
from ai_agent.supervisor_prompt import (
    MAX_DELEGATION_PATHS,
    MAX_DELEGATION_RECEIPTS,
    SUPERVISOR_CORE_BUDGET_CHARS,
    SUPERVISOR_CORE_INSTRUCTIONS,
    assemble_supervisor_prompt,
)
from ai_provider.errors import ProviderError

SECRET = "synthetic-credential-only-in-fixture-13579"

HANDBOOK_PATH = Path(__file__).resolve().parents[1] / "docs" / "supervisor-handbook.md"


def test_core_fits_explicit_character_budget() -> None:
    """The always-sent core stays below its pinned budget (not the handbook)."""
    assert SUPERVISOR_CORE_BUDGET_CHARS <= 600
    assert 0 < len(SUPERVISOR_CORE_INSTRUCTIONS) <= SUPERVISOR_CORE_BUDGET_CHARS


def test_core_keeps_grounding_contract() -> None:
    """Slimming keeps every grounding phrase the chat relay pins."""
    for phrase in (
        "inspect the workspace",
        "cannot edit files",
        "never claim an email was or will be sent",
        "no live view of services",
        "Request-run button",
        "runs Windows",
    ):
        assert phrase in SUPERVISOR_CORE_INSTRUCTIONS


def test_default_assembly_sends_core_only() -> None:
    """No delegation state means no extra sections."""
    assert assemble_supervisor_prompt() == SUPERVISOR_CORE_INSTRUCTIONS


def test_handbook_material_not_sent_by_default() -> None:
    """Long-form reference stays out of the prompt path."""
    assert HANDBOOK_PATH.is_file(), "handbook reference must exist in the repo"
    prompt = assemble_supervisor_prompt(
        receipts=["read_file apps/demo.py"],
        approval_policy="restricted",
        paths=["apps/demo.py"],
    )
    assert "supervisor-handbook.md" not in prompt
    assert "reference-only detail" not in prompt
    handbook = HANDBOOK_PATH.read_text(encoding="utf-8")
    assert "reference only" in handbook.lower()
    # The handbook's own banner sentence must never be inlined into prompts.
    assert "never sent to the model" in handbook
    assert "never sent to the model" not in prompt


def test_assembly_includes_delegation_state() -> None:
    """Receipts, approval surface, and paths ride along when present."""
    prompt = assemble_supervisor_prompt(
        receipts=["read_file apps/demo.py", "git_status clean"],
        approval_policy="restricted",
        paths=["apps/demo.py", "apps/other.py"],
    )
    assert prompt.startswith(SUPERVISOR_CORE_INSTRUCTIONS)
    assert "Delegation receipts so far:" in prompt
    assert "read_file apps/demo.py" in prompt
    assert "git_status clean" in prompt
    assert "fan-out 'restricted'" in prompt
    assert "child spawns refused" in prompt
    assert "Paths involved:" in prompt
    assert "apps/demo.py" in prompt


def test_empty_state_adds_no_sections() -> None:
    """Blank receipts/paths behave like absent state."""
    prompt = assemble_supervisor_prompt(receipts=["  "], paths=["\t"], approval_policy=None)
    assert prompt == SUPERVISOR_CORE_INSTRUCTIONS


def test_unknown_approval_policy_refused() -> None:
    with pytest.raises(ValueError, match="Unknown fan-out policy"):
        assemble_supervisor_prompt(approval_policy="sometimes")


def test_receipt_bounds_are_deterministic() -> None:
    receipts = [f"tool_{index} ok" for index in range(MAX_DELEGATION_RECEIPTS + 3)]
    prompt = assemble_supervisor_prompt(receipts=receipts)
    assert "[3 earlier receipt(s) omitted]" in prompt
    assert "tool_0 ok" not in prompt
    assert f"tool_{MAX_DELEGATION_RECEIPTS + 2} ok" in prompt
    long = assemble_supervisor_prompt(receipts=["x" * 500])
    assert ("x" * 200 + "…") in long


def test_path_bounds_are_deterministic() -> None:
    paths = [f"src/file_{index}.py" for index in range(MAX_DELEGATION_PATHS + 2)]
    prompt = assemble_supervisor_prompt(paths=paths)
    assert "[+2 more]" in prompt
    assert "src/file_0.py" in prompt
    assert f"src/file_{MAX_DELEGATION_PATHS + 1}.py" not in prompt


@pytest.mark.parametrize("bad", ["C:/Windows/Temp/x.py", "/etc/hosts", "../outside.py"])
def test_non_relative_paths_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="workspace-relative"):
        assemble_supervisor_prompt(paths=[bad])


@pytest.mark.parametrize("bad", [".env", "sub/.env.local", ".aws/credentials"])
def test_credential_paths_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="credential file"):
        assemble_supervisor_prompt(paths=[bad])


def test_non_string_state_refused() -> None:
    with pytest.raises(TypeError, match="sequence of strings"):
        assemble_supervisor_prompt(receipts="read_file")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sequence of strings"):
        assemble_supervisor_prompt(paths=[None])  # type: ignore[list-item]


def test_credential_bearing_prompt_refused_without_echo(monkeypatch) -> None:
    """Fail-closed refusal, same pattern as the agent loop transport guard."""
    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    with pytest.raises(ProviderError, match="Credential-bearing") as excinfo:
        assemble_supervisor_prompt(receipts=[f"read passwords {SECRET}"])
    assert SECRET not in str(excinfo.value)
    with pytest.raises(ProviderError, match="Credential-bearing"):
        assemble_supervisor_prompt(paths=["notes.txt", SECRET])
