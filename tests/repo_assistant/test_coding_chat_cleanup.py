"""Cleanup uncertainty must survive a successful turn and retain owned scopes."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_agent import coding_chat_cli
from ai_agent.coding_chat import CodingTurnResult
from ai_agent.coding_chat_input import CodingChatInput
from ai_agent.repo_assistant_args import build_argument_parser
from ai_provider.coding_sessions import ACTIVE_SESSION, CodingSession
from ai_provider.foreground_tools import ACTIVE_FOREGROUND, ForegroundTools


@pytest.fixture
def cleanup_chat(tmp_path: Path, monkeypatch):
    """Use a real session and child; recover test resources even on regression."""
    owners: list[ForegroundTools] = []
    sessions: list[CodingSession] = []
    before_foreground, before_session = ACTIVE_FOREGROUND.get(), ACTIVE_SESSION.get()
    original_close = ForegroundTools.close
    monkeypatch.setattr("builtins.input", lambda _: "/exit")

    def run(returncode: int = 0) -> int:
        def execute(args, config):
            owner, session = ACTIVE_FOREGROUND.get(), ACTIVE_SESSION.get()
            assert owner is not None and session is not None
            owners.append(owner)
            sessions.append(session)
            owner.supervisor.start([sys.executable, "-u", "-c", "import time; time.sleep(60)"])
            args._coding_chat_observer(
                CodingTurnResult(returncode, "Synthetic inspection report", "completed")
            )
            return returncode

        parser = build_argument_parser()
        arguments = parser.parse_args(
            [
                "--mode",
                "coding-chat",
                "--execute",
                "--repo-root",
                str(tmp_path),
                "--privacy",
                "local_only",
                "--cost-policy",
                "local_only",
                "--coding-session-db",
                str(tmp_path / "session.sqlite3"),
                "Inspect only",
            ]
        )
        return coding_chat_cli.run_coding_chat(arguments, parser, execute)

    def status() -> str:
        with sessions[0].connection() as connection:
            return connection.execute("SELECT status FROM coding_sessions").fetchone()["status"]

    def assert_closed() -> None:
        assert owners[0].supervisor.closed
        assert all(p.process.poll() is not None for p in owners[0].supervisor.processes.values())

    try:
        yield SimpleNamespace(
            run=run,
            status=status,
            assert_closed=assert_closed,
            owners=owners,
            sessions=sessions,
            before_foreground=before_foreground,
            before_session=before_session,
        )
    finally:
        for owner in owners:
            original_close(owner)
            assert all(p.process.poll() is not None for p in owner.supervisor.processes.values())
        ACTIVE_FOREGROUND.set(before_foreground)
        ACTIVE_SESSION.set(before_session)


@pytest.mark.parametrize("failure", ["terminal", "foreground", "observation"])
@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_cleanup_failure_closes_children_and_requires_reconciliation(
    cleanup_chat, monkeypatch, tmp_path: Path, failure: str, error_type: type[BaseException]
):
    owner = (
        CodingChatInput
        if failure == "terminal"
        else ForegroundTools
        if failure == "foreground"
        else CodingSession
    )
    method = "observe_process" if failure == "observation" else "close"
    original = getattr(owner, method)

    def fail_after_cleanup(self, *args):
        original(self, *args)
        raise error_type("synthetic cleanup failure")

    monkeypatch.setattr(owner, method, fail_after_cleanup)
    with pytest.raises(error_type, match="synthetic cleanup failure"):
        cleanup_chat.run()
    cleanup_chat.assert_closed()
    assert cleanup_chat.status() == "interrupted"
    assert ACTIVE_FOREGROUND.get() is cleanup_chat.before_foreground
    assert ACTIVE_SESSION.get() is cleanup_chat.before_session
    identifier = cleanup_chat.sessions[0].session_id
    with pytest.raises(ValueError, match="reconciliation"):
        CodingSession.open(
            tmp_path / "session.sqlite3",
            identifier,
            tmp_path,
            "Resume",
            [],
            privacy_class="local_only",
            cost_policy="local_only",
        )
    resumed = CodingSession.open(
        tmp_path / "session.sqlite3",
        identifier,
        tmp_path,
        "Resume",
        [],
        reconciled=True,
        privacy_class="local_only",
        cost_policy="local_only",
    )
    assert resumed.session_id == identifier


@pytest.mark.parametrize(
    "returncode,status", [(0, "completed"), (1, "failed"), (130, "interrupted")]
)
def test_successful_cleanup_preserves_the_turn_outcome(cleanup_chat, returncode: int, status: str):
    assert cleanup_chat.run(returncode) == returncode
    cleanup_chat.assert_closed()
    assert cleanup_chat.status() == status
    assert ACTIVE_FOREGROUND.get() is cleanup_chat.before_foreground
    assert ACTIVE_SESSION.get() is cleanup_chat.before_session


def test_multiple_cleanup_failures_retain_the_exception_chain(cleanup_chat, monkeypatch):
    terminal_error = OSError("synthetic terminal cleanup failure")
    foreground_error = TimeoutError("synthetic foreground cleanup failure")
    terminal_close, foreground_close = CodingChatInput.close, ForegroundTools.close
    attempted = []

    def terminal(self):
        terminal_close(self)
        attempted.append("terminal")
        raise terminal_error

    def foreground(self):
        foreground_close(self)
        attempted.append("foreground")
        raise foreground_error

    monkeypatch.setattr(CodingChatInput, "close", terminal)
    monkeypatch.setattr(ForegroundTools, "close", foreground)
    with pytest.raises(TimeoutError) as caught:
        cleanup_chat.run()
    assert attempted == ["terminal", "foreground"]
    assert caught.value is foreground_error and caught.value.__context__ is terminal_error
    assert cleanup_chat.status() == "interrupted"
    cleanup_chat.assert_closed()
    assert ACTIVE_FOREGROUND.get() is cleanup_chat.before_foreground
    assert ACTIVE_SESSION.get() is cleanup_chat.before_session


def test_cleanup_restores_an_existing_outer_scope(cleanup_chat, monkeypatch, tmp_path: Path):
    parent_foreground = ForegroundTools(tmp_path)
    parent_session = CodingSession(tmp_path / "outer.sqlite3", "outer", tmp_path)
    foreground_token = ACTIVE_FOREGROUND.set(parent_foreground)
    session_token = ACTIVE_SESSION.set(parent_session)
    original = CodingChatInput.close

    def terminal(self):
        original(self)
        raise OSError("synthetic terminal cleanup failure")

    monkeypatch.setattr(CodingChatInput, "close", terminal)
    try:
        with pytest.raises(OSError, match="synthetic terminal cleanup failure"):
            cleanup_chat.run()
        assert ACTIVE_FOREGROUND.get() is parent_foreground
        assert ACTIVE_SESSION.get() is parent_session
        cleanup_chat.assert_closed()
    finally:
        ACTIVE_FOREGROUND.reset(foreground_token)
        ACTIVE_SESSION.reset(session_token)
        parent_foreground.close()
