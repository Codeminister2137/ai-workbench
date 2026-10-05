"""Machine-local configuration and a fixed read-only IDE boundary."""

import json

import pytest
from ai_agent import ide_bridge
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.ide_bridge import CONFIG_PATH, IDE_TOOL_NAMES, IdeConfiguration, IdeTool
from ai_agent.tool_profiles import shared_tool_registry
from ai_agent.tools import ToolContext
from ai_provider.shared_client_tools import codex_inspection_overrides, copilot_inspection_options


def settings(workspace):
    return {
        "type": "streamable-http",
        "url": "http://127.0.0.1:12345/stream",
        "headers": {ide_bridge.PROJECT_HEADER: str(workspace)},
    }


class TestConfigurationImport:
    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com:1234/stream",
            "https://127.0.0.1:1234/stream",
            "http://user:secret@127.0.0.1:1234/stream",
            "http://127.0.0.1:1234/stream?token=secret",
            "http://127.0.0.1:1234/stream#secret",
            "http://localhost/stream",
        ],
    )
    def test_import_refuses_nonlocal_or_credential_bearing_urls(self, tmp_path, url):
        data = settings(tmp_path)
        data["url"] = url
        with pytest.raises(ValueError, match="loopback"):
            IdeConfiguration.parse(data, tmp_path)

    def test_import_is_machine_local_no_overwrite_and_maps_common_read_tools(self, tmp_path):
        copied = tmp_path / "copy.json"
        copied.write_text(json.dumps(settings(tmp_path)))
        assert (
            ide_bridge.main(["--workspace-root", str(tmp_path), "--import-config", str(copied)])
            == 0
        )
        assert json.loads((tmp_path / CONFIG_PATH).read_text()) == settings(tmp_path)
        assert (
            ide_bridge.main(["--workspace-root", str(tmp_path), "--import-config", str(copied)])
            == 1
        )
        for profile in ("inspection", "coding"):
            registry = shared_tool_registry(profile, tmp_path)
            for name in IDE_TOOL_NAMES:
                tool = registry.get(name)
                assert tool is not None and tool.definition.category == ToolCategory.READ
        for command in (
            codex_inspection_overrides(tmp_path),
            copilot_inspection_options(tmp_path),
        ):
            assert all(name in " ".join(command) for name in IDE_TOOL_NAMES)

    def test_import_refuses_other_project_credentials_and_header_injection(self, tmp_path):
        data = settings(tmp_path)
        data["headers"] = {ide_bridge.PROJECT_HEADER: str(tmp_path.parent)}
        with pytest.raises(ValueError, match="different workspace"):
            IdeConfiguration.parse(data, tmp_path)
        data["headers"] = {
            ide_bridge.PROJECT_HEADER: str(tmp_path),
            "Authorization": "Bearer secret",
        }
        with pytest.raises(ValueError, match="non-secret"):
            IdeConfiguration.parse(data, tmp_path)
        data["headers"] = {ide_bridge.PROJECT_HEADER: str(tmp_path) + "\r\nsecret"}
        with pytest.raises(ValueError, match="Invalid"):
            IdeConfiguration.parse(data, tmp_path)


class TestReadOnlyWrappers:
    def test_wrappers_forward_exact_read_operations_and_contain_paths(self, tmp_path, monkeypatch):
        file = tmp_path / "source.py"
        file.write_text("value = 1\n")
        seen = []

        async def request(configuration, operation, arguments):
            seen.append((operation, arguments))
            return {"output": "fixture", "is_error": False, "metadata": {"line": 1}}

        monkeypatch.setattr(ide_bridge, "_request", request)
        configuration = IdeConfiguration.parse(settings(tmp_path), tmp_path)
        for operation in IDE_TOOL_NAMES:
            tool = IdeTool(operation, configuration, tmp_path)
            args = {"path": "source.py", "line": 1, "column": 1}
            result = tool.run(ToolCall(operation, args), ToolContext(tmp_path))
            assert not result.is_error
            assert seen[-1][1]["filePath"] == "source.py"
            assert tool.run(
                ToolCall(operation, {**args, "path": "../outside.py"}), ToolContext(tmp_path)
            ).is_error
            assert tool.run(ToolCall(operation, args), ToolContext(tmp_path.parent)).is_error
        tool = IdeTool("symbol_info", configuration, tmp_path)
        assert tool.run(
            ToolCall("symbol_info", {"path": "source.py", "line": 0, "column": 1}),
            ToolContext(tmp_path),
        ).is_error

    def test_missing_configuration_keeps_existing_tool_surface(self, tmp_path):
        assert not set(IDE_TOOL_NAMES) & {
            definition.name
            for definition in shared_tool_registry("inspection", tmp_path).list_definitions()
        }
