"""Offline permission, terminal isolation, scoped receipt and mapping contracts."""

import json
import os
import subprocess
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest
from ai_agent import mcp_server, shared_approvals
from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition
from ai_agent.mcp_server import handle_mcp_message, run_stdio_server
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.shared_approvals import TerminalApproval, scoped_registry
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools import ToolContext
from ai_agent.tools.base import BaseTool, ToolRegistry
from ai_orchestrator import AccessMethod
from ai_provider.acceptance_processes import process_identity
from ai_provider.coding_sessions import ACTIVE_SESSION, CodingSession
from ai_provider.external_agents import (
    ExternalAgentConfig,
    build_external_agent_command,
    run_external_agent,
)


def scoped(path: Path, preset="interactive", callback=None, run_id="run-one"):
    return scoped_registry(
        shared_tool_registry("coding"),
        PermissionManager(PermissionPolicy.from_approval_preset(preset), callback),
        path,
        "task-one",
        run_id,
    )


def call(registry, path, name="create_file", arguments=None):
    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments or {"path": "new.txt", "content": "private fixture"},
            },
        },
        registry=registry,
        context=ToolContext(path),
    )
    assert response is not None
    return response["result"]


def owner_args():
    return ["--owner-pid", str(os.getpid()), "--owner-birth", process_identity(os.getpid()) or ""]


@pytest.mark.parametrize(
    "preset,authorized",
    [
        ("read_only", False),
        ("interactive", False),
        ("workspace_write", True),
        ("trusted_local", True),
    ],
)
def test_presets_authorize_or_deny_without_human(tmp_path: Path, preset, authorized):
    response = call(scoped(tmp_path, preset), tmp_path)
    receipt = response["structuredContent"]["metadata"]["shared_receipt"]
    assert receipt["authorized"] is authorized
    assert response["isError"] is not authorized
    assert (tmp_path / "new.txt").exists() is authorized
    assert receipt["task_id"] == "task-one" and receipt["run_id"] == "run-one"
    assert "private fixture" not in json.dumps(receipt)


def test_approval_applies_once_and_does_not_survive_restart(tmp_path: Path):
    observed = []
    answers = iter([True, False])

    def approve(call, category):
        observed.append((call.name, call.arguments, category))
        return next(answers)

    registry = scoped(tmp_path, callback=approve)
    assert not call(registry, tmp_path)["isError"]
    assert call(registry, tmp_path, arguments={"path": "second.txt", "content": "no"})["isError"]
    assert len(observed) == 2
    assert not (tmp_path / "second.txt").exists()
    assert call(
        scoped(tmp_path, run_id="restart"),
        tmp_path,
        arguments={"path": "third.txt", "content": "no"},
    )["isError"]


class ShellProbe(BaseTool):
    @property
    def definition(self):
        return ToolDefinition("probe", "Synthetic shell", ToolCategory.SHELL)

    def execute(self, arguments, context):
        pytest.fail("unapproved shell executed")


@pytest.mark.parametrize("preset", ["read_only", "interactive", "workspace_write"])
def test_unattended_shell_is_denied(preset, tmp_path):
    registry = scoped_registry(
        ToolRegistry((ShellProbe(),)),
        PermissionManager(PermissionPolicy.from_approval_preset(preset)),
        tmp_path,
        "task",
        "run",
    )
    assert call(registry, tmp_path, "probe", {"command": "synthetic"})["isError"]


def test_workspace_and_tool_boundary_remain_required_after_approval(tmp_path):
    registry = scoped(tmp_path, "trusted_local")
    outside = tmp_path.parent / "outside-mutation-fixture.txt"
    assert call(registry, tmp_path, arguments={"path": str(outside), "content": "no"})["isError"]
    assert not outside.exists()
    another = tmp_path / "different"
    another.mkdir()
    assert call(registry, another)["isError"]


class Tty(StringIO):
    def isatty(self):
        return True

    def close(self):
        pass


