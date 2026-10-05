"""Real loopback transport and children, with synthetic clients and no inference."""

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ai_agent.http_proxy import HttpMcpConnection
from ai_agent.mcp_server import PROTOCOL_VERSION
from ai_orchestrator import AccessMethod
from ai_provider.coding_sessions import ACTIVE_SESSION, CodingSession
from ai_provider.external_agents import ExternalAgentConfig, run_external_agent
from ai_provider.foreground_tools import ACTIVE_FOREGROUND, ForegroundTools


def initialize(config):
    connection = HttpMcpConnection(
        config.shared_host_url, config.shared_child_env[config.shared_token_env]
    )
    response = connection.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fixture", "version": "1"},
            },
        }
    )
    assert response is not None
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    connection.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return connection


def call(connection, operation, **arguments):
    return connection.send(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": operation, "arguments": arguments},
        }
    )["result"]


def config(workspace, method=AccessMethod.CODEX_CLI, policy="trusted_local"):
    return ExternalAgentConfig(
        method,
        "fixture-client",
        "auto",
        workspace,
        10,
        sandbox="read-only",
        approval_policy=policy,
        shared_tool_profile="coding",
        shared_task_id="fixture-task",
    )


def test_inflight_child_survives_actual_external_route_switch_and_old_scope_expires(tmp_path):
    session = CodingSession.open(tmp_path / "state.sqlite3", "new", tmp_path, "tests", [])
    foreground = ForegroundTools(tmp_path, session)
    foreground_token = ACTIVE_FOREGROUND.set(foreground)
    session_token = ACTIVE_SESSION.set(session)
    connections = []
    handle = None
    pid = None

    def runner(command, **kwargs):
        nonlocal handle, pid
        assert "--proxy-url" in " ".join(command)
        name = next(key for key in kwargs["env"] if key.startswith("AI_PROJECTS_MCP_"))
        secret = kwargs["env"][name]
        assert secret not in " ".join(command)
        assert foreground.host is not None
        connection = HttpMcpConnection(foreground.host.url, secret)
        connection.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        connection.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        connections.append(connection)
        if handle is None:
            result = call(
                connection,
                "process_start",
                argv=[
                    sys.executable,
                    "-u",
                    "-c",
                    "import time; print('in-flight', flush=True); time.sleep(30)",
                ],
            )
            assert not result["isError"]
            metadata = result["structuredContent"]["metadata"]
            handle, pid = metadata["process_handle"], metadata["pid"]
        else:
            result = call(connection, "process_status", process_handle=handle)
            assert not result["isError"]
            assert result["structuredContent"]["metadata"]["pid"] == pid
            assert result["structuredContent"]["metadata"]["status"] == "running"
            assert not call(connection, "process_stop", process_handle=handle)["isError"]
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    try:
        run_external_agent("start", config(tmp_path), runner=runner)
        with pytest.raises(HTTPError) as error:
            call(connections[0], "process_status", process_handle=handle)
        assert error.value.code == 401
        run_external_agent("continue", config(tmp_path, AccessMethod.COPILOT_CLI), runner=runner)
        assert handle is not None
        assert len(foreground.supervisor.processes) == 1
        assert foreground.supervisor.status(handle)["returncode"] is not None
        assert "process_start" in session.handoff()
        assert pid == session.supervisor.status(handle)["pid"]
    finally:
        foreground.close()
        ACTIVE_FOREGROUND.reset(foreground_token)
        ACTIVE_SESSION.reset(session_token)


