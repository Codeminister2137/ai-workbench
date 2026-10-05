"""SDK failures are explicit, redacted, and do not escape the CLI boundary."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from ai_agent import ide_bridge


class TestSdkFailures:
    def test_official_sdk_cancels_live_stream_that_never_answers(self, tmp_path, monkeypatch):
        pytest.importorskip("mcp")
        pytest.importorskip("httpx2")
        stop = threading.Event()
        streamed = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                try:
                    while not stop.wait(0.01):
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        streamed.set()
                except OSError:
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        monkeypatch.setattr(ide_bridge, "IDE_TIMEOUT_SECONDS", 0.5)
        configuration = ide_bridge.IdeConfiguration(
            f"http://127.0.0.1:{server.server_port}/stream", {}
        )
        try:
            with pytest.raises(RuntimeError, match="exceeded its time limit"):
                asyncio.run(ide_bridge._request(configuration, None, {}))
            assert streamed.is_set()
        finally:
            stop.set()
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            assert not worker.is_alive()

    @pytest.mark.parametrize("blocked_stage", ["handshake", "list_tools", "call_tool", "cleanup"])
    def test_request_deadline_cancels_stalled_sdk_and_closes_http(self, monkeypatch, blocked_stage):
        closed = []

        async def block(stage):
            if stage == blocked_stage:
                await asyncio.Event().wait()

        class HttpConnection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                closed.append("http")

        class Session:
            async def __aenter__(self):
                await block("handshake")
                return self

            async def __aexit__(self, *args):
                closed.append("session")
                await block("cleanup")

            async def list_tools(self):
                await block("list_tools")
                return SimpleNamespace(tools=[SimpleNamespace(name="get_python_environment")])

            async def call_tool(self, *args):
                await block("call_tool")
                return SimpleNamespace(content=[], is_error=False, structured_content=None)

        modules = {
            "httpx2": SimpleNamespace(AsyncClient=lambda **kw: HttpConnection()),
            "mcp.client.streamable_http": SimpleNamespace(
                streamable_http_client=lambda *a, **kw: object()
            ),
            "mcp": SimpleNamespace(Client=lambda transport: Session()),
        }
        monkeypatch.setattr(ide_bridge.importlib, "import_module", modules.__getitem__)
        monkeypatch.setattr(ide_bridge, "IDE_TIMEOUT_SECONDS", 0.02)
        with pytest.raises(RuntimeError, match="exceeded its time limit"):
            asyncio.run(
                ide_bridge._request(
                    ide_bridge.IdeConfiguration("unused", {}), "python_environment", {}
                )
            )
        assert "http" in closed
        assert ("session" in closed) == (blocked_stage != "handshake")

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
