"""Synthetic clients continue actual shared effects without reusing approvals."""

import json
import sqlite3
import subprocess
from io import StringIO
from typing import Any, cast

import pytest
from ai_agent.shared_approvals import TerminalApproval
from ai_orchestrator import AccessMethod
from ai_provider import repo_coding_assistant as cli
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.external_agents import ExternalAgentConfig, run_external_agent


@pytest.mark.parametrize("failure", ["usage_limit_reached", "server_overloaded"])
@pytest.mark.parametrize("preset", ["workspace_write", "interactive"])
@pytest.mark.parametrize("persist", [False, True])
def test_cli_shared_partial_effect_continuation(
    tmp_path, monkeypatch, capsys, failure, preset, persist
):
    catalog = tmp_path / "catalog.toml"
    catalog.write_text("""[[models]]
route_id = "codex"
provider = "openai"
product = "codex"
model = "test"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "high"
[models.capabilities]
chat = true
tools = true
[[models]]
route_id = "copilot"
provider = "github"
product = "github_copilot"
model = "auto"
location = "external"
access_method = "copilot_cli"
auth_method = "github_account_sign_in"
billing_source = "github_copilot_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "high"
[models.capabilities]
chat = true
tools = true
""")
    source = tmp_path / "source.py"
    source.write_text("value = 0\n")
    instructions = "Preserve protected.txt. Inspect before each change.\n" + "x" * 6000
    (tmp_path / "AGENTS.md").write_text(instructions)
    protected = tmp_path / "protected.txt"
    protected.write_text("assert value == 2\n")
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "copilot-test")
    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(True, "synthetic; no authentication"),
    )

    class Tty(StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr("ai_provider.external_agents.sys.stdin", Tty())
    approvals = []
    outcomes = iter([True, False, True])

    def approve(self, call, category):
        approvals.append((self.run_id, call.name, dict(call.arguments)))
        return next(outcomes)

    monkeypatch.setattr(TerminalApproval, "__call__", approve)
    runs, tasks, effects, timeouts, deadlines = [], [], [], [], []

    def serve(connection):
        def call(name, arguments):
            response = connection.send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            assert response is not None
            result = response["result"]
            receipt = result["structuredContent"]["metadata"]["shared_receipt"]
            assert receipt["run_id"] == runs[-1]
            effects.append(receipt)
            return result

        before, after = (0, 1) if len(runs) == 1 else (1, 2)
        assert f"value = {before}" in call("read_file", {"path": "source.py"})["content"][0]["text"]
        args = {
            "path": "source.py",
            "old_text": f"value = {before}",
            "new_text": f"value = {after}",
        }
        if len(runs) == 2 and preset == "interactive":
            assert call("edit_file", args)["isError"]
            assert source.read_text() == "value = 1\n"
        assert not call("edit_file", args)["isError"]
        assert source.read_text() == f"value = {after}\n"
        assert not call("read_file", {"path": "source.py"})["isError"]
        return 0

    def runner(command, **kwargs):
        if command[0] == "codex-test":
            settings = dict(
                value.split("=", 1) for value in command if value.startswith("mcp_servers.")
            )
            args = json.loads(settings["mcp_servers.repo_shared.args"])
            payload = kwargs["input"]
        else:
            settings = json.loads(command[command.index("--additional-mcp-config") + 1])
            args = settings["mcpServers"]["repo_shared"]["args"]
            payload = command[command.index("-p") + 1]
            assert "Route-failure continuation" in payload
            if persist:
                assert "Approvals from earlier invocations have expired" in payload
                assert "shared:" in payload and runs[0] in payload
                assert "Explicit decisions" in payload and "Preserve protected.txt" in payload
        assert instructions in payload
        assert "Set value to 2" in payload
        from ai_agent.http_proxy import HttpMcpConnection
        from ai_provider.coding_sessions import ACTIVE_SESSION

        connection = HttpMcpConnection(
            args[args.index("--proxy-url") + 1],
            kwargs["env"][args[args.index("--proxy-token-env") + 1]],
        )
        connection.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        connection.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        response = connection.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "read_file", "arguments": {"path": "source.py"}},
            }
        )
        assert response is not None
        observed = response["result"]["structuredContent"]["metadata"]["shared_receipt"]
        tasks.append(observed["task_id"])
        runs.append(observed["run_id"])
        if persist:
            session = ACTIVE_SESSION.get()
            assert session is not None and tasks[-1] == session.session_id
        timeouts.append(kwargs["timeout"])
        try:
            assert serve(connection) == 0
        finally:
            connection.close()
        return subprocess.CompletedProcess(
            command,
            1 if len(runs) == 1 else 0,
            json.dumps({"type": "error", "message": failure}) if len(runs) == 1 else "Completed",
            "",
        )

    def execute(prompt, config, **kwargs):
        assert config.shared_tool_profile == "coding"
        assert config.approval_policy == preset
        assert config.sandbox == "read-only"
        deadlines.append(kwargs["deadline"])
        return run_external_agent(prompt, config, runner=runner, **kwargs)

    monkeypatch.setattr(cli, "_run_external_agent", execute)
    database = tmp_path / "sessions.sqlite3"
    session_args = (
        [
            "--coding-session",
            "new",
            "--coding-session-db",
            str(database),
            "--session-decision",
            "Preserve protected.txt",
        ]
        if persist
        else []
    )
    assert (
        cli.main(
            [
                "--mode",
                "implement",
                "Set value to 2 in source.py.",
                "--repo-root",
                str(tmp_path),
                "--catalog",
                str(catalog),
                "--route-id",
                "codex",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "allowances_allowed",
                "--approval-policy",
                preset,
                "--shared-tools",
                "coding",
                "--skip-prompt-review",
                *session_args,
                "--away-minutes",
                "1",
                "--execute",
            ]
        )
        == 0
    )
    assert len(runs) == 2 and runs[0] != runs[1]
    assert tasks[0] == tasks[1]
    assert deadlines[0] == deadlines[1] and deadlines[0] is not None
    assert 0 < timeouts[1] <= timeouts[0] <= 60
    edits = [r for r in effects if r["operation"] == "edit_file" and r["authorized"]]
    assert len(edits) == 2
    assert source.read_text() == "value = 2\n"
    assert protected.read_text() == "assert value == 2\n"
    assert (tmp_path / "AGENTS.md").read_text() == instructions
    if preset == "interactive":
        assert [a[0] for a in approvals] == [runs[0], runs[1], runs[1]]
    else:
        assert not approvals
    if persist:
        with sqlite3.connect(database) as connection:
            assert (
                connection.execute("SELECT status FROM coding_sessions").fetchone()[0]
                == "completed"
            )
            rows = connection.execute("SELECT operation,status FROM coding_receipts").fetchall()
        assert len([r for r in rows if ":edit_file:" in r[0] and r[1] == "completed"]) == 2
        assert not any("value =" in operation for operation, _ in rows)
    else:
        assert not database.exists()
    assert "effective_route_id: copilot" in capsys.readouterr().out


