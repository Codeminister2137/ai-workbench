"""SDK failures are explicit, redacted, and do not escape the CLI boundary."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from ai_agent import ide_bridge


class TestSdkFailures:
    def test_missing_optional_sdk_explains_installation(self, monkeypatch):
        def missing(name):
            raise ImportError(name)

        monkeypatch.setattr(ide_bridge.importlib, "import_module", missing)
        with pytest.raises(RuntimeError, match="ide optional extra"):
            asyncio.run(ide_bridge._request(ide_bridge.IdeConfiguration("unused", {}), None, {}))

    def test_transport_task_group_failure_is_redacted(self, tmp_path, monkeypatch, capsys):
        class Connection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

        class FailedSession(Connection):
            async def __aenter__(self):
                raise ExceptionGroup("private-header", [OSError("private-endpoint")])

        modules = {
            "httpx2": SimpleNamespace(AsyncClient=lambda **kw: Connection()),
            "mcp.client.streamable_http": SimpleNamespace(
                streamable_http_client=lambda *a, **kw: object()
            ),
            "mcp": SimpleNamespace(Client=lambda transport: FailedSession()),
        }
        monkeypatch.setattr(ide_bridge.importlib, "import_module", modules.__getitem__)
        target = tmp_path / ide_bridge.CONFIG_PATH
        target.parent.mkdir()
        target.write_text(
            json.dumps(
                {
                    "type": "streamable-http",
                    "url": "http://127.0.0.1:12345/stream",
                    "headers": {ide_bridge.PROJECT_HEADER: str(tmp_path)},
                }
            )
        )
        assert ide_bridge.main(["--workspace-root", str(tmp_path), "--check"]) == 1
        output = capsys.readouterr().out
        assert "Cannot communicate" in output
        assert "private-header" not in output and "private-endpoint" not in output
