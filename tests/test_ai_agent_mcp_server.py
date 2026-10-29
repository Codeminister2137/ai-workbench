from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_agent import mcp_server as _MCP_SERVER
from ai_agent.contracts import ToolResult
from ai_agent.mcp_server import (
    codex_mcp_tool_registry,
    handle_mcp_message,
    read_search_tool_registry,
    tool_definition_to_mcp_tool,
)
from ai_agent.tool_profiles import INSPECTION_PROFILE
from ai_agent.tools import CreateFileTool, ReadFileTool, ToolContext
from ai_orchestrator import AccessMethod, TaskCapability, TaskProfile
from ai_provider import FinishReason


def test_mcp_initialize_and_tools_list(tmp_path: Path) -> None:
    registry = read_search_tool_registry()
    context = ToolContext(workspace_root=tmp_path)

    initialized = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        registry=registry,
        context=context,
    )
    listed = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        registry=registry,
        context=context,
    )

    assert initialized is not None
    assert initialized["result"]["capabilities"] == {"tools": {}}
    assert "No write or shell tools" in initialized["result"]["instructions"]
    assert "delegate_task" not in initialized["result"]["instructions"]
    assert listed is not None
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    # read_search_tool_registry exposes only read/search tools — no write, shell, or git tools.
    expected = {tool.name for tool in read_search_tool_registry().list_definitions()}
    assert tool_names == expected
    assert "run_command" not in tool_names
    assert "create_file" not in tool_names
    assert "run_command" not in tool_names


def test_write_definition_is_not_annotated_read_only() -> None:
    descriptor = tool_definition_to_mcp_tool(CreateFileTool().definition)
    assert descriptor["annotations"]["readOnlyHint"] is False


def test_read_search_only_entrypoint_omits_model_backed_delegation(monkeypatch, tmp_path):
    captured = []

    def serve(*, workspace_root, registry):
        captured.extend(tool.name for tool in registry.list_definitions())
        assert workspace_root == tmp_path
        return 0

    monkeypatch.setattr(_MCP_SERVER, "run_stdio_server", serve)
    monkeypatch.setattr(
        _MCP_SERVER,
        "codex_mcp_tool_registry",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("delegation registry created")),
    )
    assert _MCP_SERVER.main(["--workspace-root", str(tmp_path), "--read-search-only"]) == 0
    # --read-search-only serves the inspection profile tools (read/search + git inspection).
    # Derived from INSPECTION_PROFILE so the test stays in sync when tools are added/removed.
    assert captured == list(INSPECTION_PROFILE.tool_names)


def test_codex_mcp_registry_includes_bounded_delegate_task(tmp_path: Path) -> None:
    registry = codex_mcp_tool_registry(catalog_path=tmp_path / "catalog.toml")
    context = ToolContext(workspace_root=tmp_path)

    initialized = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        registry=registry,
        context=context,
    )
    listed = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        registry=registry,
        context=context,
    )

    assert initialized is not None
    assert (
        "host-granted supervisor permissions and resource limits"
        in initialized["result"]["instructions"]
    )
    assert (
        "Unbound legacy runners remain local and read-only"
        in (initialized["result"]["instructions"])
    )
    assert listed is not None
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert set(tools) == {"read_file", "list_dir", "find_files", "grep_search", "delegate_task"}
    assert tools["delegate_task"]["annotations"]["readOnlyHint"] is False
    assert tools["delegate_task"]["annotations"]["destructiveHint"] is False
    assert "run_command" not in tools


def test_mcp_tools_call_runs_workspace_bounded_tool(tmp_path: Path) -> None:
    (tmp_path / "source.txt").write_text("first\nsecond\n", encoding="utf-8")
    registry = read_search_tool_registry()

    response = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "read_file",
                "arguments": {"path": "source.txt", "start_line": 2},
            },
        },
        registry=registry,
        context=ToolContext(workspace_root=tmp_path),
    )

    assert response is not None
    assert response["result"]["isError"] is False
    assert "   2 | second" in response["result"]["content"][0]["text"]


def test_mcp_write_message_escapes_non_ascii_for_stdio_transport() -> None:
    output = StringIO()

    _MCP_SERVER._write_message(  # noqa: SLF001 - regression for stdio transport encoding.
        output,
        {"jsonrpc": "2.0", "id": 1, "result": {"text": "non-breaking hyphen: \u2011"}},
    )

    text = output.getvalue()
    assert "\\u2011" in text
    assert "\u2011" not in text


