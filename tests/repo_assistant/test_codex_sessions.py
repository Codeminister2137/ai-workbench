"""Repo-assistant codex sessions regression contracts."""

from __future__ import annotations

import pytest

from .support import (
    main,
)


def test_cli_can_plan_persistent_codex_session(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Start a persistent Codex session.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-persist-session",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_ephemeral: False" in output
    assert "--ephemeral" not in output
    assert "external_agent_command_line_json:" in output


def test_cli_can_plan_codex_resume_last(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Resume Codex.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-resume",
                "last",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_resume: last" in output
    assert '"exec", "--cd", ' in output
    assert (
        '"--model", "gpt-5.5", "--sandbox", "workspace-write", "resume", "--json", "--last", "-"'
    ) in output
    assert "--ephemeral" not in output


def test_codex_persist_and_resume_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid flags.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-persist-session",
                "--codex-resume",
                "last",
            ]
        )


def test_codex_session_flags_require_codex_route() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-resume",
                "last",
            ]
        )
