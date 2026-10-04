"""Durable handoffs preserve boundaries and do not replay uncertain actions."""

import sqlite3

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.tools import ReadFileTool, ToolContext, ToolRegistry
from ai_provider.coding_sessions import CodingSession


def test_additive_storage_preserves_existing_application_tables(tmp_path):
    database = tmp_path / "existing.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE chat_messages(content TEXT)")
        connection.execute("INSERT INTO chat_messages VALUES ('human work')")
    session = CodingSession.open(database, "new", tmp_path, "Review", ["Keep interfaces"])
    with session.connection() as connection:
        assert connection.execute("SELECT content FROM chat_messages").fetchone()[0] == "human work"
    assert "Keep interfaces" in session.handoff()
    assert "Approvals from earlier invocations have expired" in session.handoff()


def test_restarting_running_session_requires_explicit_effect_reconciliation(tmp_path):
    database = tmp_path / "sessions.sqlite3"
    first = CodingSession.open(database, "new", tmp_path, "Build", [])
    receipt = first.begin("edit_file")
    with pytest.raises(ValueError, match="reconciliation"):
        CodingSession.open(database, first.session_id, tmp_path, "Continue", [])
    restarted = CodingSession.open(
        database, first.session_id, tmp_path, "Continue", [], reconciled=True
    )
    assert "running" in restarted.handoff()
    with restarted.connection() as connection:
        assert (
            connection.execute(
                "SELECT status FROM coding_receipts WHERE receipt_id=?", (receipt,)
            ).fetchone()[0]
            == "running"
        )
    assert not list(tmp_path.glob("*.py"))


def test_session_cannot_change_workspace_privacy_or_cost_boundary(tmp_path):
    database = tmp_path / "sessions.sqlite3"
    session = CodingSession.open(database, "new", tmp_path, "Work", [])
    session.status("completed")
    with pytest.raises(ValueError, match="different workspace"):
        CodingSession.open(database, session.session_id, tmp_path / "other", "Work", [])
    with pytest.raises(ValueError, match="privacy/cost"):
        CodingSession.open(
            database, session.session_id, tmp_path, "Work", [], privacy_class="external_allowed"
        )


def test_observed_tool_persists_status_and_hash_without_arguments_or_output(tmp_path):
    secret = "synthetic-secret-not-for-storage"
    (tmp_path / "source.txt").write_text(secret)
    session = CodingSession.open(tmp_path / "sessions.sqlite3", "new", tmp_path, "Review", [])
    registry = session.observe_registry(ToolRegistry((ReadFileTool(),)))
    result = registry.execute(ToolCall("read_file", {"path": "source.txt"}), ToolContext(tmp_path))
    assert secret in result.output
    handoff = session.handoff()
    assert "read_file" in handoff and "completed" in handoff
    assert secret not in handoff and "source.txt" not in handoff
    with session.connection() as connection:
        row = connection.execute("SELECT output_sha256 FROM coding_receipts").fetchone()
        assert len(row[0]) == 64


def test_unknown_process_handles_remain_metadata_after_restart(tmp_path):
    session = CodingSession.open(tmp_path / "sessions.sqlite3", "new", tmp_path, "Work", [])
    session.observe_process(
        {"process_handle": "old", "pid": 999999, "status": "running", "returncode": None}
    )
    resumed = CodingSession.open(
        session.database, session.session_id, tmp_path, "Continue", [], reconciled=True
    )
    with resumed.connection() as connection:
        assert (
            connection.execute("SELECT status FROM coding_processes").fetchone()[0]
            == "unknown_after_restart"
        )
    assert not resumed.supervisor.processes


def test_interrupted_client_requires_reconciliation_even_after_failed_session(tmp_path):
    import subprocess

    from ai_orchestrator import AccessMethod
    from ai_provider.coding_sessions import ACTIVE_SESSION
    from ai_provider.external_agents import ExternalAgentConfig, run_external_agent

    session = CodingSession.open(tmp_path / "sessions.sqlite3", "new", tmp_path, "Review", [])
    token = ACTIVE_SESSION.set(session)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            run_external_agent(
                "Review",
                ExternalAgentConfig(AccessMethod.CODEX_CLI, "client", "model", tmp_path, 1),
                runner=lambda *a, **kw: (_ for _ in ()).throw(
                    subprocess.TimeoutExpired("client", 1)
                ),
            )
    finally:
        ACTIVE_SESSION.reset(token)
    session.status("failed")
    with pytest.raises(ValueError, match="reconciliation"):
        CodingSession.open(session.database, session.session_id, tmp_path, "Continue", [])


def test_cli_session_uses_effective_config_cost_policy_and_cleans_up(tmp_path, monkeypatch):
    from ai_provider import repo_coding_assistant
    from ai_provider.coding_sessions import ACTIVE_SESSION

    database = tmp_path / "sessions.sqlite3"
    (tmp_path / "user-config.toml").write_text('[defaults]\ncost_policy = "local_only"\n')

    def execute(_argv):
        session = ACTIVE_SESSION.get()
        assert session is not None
        with session.connection() as connection:
            row = connection.execute("SELECT cost_policy FROM coding_sessions").fetchone()
            assert row[0] == "local_only"
        return 0

    monkeypatch.setattr(repo_coding_assistant, "_main", execute)
    assert (
        repo_coding_assistant.main(
            [
                "Review",
                "--execute",
                "--repo-root",
                str(tmp_path),
                "--coding-session",
                "new",
                "--coding-session-db",
                str(database),
            ]
        )
        == 0
    )
    assert ACTIVE_SESSION.get() is None
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT status FROM coding_sessions").fetchone()[0] == "completed"


def test_invalid_session_options_fail_before_creating_storage(tmp_path):
    from ai_provider import repo_coding_assistant

    database = tmp_path / "sessions.sqlite3"
    with pytest.raises(SystemExit) as exc:
        repo_coding_assistant.main(
            ["Review", "--coding-session", "new", "--coding-session-db", str(database)]
        )
    assert exc.value.code == 2
    assert not database.exists()