def _delegate_through_mcp(
    tmp_path: Path,
    monkeypatch,
    *,
    content: str = "child findings",
    pending_response: bool = False,
    pending_message: bool = False,
    finish_reason: FinishReason = FinishReason.STOP,
    tool_results: tuple[ToolResult, ...] = (),
) -> tuple[dict, dict[str, TaskProfile]]:
    """Call the MCP delegate_task tool with a synthetic child run."""

    class FakeAgentLoop:
        def __init__(self, client, registry, context, *, max_iterations):
            self.client = client
            self.registry = registry
            self.context = context
            self.max_iterations = max_iterations

        def run(self, prompt, *, model, privacy_class):
            return SimpleNamespace(
                response=SimpleNamespace(
                    message=SimpleNamespace(
                        content=content,
                        tool_calls=("pending",) if pending_message else (),
                    ),
                    tool_calls=("pending",) if pending_response else (),
                    finish_reason=finish_reason,
                ),
                iterations=1,
                tool_results=tool_results,
            )

    target = SimpleNamespace(
        route_id="local-child",
        access_method=AccessMethod.LOCAL_RUNTIME,
        provider="ollama",
        model="child-model",
        base_url="http://localhost:11434",
        timeout_seconds=30.0,
    )
    orchestration = SimpleNamespace(
        is_ready=True,
        execution_plan=SimpleNamespace(target=target),
        failure_reason=None,
        status=SimpleNamespace(value="ready"),
    )
    captured: dict[str, TaskProfile] = {}

    def fake_prepare_execution(prompt, profile, *args, **kwargs):
        captured["profile"] = profile
        return orchestration

    monkeypatch.setattr(_MCP_SERVER, "load_model_catalog", lambda path: ())
    monkeypatch.setattr(_MCP_SERVER, "prepare_execution", fake_prepare_execution)
    monkeypatch.setattr(_MCP_SERVER, "create_chat_client", lambda config: object())
    monkeypatch.setattr(_MCP_SERVER, "AgentLoop", FakeAgentLoop)
    registry = codex_mcp_tool_registry(catalog_path=tmp_path / "catalog.toml")

    reply = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "delegate_task", "arguments": {"task": "Summarize README.md"}},
        },
        registry=registry,
        context=ToolContext(workspace_root=tmp_path),
    )
    assert reply is not None
    return reply, captured


def test_mcp_delegate_task_reports_execution_fact_after_recovered_tool_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reply, captured = _delegate_through_mcp(
        tmp_path,
        monkeypatch,
        tool_results=(ToolResult("read_file", "synthetic earlier failure", is_error=True),),
    )

    result = reply["result"]
    # ADR-078: the legacy boolean keeps reporting historical tool errors.
    assert result["isError"] is True
    text = result["content"][0]["text"]
    structured = result["structuredContent"]
    assert "Delegated task status: failed" in text
    assert "Execution complete: true (final response returned (finish_reason=stop));" in text
    assert "task outcome still requires independent validation" in text
    assert "Tool error evidence (historical; recovery is not independently verified):" in text
    assert "read_file: synthetic earlier failure" in text
    assert "Route: local-child" in text
    assert "Tool surface: read/search only" in text
    assert structured["output"] == text
    assert structured["metadata"]["child_response"] == "child findings"
    assert structured["metadata"]["execution_complete"] is True
    assert structured["metadata"]["tool_errors"] == [
        {"name": "read_file", "output": "synthetic earlier failure", "truncated": False}
    ]
    profile = captured["profile"]
    assert profile.required_capabilities == frozenset({TaskCapability.CHAT, TaskCapability.TOOLS})


def test_mcp_delegate_task_clean_run_is_complete_without_error_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reply, _ = _delegate_through_mcp(tmp_path, monkeypatch)

    result = reply["result"]
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "Delegated task status: completed" in text
    assert "Execution complete: true (final response returned (finish_reason=stop));" in text
    assert "Tool error evidence" not in text
    assert result["structuredContent"]["metadata"]["tool_errors"] == []
    assert result["structuredContent"]["metadata"]["execution_complete"] is True


@pytest.mark.parametrize(
    "content,pending_response,pending_message,finish_reason,legacy_error,reason",
    [
        ("", False, False, FinishReason.STOP, True, "empty final response"),
        ("child findings", True, False, FinishReason.STOP, True, "unresolved tool calls"),
        ("child findings", False, True, FinishReason.STOP, False, "unresolved tool calls"),
        (
            "child findings",
            False,
            False,
            FinishReason.LENGTH,
            False,
            "provider output length limit",
        ),
        (
            "child findings",
            False,
            False,
            FinishReason.ERROR,
            False,
            "provider error finish reason",
        ),
    ],
)
def test_mcp_delegate_task_reports_why_execution_is_incomplete(
    tmp_path: Path,
    monkeypatch,
    content: str,
    pending_response: bool,
    pending_message: bool,
    finish_reason: FinishReason,
    legacy_error: bool,
    reason: str,
) -> None:
    reply, _ = _delegate_through_mcp(
        tmp_path,
        monkeypatch,
        content=content,
        pending_response=pending_response,
        pending_message=pending_message,
        finish_reason=finish_reason,
    )

    result = reply["result"]
    assert result["isError"] is legacy_error
    text = result["content"][0]["text"]
    assert f"Execution complete: false ({reason});" in text
    metadata = result["structuredContent"]["metadata"]
    assert metadata["execution_complete"] is False
    assert metadata["execution_reason"] == reason


def test_mcp_tools_call_rejects_unknown_or_outside_workspace_tool(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    registry = read_search_tool_registry()
    context = ToolContext(workspace_root=tmp_path)

    unknown = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "run_command", "arguments": {"command": "echo no"}},
        },
        registry=registry,
        context=context,
    )
    outside_read = handle_mcp_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": str(outside)}},
        },
        registry=registry,
        context=context,
    )

    assert unknown is not None
    assert unknown["error"]["message"] == "Unknown tool: run_command"
    assert outside_read is not None
    assert outside_read["result"]["isError"] is True
    assert "outside the allowed workspace boundary" in outside_read["result"]["content"][0]["text"]


def test_mcp_tool_descriptor_uses_mcp_input_schema() -> None:
    descriptor = tool_definition_to_mcp_tool(ReadFileTool().definition)

    assert descriptor["name"] == "read_file"
    assert "inputSchema" in descriptor
    assert descriptor["inputSchema"]["properties"]["path"]["type"] == "string"
    assert descriptor["annotations"]["readOnlyHint"] is True
