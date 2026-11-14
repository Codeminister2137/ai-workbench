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
        assert "user request" in run["instruction"]
        return {"status": "completed", "stdout_tail": "Done.", "mai_session_id": "mai-1"}

    outcome = chat.send(
        session.session_id, "user request", stores=stores, mode="agent", agent_executor=fake_execute
    )
    assert outcome.execution_status == "completed"
    assert "Staged files" in outcome.response_text
    assert "app.py" in outcome.response_text
    assert stores.get_chat_mode(session.session_id)["coding_session_id"] == "mai-1"


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