@pytest.mark.parametrize(
    "answer,approved", [("yes\n", True), ("no\n", False), ("", False), ("y\n", False)]
)
def test_terminal_prompt_never_reads_mcp_stdio(tmp_path, monkeypatch, answer, approved):
    reader, writer = Tty(answer), Tty()
    names = []

    def opener(name, mode="r", **kwargs):
        names.append(name)
        return reader if mode == "r" else writer

    monkeypatch.setattr(shared_approvals, "open", opener, raising=False)
    assert (
        TerminalApproval("task", "run", tmp_path)(
            ToolCall("edit_file", {"path": "file\x1b[2J.txt", "new_text": "changed"}),
            ToolCategory.WRITE,
        )
        is approved
    )
    assert all(name in {"CONIN$", "CONOUT$", "/dev/tty"} for name in names)
    preview = writer.getvalue()
    assert "task" in preview and "run" in preview and str(tmp_path) in preview.replace("\\\\", "\\")
    assert "\x1b" not in preview and "\\u001b" in preview


def test_terminal_unavailable_or_unbounded_operation_denies(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("no controlling terminal")

    monkeypatch.setattr(shared_approvals, "open", unavailable, raising=False)
    approve = TerminalApproval("task", "run", tmp_path)
    assert not approve(ToolCall("run_command", {"command": "fixture"}), ToolCategory.SHELL)
    assert not approve(ToolCall("edit_file", {"new_text": "x" * 64001}), ToolCategory.WRITE)


def test_mcp_transport_stays_json_when_human_is_unavailable(tmp_path):
    message = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_file", "arguments": {"path": "new", "content": "no"}},
        }
    )
    output = StringIO()
    assert (
        run_stdio_server(
            workspace_root=tmp_path,
            input_stream=[message],
            output_stream=output,
            registry=scoped(tmp_path),
        )
        == 0
    )
    assert json.loads(output.getvalue())["result"]["isError"]


@pytest.mark.parametrize(
    "method", [AccessMethod.CODEX_CLI, AccessMethod.COPILOT_CLI, AccessMethod.KIRO_CLI]
)
def test_scoped_client_mappings_avoid_global_permission_bypass(tmp_path, method):
    config = ExternalAgentConfig(
        method,
        "client",
        "auto",
        tmp_path,
        10,
        sandbox="read-only",
        approval_policy="interactive",
        shared_tool_profile="coding",
    )
    command = build_external_agent_command(config, prompt="edit fixture")
    text = " ".join(command)
    assert "--trust-all-tools" not in text and "--dangerously-skip-permissions" not in text
    if method is not AccessMethod.KIRO_CLI:
        assert "--shared-profile" in text and "coding" in text
        assert all(name in text for name in CODING_PROFILE.tool_names)
    if method is AccessMethod.CODEX_CLI:
        assert command[command.index("--ask-for-approval") + 1] == "never"
    with pytest.raises(ValueError):
        build_external_agent_command(
            replace(config, sandbox="workspace-write"), prompt="edit fixture"
        )


def test_antigravity_coding_remains_excluded(tmp_path):
    config = ExternalAgentConfig(
        AccessMethod.ANTIGRAVITY_CLI,
        "client",
        "auto",
        tmp_path,
        10,
        sandbox="read-only",
        approval_policy="interactive",
        shared_tool_profile="coding",
    )
    with pytest.raises(NotImplementedError, match="not verified"):
        build_external_agent_command(config, prompt="edit fixture")


def test_per_run_kiro_configuration_changes_identity_and_is_removed(tmp_path):
    config = ExternalAgentConfig(
        AccessMethod.KIRO_CLI,
        "client",
        "auto",
        tmp_path,
        10,
        sandbox="read-only",
        approval_policy="workspace_write",
        shared_tool_profile="coding",
    )
    runs = []

    def runner(command, **kwargs):
        file = next((tmp_path / ".kiro/agents").glob("repo-shared-*.json"))
        settings = json.loads(file.read_text())
        assert settings["tools"] == settings["allowedTools"]
        args = settings["mcpServers"]["repo_shared"]["args"]
        runs.append(args[args.index("--run-id") + 1])
        assert args[args.index("--approval-policy") + 1] == "workspace_write"
        return subprocess.CompletedProcess(command, 0, "done", "")

    for _ in range(2):
        run_external_agent("fixture", config, runner=runner)
        assert not (tmp_path / ".kiro").exists()
    assert runs[0] != runs[1]


