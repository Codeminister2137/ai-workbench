"""Common documentation retrieval preserves provenance and existing permissions."""

import json
from datetime import UTC, datetime

import pytest
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.mcp_server import handle_mcp_message, tool_definition_to_mcp_tool
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.shared_approvals import scoped_registry
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry
from ai_agent.tools import ToolContext, research
from ai_agent.tools.research_http import FetchedSource
from ai_provider.shared_client_tools import (
    SharedToolRun,
    codex_inspection_overrides,
    copilot_inspection_options,
    kiro_inspection_agent,
)


@pytest.fixture
def fetched(monkeypatch):
    seen = []
    receipt = {
        "requested_url": "https://docs.python.org/3/",
        "final_url": "https://docs.python.org/3/",
        "http_status": 200,
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "sha256": "a" * 64,
        "bytes_retained": 15,
        "truncated": False,
    }

    def fetch(url, **kwargs):
        seen.append(url)
        return FetchedSource(b"public document", "text/plain", "utf-8", receipt)

    monkeypatch.setattr(research, "fetch_public_url", fetch)
    return seen, receipt


class TestCommonDocumentation:
    def test_native_and_mcp_return_same_public_text_and_execution_receipt(self, tmp_path, fetched):
        registry = shared_tool_registry("coding", tmp_path)
        assert tuple(item.name for item in registry.list_definitions()) == CODING_PROFILE.tool_names
        context = ToolContext(tmp_path)
        arguments = {"url": "https://docs.python.org/3/"}
        native = registry.execute(ToolCall("fetch_url", arguments), context)
        response = handle_mcp_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "fetch_url", "arguments": arguments},
            },
            registry=registry,
            context=context,
        )
        assert response is not None
        assert not native.is_error and not response["result"]["isError"]
        assert response["result"]["structuredContent"]["output"] == native.output
        assert native.metadata == fetched[1]
        assert json.loads(native.output)["text"] == "public document"
        assert fetched[0] == [arguments["url"], arguments["url"]]
        assert not list(tmp_path.iterdir())

    @pytest.mark.parametrize("preset", ["read_only", "workspace_write", "interactive"])
    def test_no_unattended_network_authority_is_added(self, tmp_path, fetched, preset):
        registry = scoped_registry(
            shared_tool_registry("coding"),
            PermissionManager(PermissionPolicy.from_approval_preset(preset)),
            tmp_path,
            "task",
            "run",
        )
        result = registry.execute(
            ToolCall("fetch_url", {"url": "https://docs.python.org/3/"}), ToolContext(tmp_path)
        )
        assert result.is_error
        assert not result.metadata["shared_receipt"]["authorized"]
        assert fetched[0] == []

    def test_exact_custom_approval_and_hash_receipt(self, tmp_path, fetched):
        approvals = []

        def approve(call, category):
            approvals.append((call, category))
            return True

        registry = scoped_registry(
            shared_tool_registry("coding"),
            PermissionManager(PermissionPolicy.interactive(), approve),
            tmp_path,
            "task",
            "run",
        )
        call = ToolCall("fetch_url", {"url": "https://docs.python.org/3/"})
        result = registry.execute(call, ToolContext(tmp_path))
        assert not result.is_error
        assert approvals == [(call, ToolCategory.CUSTOM)]
        assert result.metadata["final_url"] == fetched[1]["final_url"]
        saved = result.metadata["shared_receipt"]
        assert saved["authorized"] and saved["category"] == "custom"
        assert "public document" not in json.dumps(saved)
        assert "docs.python.org" not in json.dumps(saved)

    def test_inspection_and_external_client_allowlists_preserve_selected_surface(self, tmp_path):
        assert shared_tool_registry("inspection").get("fetch_url") is None
        run = SharedToolRun("task", "run", "interactive")
        codex = codex_inspection_overrides(tmp_path, run)
        enabled = next(value for value in codex if ".enabled_tools=" in value)
        assert "fetch_url" in json.loads(enabled.split("=", 1)[1])
        copilot = copilot_inspection_options(tmp_path, run)
        assert "repo_shared(fetch_url)" in copilot
        assert "repo_shared-fetch_url" in copilot
        kiro = kiro_inspection_agent(tmp_path, "fixture", run)
        kiro_tools = kiro["tools"]
        assert isinstance(kiro_tools, list)
        assert "@repo_shared/fetch_url" in kiro_tools
        assert kiro["tools"] == kiro["allowedTools"]
        tool = shared_tool_registry("coding").get("fetch_url")
        assert tool is not None
        descriptor = tool_definition_to_mcp_tool(tool.definition)
        assert descriptor["annotations"]["openWorldHint"]
        assert descriptor["inputSchema"]["required"] == ["url"]