def test_external_deadline_refuses_process_launch(tmp_path, monkeypatch):
    monkeypatch.setattr("ai_provider.external_agents.time.perf_counter", lambda: 2.0)
    config = ExternalAgentConfig(AccessMethod.CODEX_CLI, "fake", "auto", tmp_path, 60)
    with pytest.raises(subprocess.TimeoutExpired):
        run_external_agent(
            "Expired",
            config,
            deadline=1.0,
            runner=lambda *a, **kw: pytest.fail("Expired runner launched"),
        )


def test_external_output_cannot_extend_overall_deadline(tmp_path, monkeypatch):
    import ai_provider.external_agents as agents

    ticks = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(agents.time, "perf_counter", lambda: next(ticks))

    class Process:
        stdin = StringIO()
        stdout = StringIO("observed before deadline\nmore output\n")
        stderr = StringIO()
        killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    class Reader:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

        def join(self, **kwargs):
            pass

    monkeypatch.setattr(agents.threading, "Thread", Reader)
    process = Process()
    config = ExternalAgentConfig(AccessMethod.CODEX_CLI, "fake", "auto", tmp_path, 60)
    with pytest.raises(subprocess.TimeoutExpired) as error:
        run_external_agent(
            "Continue", config, deadline=1.0, popen_factory=lambda *a, **kw: cast(Any, process)
        )
    assert process.killed
    assert "observed before deadline" in error.value.output