def test_mcp_session_receipts_reuse_storage_with_task_run_and_operation_digest(
    tmp_path, monkeypatch
):
    session = CodingSession.open(tmp_path / "session.sqlite3", "new", tmp_path, "Fixture", [])

    def serve(*, workspace_root, registry):
        result = call(registry, workspace_root)
        assert not result["isError"]
        return 0

    monkeypatch.setattr(mcp_server, "run_stdio_server", serve)
    assert (
        mcp_server.main(
            [
                "--workspace-root",
                str(tmp_path),
                "--shared-profile",
                "coding",
                "--approval-policy",
                "workspace_write",
                "--task-id",
                "task",
                "--run-id",
                "run",
                "--session-database",
                str(session.database),
                "--session-id",
                session.session_id,
                *owner_args(),
            ]
        )
        == 0
    )
    with session.connection() as connection:
        rows = connection.execute(
            "SELECT operation,status,output_sha256 FROM coding_receipts"
        ).fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "completed"
    assert rows[0]["operation"].startswith("shared:task:run:create_file:")
    assert rows[0]["output_sha256"]
    assert "private fixture" not in session.handoff() and "new.txt" not in session.handoff()


def test_mcp_session_denial_is_durable_and_does_not_mutate(tmp_path, monkeypatch):
    session = CodingSession.open(tmp_path / "session.sqlite3", "new", tmp_path, "Fixture", [])

    def serve(*, workspace_root, registry):
        assert call(registry, workspace_root)["isError"]
        return 0

    monkeypatch.setattr(mcp_server, "run_stdio_server", serve)
    assert (
        mcp_server.main(
            [
                "--workspace-root",
                str(tmp_path),
                "--shared-profile",
                "coding",
                "--task-id",
                "task",
                "--run-id",
                "run",
                "--session-database",
                str(session.database),
                "--session-id",
                session.session_id,
                *owner_args(),
            ]
        )
        == 0
    )
    with session.connection() as connection:
        assert connection.execute("SELECT status FROM coding_receipts").fetchone()[0] == "failed"
    assert not (tmp_path / "new.txt").exists()


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--task-id", "task"],
        ["--task-id", "task", "--run-id", "run", "--session-id", "missing"],
    ],
)
def test_missing_scope_or_receipt_store_refuses_startup(tmp_path, extra, monkeypatch):
    monkeypatch.setattr(
        mcp_server, "run_stdio_server", lambda **kwargs: pytest.fail("invalid server started")
    )
    with pytest.raises(SystemExit):
        mcp_server.main(["--workspace-root", str(tmp_path), "--shared-profile", "coding", *extra])


def test_external_run_passes_existing_session_without_renewing_authority(tmp_path):
    session = CodingSession.open(tmp_path / "session.sqlite3", "new", tmp_path, "Fixture", [])
    config = ExternalAgentConfig(
        AccessMethod.COPILOT_CLI,
        "client",
        "auto",
        tmp_path,
        10,
        sandbox="read-only",
        approval_policy="interactive",
        shared_tool_profile="coding",
    )

    def runner(command, **kwargs):
        document = json.loads(command[command.index("--additional-mcp-config") + 1])
        args = document["mcpServers"]["repo_shared"]["args"]
        assert args[args.index("--session-id") + 1] == session.session_id
        assert args[args.index("--approval-policy") + 1] == "interactive"
        assert "--terminal-approvals" not in args
        return subprocess.CompletedProcess(command, 0, "done", "")

    token = ACTIVE_SESSION.set(session)
    try:
        run_external_agent("fixture", config, runner=runner)
    finally:
        ACTIVE_SESSION.reset(token)


def test_owner_exit_during_approval_denies_before_effect(tmp_path):
    state = [True]

    def approve(*args):
        state[0] = False
        return True

    registry = scoped_registry(
        shared_tool_registry("coding"),
        PermissionManager(PermissionPolicy.interactive(), approve),
        tmp_path,
        "task",
        "run",
        is_active=lambda: state[0],
    )
    assert call(registry, tmp_path)["isError"]
    assert not (tmp_path / "new.txt").exists()


def test_dead_owner_never_prompts_or_mutates(tmp_path):
    registry = scoped_registry(
        shared_tool_registry("coding"),
        PermissionManager(
            PermissionPolicy.interactive(), lambda *args: pytest.fail("expired run prompted")
        ),
        tmp_path,
        "task",
        "run",
        is_active=lambda: False,
    )
    assert call(registry, tmp_path)["isError"]
    assert not (tmp_path / "new.txt").exists()