def test_permissions_session_binding_deadline_and_shutdown(tmp_path):
    foreground = ForegroundTools(tmp_path)
    handle = foreground.supervisor.start([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with foreground.invocation(config(tmp_path, policy="read_only")) as scoped:
            connection = initialize(scoped)
            assert call(connection, "process_start", argv=[sys.executable])["isError"]
            assert call(connection, "process_stop", process_handle=handle)["isError"]
            assert not call(connection, "process_status", process_handle=handle)["isError"]
            connection.close()
            with pytest.raises(HTTPError) as error:
                connection.send({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            assert error.value.code == 400
        with foreground.invocation(config(tmp_path), deadline=time.perf_counter() - 1) as scoped:
            with pytest.raises(HTTPError) as error:
                initialize(scoped)
            assert error.value.code == 401
        with foreground.invocation(config(tmp_path)) as scoped:
            connection = initialize(scoped)
            with foreground.invocation(config(tmp_path)) as other:
                stranger = initialize(other)
                stranger.session = connection.session
                with pytest.raises(HTTPError) as error:
                    call(stranger, "process_status", process_handle=handle)
                assert error.value.code == 404
            headers = {
                "Authorization": "Bearer " + connection.token,
                "Origin": "https://evil.example",
            }
            assert scoped.shared_host_url is not None
            with pytest.raises(HTTPError) as error:
                urlopen(Request(scoped.shared_host_url, headers=headers), timeout=5)
            assert error.value.code == 403
    finally:
        foreground.close()
    assert foreground.supervisor.status(handle)["returncode"] is not None
    replacement = ForegroundTools(tmp_path)
    try:
        with replacement.invocation(config(tmp_path)) as scoped:
            assert call(initialize(scoped), "process_status", process_handle=handle)["isError"]
    finally:
        replacement.close()


def test_interrupted_invocation_revokes_access_and_cli_finally_cleans_child(tmp_path):
    foreground = ForegroundTools(tmp_path)
    active = ACTIVE_FOREGROUND.set(foreground)
    saved = []

    def runner(command, **kwargs):
        name = next(key for key in kwargs["env"] if key.startswith("AI_PROJECTS_MCP_"))
        saved.append(kwargs["env"][name])
        raise KeyboardInterrupt

    try:
        with pytest.raises(KeyboardInterrupt):
            run_external_agent("start", config(tmp_path), runner=runner)
        assert foreground.host is not None
        assert not foreground.host.active(saved[0])
    finally:
        foreground.close()
        ACTIVE_FOREGROUND.reset(active)


@pytest.mark.parametrize("adapter", ["codex", "copilot", "kiro"])
def test_real_stdio_proxy_connects_without_token_in_configuration(tmp_path, adapter):
    foreground = ForegroundTools(tmp_path)
    try:
        with foreground.invocation(config(tmp_path)) as scoped:
            from ai_provider.external_agents import _shared_run_context
            from ai_provider.shared_client_tools import (
                codex_inspection_overrides,
                copilot_inspection_options,
                inspection_server,
                kiro_inspection_agent,
            )

            settings = cast(
                dict[str, Any], inspection_server(tmp_path, _shared_run_context(scoped))
            )
            run = _shared_run_context(scoped)
            assert scoped.shared_child_env is not None and scoped.shared_token_env is not None
            if adapter == "codex":
                overrides = codex_inspection_overrides(tmp_path, run)
                entry = next(value for value in overrides if ".env_vars=" in value)
                forwarded = json.loads(entry.split("=", 1)[1])
                child_env = {key: scoped.shared_child_env[key] for key in forwarded}
            else:
                if adapter == "copilot":
                    options = copilot_inspection_options(tmp_path, run)
                    server = json.loads(options[options.index("--additional-mcp-config") + 1])[
                        "mcpServers"
                    ]["repo_shared"]
                else:
                    agent = cast(dict[str, Any], kiro_inspection_agent(tmp_path, "fixture", run))
                    server = agent["mcpServers"]["repo_shared"]
                child_env = {
                    key: scoped.shared_child_env[value.removeprefix("${").removesuffix("}")]
                    for key, value in server["env"].items()
                }
            assert scoped.shared_child_env[scoped.shared_token_env] not in json.dumps(settings)
            payload = (
                "\n".join(
                    json.dumps(message)
                    for message in (
                        {"jsonrpc": "2.0", "id": 0, "method": "server/discover"},
                        {"id": 1, "method": "initialize"},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"},
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    )
                )
                + "\n"
            )
            result = subprocess.run(
                [settings["command"], *settings["args"]],
                input=payload,
                capture_output=True,
                text=True,
                env={**os.environ, **child_env},
                timeout=10,
            )
            assert result.returncode == 0, result.stderr
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            assert responses[0]["error"]["code"] == -32601
            names = {tool["name"] for tool in responses[2]["result"]["tools"]}
            assert {"process_start", "process_stop", "process_status"} <= names
            assert foreground.host is not None
            assert not foreground.host.scopes[next(iter(foreground.host.scopes))].sessions
    finally:
        foreground.close()


def test_revocation_during_human_approval_refuses_effect_and_allows_shutdown(tmp_path, monkeypatch):
    from ai_agent.shared_approvals import TerminalApproval

    waiting = threading.Event()
    results = []

    def approve(self, call, category):
        waiting.set()
        until = time.monotonic() + 5
        while self.is_active() and time.monotonic() < until:
            time.sleep(0.01)
        return True  # An expired approval must still refuse the operation.

    monkeypatch.setattr(TerminalApproval, "__call__", approve)
    foreground = ForegroundTools(tmp_path)
    from dataclasses import replace

    invocation = foreground.invocation(
        replace(
            config(tmp_path, policy="interactive"),
            shared_terminal_approvals=True,
        )
    )
    try:
        scoped = invocation.__enter__()
        connection = initialize(scoped)
        worker = threading.Thread(
            target=lambda: results.append(
                call(connection, "create_file", path="denied.txt", content="must not appear")
            )
        )
        worker.start()
        assert waiting.wait(timeout=5)
        invocation.__exit__(None, None, None)
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert results[0]["isError"]
        assert not (tmp_path / "denied.txt").exists()
    finally:
        foreground.close()


def test_foreground_refuses_task_or_workspace_change(tmp_path):
    from dataclasses import replace

    foreground = ForegroundTools(tmp_path)
    try:
        with foreground.invocation(config(tmp_path)):
            pass
        with pytest.raises(ValueError, match="task changed"):
            with foreground.invocation(replace(config(tmp_path), shared_task_id="another-task")):
                pass
        with pytest.raises(ValueError, match="workspace changed"):
            with foreground.invocation(config(tmp_path.parent)):
                pass
    finally:
        foreground.close()


def test_official_sdk_client_interoperates_with_foreground_host(tmp_path):
    import asyncio

    sdk = pytest.importorskip("mcp")
    http = pytest.importorskip("httpx2")
    transport_module = pytest.importorskip("mcp.client.streamable_http")
    foreground = ForegroundTools(tmp_path)

    async def exercise(scoped):
        bearer = scoped.shared_child_env[scoped.shared_token_env]
        async with http.AsyncClient(
            headers={"Authorization": "Bearer " + bearer}, timeout=5, trust_env=False
        ) as http_client:
            transport = transport_module.streamable_http_client(
                scoped.shared_host_url, http_client=http_client
            )
            async with sdk.Client(transport) as client:
                listed = await client.list_tools()
                assert "process_status" in {tool.name for tool in listed.tools}
                result = await client.call_tool("process_status", {"process_handle": "missing"})
                assert result.is_error

    try:
        with foreground.invocation(config(tmp_path)) as scoped:
            asyncio.run(exercise(scoped))
    finally:
        foreground.close()
