"""Agent-mode chat turns: routing, binding, staging, apply guards."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

import pytest
from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
from chat_agent import (
    ChatAgentError,
    apply_staged,
    build_chat_prompt,
    ensure_chat_worktree,
    split_agent_transcript,
)
from dashboard_chat import DashboardChat
from dashboard_config import DashboardConfig, load_config
from dashboard_stores import DashboardStores


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return completed.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "develop", str(root)], check=True, timeout=60)
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "user-config.toml").write_text("[defaults]\n", encoding="utf-8")
    (root / "app.py").write_text("v1", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "one")
    return root


@pytest.fixture
def chat(git_repo: Path, tmp_path: Path):
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(provider="ollama", model="fake", chat_agent_enabled=True)
    return DashboardChat(store, config, git_repo)


@pytest.fixture
def stores(tmp_path: Path):
    return DashboardStores(tmp_path / "data")


def test_agent_turn_binds_session_and_lists_staged(chat, stores, git_repo) -> None:
    session = chat.create_session(title="t")
    worktree = ensure_chat_worktree(git_repo, session.session_id)
    (worktree.path / "app.py").write_text("v2", encoding="utf-8")

    def fake_execute(run: dict) -> dict:
        # build_mai_argv renders Task from "body": an "instruction"-only
        # run used to deliver an empty task to Mai (2026-11-18).
        assert "user request" in run["body"]
        from mai_run import build_mai_argv

        prompt = build_mai_argv(run, repo_root=git_repo, user_config="u")[0]
        assert "Task:\n" in prompt and "user request" in prompt.split("Task:\n", 1)[1]
        return {"status": "completed", "stdout_tail": "Done.", "mai_session_id": "mai-1"}

    outcome = chat.send(
        session.session_id, "user request", stores=stores, mode="agent", agent_executor=fake_execute
    )
    assert outcome.execution_status == "completed"
    assert "Staged files" in outcome.response_text
    assert "app.py" in outcome.response_text
    assert stores.get_chat_mode(session.session_id)["coding_session_id"] == "mai-1"
    messages = chat.store.list_messages(session.session_id)
    from chat_agent import progress_path

    assert messages[-1].metadata["progress_path"] == str(
        progress_path(stores.data_dir, session.session_id, messages[0].message_id)
    )


def test_agent_turn_refuses_when_disabled(git_repo, tmp_path, stores) -> None:
    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(provider="ollama", model="fake")  # agent off by default
    chat = DashboardChat(store, config, git_repo)
    session = chat.create_session(title="t")
    outcome = chat.send(session.session_id, "hi", stores=stores, mode="agent")
    assert outcome.execution_status == "failed"
    assert "disabled" in (outcome.failure_reason or "")


def test_explicit_ask_overrides_stored_agent(chat, stores) -> None:
    session = chat.create_session(title="t")
    stores.set_chat_mode(session.session_id, mode="agent")
    calls: list = []

    class Relay:
        def __call__(self, **kwargs):
            calls.append(kwargs)
            from types import SimpleNamespace

            return SimpleNamespace(answer="relay answer", tool_receipts=[], iterations=1)

    chat.relay_runner = Relay()
    outcome = chat.send(session.session_id, "hi", stores=stores, mode="ask")
    assert calls and outcome.execution_status == "completed"


def test_mode_store_defaults_and_validates(stores) -> None:
    assert stores.get_chat_mode("s")["mode"] == "ask"
    stores.set_chat_mode("s", mode="agent")
    assert stores.get_chat_mode("s")["mode"] == "agent"
    with pytest.raises(Exception, match="ask or agent"):
        stores.set_chat_mode("s", mode="yolo")


def test_worktree_adopt_is_stable(git_repo) -> None:
    first = ensure_chat_worktree(git_repo, "abc123")
    second = ensure_chat_worktree(git_repo, "abc123")
    assert first == second
    assert first.branch == "chat/abc123"
    assert (first.path / "user-config.toml").is_file()


def test_worktree_requires_git_checkout(tmp_path) -> None:
    with pytest.raises(ChatAgentError, match="not a git checkout"):
        ensure_chat_worktree(tmp_path / "plain", "s")


def test_apply_guards(git_repo) -> None:
    worktree = ensure_chat_worktree(git_repo, "s1")
    (worktree.path / "app.py").write_text("v2", encoding="utf-8")
    (worktree.path / "new.py").write_text("new", encoding="utf-8")
    outcome = apply_staged(git_repo, worktree, ["app.py", "new.py"])
    assert outcome == {"applied": ["app.py", "new.py"], "refused": {}}
    assert (git_repo / "app.py").read_text(encoding="utf-8") == "v2"

    (worktree.path / "app.py").write_text("v3", encoding="utf-8")
    (git_repo / "app.py").write_text("live-edit", encoding="utf-8")
    outcome = apply_staged(git_repo, worktree, ["app.py", "../x", ".git/y", "gone.py"])
    assert outcome["applied"] == []
    assert set(outcome["refused"]) == {"app.py", "../x", ".git/y", "gone.py"}


def test_build_chat_prompt_states_convention() -> None:
    prompt = build_chat_prompt("digest", "do it")
    assert "do it" in prompt and "digest" in prompt
    assert "never push" in prompt.lower()
    for marker in ("Did:", "Found:", "Next:", "Needs owner:"):
        assert marker in prompt


def test_ask_always_parks_then_approves(tmp_path, git_repo, stores) -> None:
    from dashboard_chat import DashboardChat
    from dashboard_config import DashboardConfig

    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(
        provider="ollama", model="fake", chat_agent_enabled=True, chat_agent_approval="ask-always"
    )
    chat = DashboardChat(store, config, git_repo)
    session = chat.create_session(title="t")
    calls: list = []

    def fake_execute(run: dict) -> dict:
        calls.append(run)
        return {"status": "completed", "stdout_tail": "Done.", "mai_session_id": "m1"}

    parked = chat.send(
        session.session_id, "do it", stores=stores, mode="agent", agent_executor=fake_execute
    )
    assert parked.execution_status == "parked"
    assert calls == []
    assert stores.get_chat_mode(session.session_id)["pending_turn"]["text"] == "do it"
    resumed = chat.send(
        session.session_id,
        "do it",
        stores=stores,
        mode="agent",
        agent_executor=fake_execute,
        approved=True,
    )
    assert resumed.execution_status == "completed"
    assert len(calls) == 1


def test_park_rejects_double_park(stores) -> None:
    stores.park_chat_turn("s", "one")
    with pytest.raises(Exception, match="already parked"):
        stores.park_chat_turn("s", "two")
    pending = stores.take_parked_turn("s")
    assert pending["text"] == "one"
    with pytest.raises(Exception, match="No parked turn"):
        stores.take_parked_turn("s")


def test_yolo_auto_applies_staged(tmp_path, git_repo, stores) -> None:
    from dashboard_chat import DashboardChat
    from dashboard_config import DashboardConfig

    store = SQLiteChatTranscriptStore(tmp_path / "chats.sqlite3")
    config = DashboardConfig(
        provider="ollama", model="fake", chat_agent_enabled=True, chat_agent_approval="yolo"
    )
    chat = DashboardChat(store, config, git_repo)
    session = chat.create_session(title="t")
    worktree = ensure_chat_worktree(git_repo, session.session_id)
    (worktree.path / "app.py").write_text("v2", encoding="utf-8")

    def fake_execute(run: dict) -> dict:
        return {"status": "completed", "stdout_tail": "Done.", "mai_session_id": "m1"}

    outcome = chat.send(
        session.session_id, "do it", stores=stores, mode="agent", agent_executor=fake_execute
    )
    assert outcome.execution_status == "completed"
    assert outcome.response_text is not None
    assert "auto-applied 1" in outcome.response_text
    assert (git_repo / "app.py").read_text(encoding="utf-8") == "v2"


def test_heartbeat_and_config_validation(stores, tmp_path) -> None:
    record = stores.touch_chat_heartbeat("s")
    assert record["last_seen_at"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"chat_agent_approval": "sometimes"}), encoding="utf-8")
    with pytest.raises(ValueError, match="chat_agent_approval"):
        load_config(bad)


def _api(base: str, method: str, path: str, payload: dict | None = None) -> dict:
    from urllib.error import HTTPError

    request = Request(
        f"{base}{path}",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


def test_chat_mode_api_roundtrip(dashboard_server) -> None:
    created = _api(dashboard_server, "POST", "/api/chat/sessions", {"title": "t"})
    sid = created["id"]
    bad = _api(dashboard_server, "POST", f"/api/chat/sessions/{sid}/mode", {"mode": "agent"})
    assert bad["ok"] is False  # master switch off in test config
    ok = _api(dashboard_server, "POST", f"/api/chat/sessions/{sid}/mode", {"mode": "ask"})
    assert ok["mode"] == "ask"
    staged = _api(dashboard_server, "GET", f"/api/chat/sessions/{sid}/staged")
    assert staged["files"] == []


def test_progress_roundtrip_and_cap(tmp_path):
    from chat_agent import ProgressWriter, progress_path, read_progress

    path = progress_path(tmp_path, "session-1", "message-1")
    assert read_progress(path) == []
    writer = ProgressWriter(path)
    writer.append("Tool read caf\u00e9")
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["ts"] and row["line"] == "Tool read caf\u00e9"
    assert read_progress(path) == ["Tool read caf\u00e9"]
    for i in range(205):
        writer.append(str(i))
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"line":')
    assert read_progress(path) == [str(i) for i in range(5, 205)]
    with pytest.raises(ValueError):
        progress_path(tmp_path, "../escape", "m")
    ProgressWriter(tmp_path).append("unwritable directory")


def test_progress_api_disabled(dashboard_server):
    assert _api(dashboard_server, "GET", "/api/chat/sessions/unknown/progress?message_id=m") == {
        "ok": True,
        "lines": [],
        "staged": [],
    }


def test_progress_api_existing_worktree(tmp_path, monkeypatch):
    from chat_agent import ProgressWriter, progress_path
    from dashboard_web_app import DashboardRequestHandler

    handler = object.__new__(DashboardRequestHandler)
    handler.data_dir = tmp_path / "data"
    handler.repo_root = tmp_path
    stores = DashboardStores(handler.data_dir)
    stores.set_chat_mode("s", mode="agent")
    monkeypatch.setattr(handler, "_stores", lambda: stores)
    responses = []
    monkeypatch.setattr(handler, "_send_json", responses.append)
    config = DashboardConfig(chat_agent_enabled=True)
    handler._send_chat_progress(config, "s", "m")
    assert responses[-1]["lines"] == []
    assert not (tmp_path / ".tmp").exists()
    worktree = tmp_path / ".tmp/chat-worktrees/s"
    worktree.mkdir(parents=True)
    ProgressWriter(progress_path(handler.data_dir, "s", "m")).append("Tool read")
    monkeypatch.setattr("chat_agent.staged_files", lambda path: [{"path": "a.py", "status": "M"}])
    handler._send_chat_progress(config, "s", "m")
    assert responses[-1]["lines"] == ["Tool read"]
    assert responses[-1]["staged"] == [{"path": "a.py", "status": "M"}]
    handler._send_chat_progress(config, "../escape", "m")
    assert responses[-1]["lines"] == []
    stores.set_chat_mode("s", mode="ask")
    handler._send_chat_progress(config, "s", "m")
    assert responses[-1] == {"ok": True, "lines": [], "staged": []}


AGENT_TRANSCRIPT = """\
coding_session_id: abc123
=== Repo Coding Assistant ===
mode: implement
external_agent_activity: thread.started
external_agent_activity: turn.started
external_agent_activity: command_execution in_progress - command: "git status"
external_agent_activity: command_execution completed - command: "git status"
external_agent_activity item.completed: The task text is empty. I will check state.
=== External agent diagnostics ===
external_agent_returncode: 0

