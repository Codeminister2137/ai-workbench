"""Actual tool/loop/CLI boundaries with synthetic credentials and no inference."""

from dataclasses import replace

import pytest
from ai_agent import AgentLoop
from ai_agent.contracts import ToolCall, ToolCategory, ToolDefinition, ToolResult
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.tools import CreateFileTool, ReadFileTool, ToolContext, ToolRegistry
from ai_agent.tools.base import BaseTool
from ai_provider import AIMessage, AIResponse, AIToolCall, BackendInfo, BackendLocation, MessageRole
from ai_provider.errors import ProviderError

SECRET = "synthetic-credential-only-in-fixture-67890"


@pytest.mark.parametrize("name", [".env", ".env.local", ".ENV", ".modal.toml", ".codex/auth.json"])
def test_sensitive_files_refused_before_read_or_write(tmp_path, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SECRET)
    context = ToolContext(tmp_path)
    read = ReadFileTool().run(ToolCall("read_file", {"path": name}), context)
    write = CreateFileTool().run(
        ToolCall("create_file", {"path": name, "content": "replaced", "overwrite": True}), context
    )
    assert read.is_error and write.is_error
    assert SECRET not in read.output and path.read_text() == SECRET


def test_safe_example_and_alias_resolution(tmp_path):
    (tmp_path / ".env.example").write_text("API_KEY=<placeholder>")
    context = ToolContext(tmp_path)
    assert not ReadFileTool().run(ToolCall("read_file", {"path": ".env.example"}), context).is_error
    (tmp_path / ".env").write_text(SECRET)
    try:
        (tmp_path / "alias.txt").symlink_to(tmp_path / ".env")
    except OSError:
        pytest.skip("Creating symlinks unavailable")
    assert ReadFileTool().run(ToolCall("read_file", {"path": "alias.txt"}), context).is_error


def test_refusal_does_not_echo_a_credential_in_the_call_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    result = ReadFileTool().run(
        ToolCall("read_file", {"path": ".env"}, call_id=SECRET), ToolContext(tmp_path)
    )
    assert result.is_error and result.call_id is None and SECRET not in repr(result)


class EchoTool(BaseTool):
    @property
    def definition(self):
        return ToolDefinition("echo_fixture", "synthetic diagnostic", ToolCategory.READ)

    def __init__(self, mode):
        self.mode = mode

    def execute(self, arguments, context):
        if self.mode == "exception":
            raise ValueError(SECRET)
        return ToolResult(
            "echo_fixture", SECRET if self.mode == "text" else "safe", metadata={"value": SECRET}
        )


@pytest.mark.parametrize("mode", ["text", "metadata", "exception"])
def test_tool_text_metadata_and_exceptions_withheld_before_receipts(tmp_path, mode):
    context = replace(ToolContext(tmp_path), credential_secrets=(SECRET,))
    result = EchoTool(mode).run(ToolCall("echo_fixture", {}), context)
    assert result.is_error and result.metadata == {"credential_output_refused": True}
    assert SECRET not in repr(result)


def test_actual_loop_does_not_forward_env_file_or_secret_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    (tmp_path / ".env").write_text(SECRET)
    requests = []

    class Client:
        backend = BackendInfo("ollama", "scripted-fixture", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            assert SECRET not in repr(request)
            calls = (
                (AIToolCall("read", "read_file", {"path": ".env"}),) if len(requests) == 1 else ()
            )
            return AIResponse(
                AIMessage(
                    MessageRole.ASSISTANT, "" if calls else "Refusal observed", tool_calls=calls
                ),
                self.backend,
                tool_calls=calls,
            )

        def stream(self, request):
            raise NotImplementedError

    result = AgentLoop(
        Client(),
        ToolRegistry((ReadFileTool(),)),
        ToolContext(tmp_path),
        permissions=PermissionManager(PermissionPolicy.read_only()),
        max_iterations=2,
    ).run("Inspect the synthetic fixture")
    assert len(requests) == 2 and result.tool_results[0].is_error
    with pytest.raises(ProviderError, match="Credential-bearing"):
        AgentLoop(Client(), ToolRegistry(()), ToolContext(tmp_path)).run(SECRET)
    assert len(requests) == 2


def test_official_cli_refused_before_start(tmp_path, monkeypatch):
    from ai_orchestrator import AccessMethod
    from ai_provider.external_agents import ExternalAgentConfig, run_external_agent

    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    config = ExternalAgentConfig(AccessMethod.CODEX_CLI, "fixture", "auto", tmp_path, 10)
    with pytest.raises(ProviderError, match="Credential-bearing"):
        run_external_agent(SECRET, config, runner=lambda *a, **k: pytest.fail("CLI started"))


def test_real_command_output_is_withheld_and_mcp_metadata_is_safe(tmp_path, monkeypatch):
    import json
    import os
    import shlex
    import subprocess
    import sys

    from ai_agent.mcp_server import handle_mcp_message
    from ai_agent.tools.shell import RunCommandTool

    monkeypatch.setenv("SYNTHETIC_API_KEY", SECRET)
    argv = [sys.executable, "-c", "import os; print(os.environ['SYNTHETIC_API_KEY'])"]
    command = subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
    result = RunCommandTool().run(
        ToolCall("run_command", {"command": command}), ToolContext(tmp_path)
    )
    assert result.is_error and result.metadata == {"credential_output_refused": True}
    assert SECRET not in result.output
    reply = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "echo_fixture",
                "arguments": {},
            },
        },
        registry=ToolRegistry((EchoTool("metadata"),)),
        context=ToolContext(tmp_path),
    )
    assert SECRET not in json.dumps(reply)
    assert reply is not None and reply["result"]["isError"]