### Agent report
Branch is clean. What should this run implement?
"""


def test_splitter_extracts_report_and_collapses_commands() -> None:
    view = split_agent_transcript(AGENT_TRANSCRIPT)
    assert view.has_agent_markers is True
    assert view.report == "### Agent report\nBranch is clean. What should this run implement?"
    assert view.commands == ({"command": "git status", "status": "completed"},)


def test_splitter_falls_back_without_markers() -> None:
    view = split_agent_transcript("Just a plain answer.")
    assert view.has_agent_markers is False
    assert view.report == "Just a plain answer."
    assert view.commands == ()


def test_splitter_accepts_summary_closeout_and_keeps_raw_commands() -> None:
    text = (
        "external_agent_activity: turn.started\n"
        "external_agent_activity: command_execution completed - command: not-json\n"
        "## **SUMMARY**\n- Changed: x\n"
    )
    view = split_agent_transcript(text)
    assert view.has_agent_markers is True
    assert view.report == "## **SUMMARY**\n- Changed: x"
    assert view.commands == ({"command": "not-json", "status": "completed"},)


def test_splitter_keeps_args_outside_quoted_exe() -> None:
    text = (
        "external_agent_activity: command_execution completed - command: "
        "\"C:\\\\Windows\\\\powershell.exe\" -Command 'git status --short'\n"
    )
    view = split_agent_transcript(text)
    assert view.commands == (
        {
            "command": "C:\\Windows\\powershell.exe -Command 'git status --short'",
            "status": "completed",
        },
    )


def test_splitter_keeps_last_status_per_command() -> None:
    text = (
        'external_agent_activity: command_execution in_progress - command: "a"\n'
        'external_agent_activity: command_execution completed - command: "b"\n'
        'external_agent_activity: command_execution failed - command: "a"\n'
    )
    view = split_agent_transcript(text)
    assert view.commands == (
        {"command": "a", "status": "failed"},
        {"command": "b", "status": "completed"},
    )
