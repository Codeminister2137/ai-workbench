"""Foreground, authenticated MCP Streamable HTTP with JSON responses.

Access is granted per invocation. HTTP sessions never grant access by themselves;
revoking a bearer also invalidates all its sessions. No SSE replay is offered.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ai_agent.mcp_server import PROTOCOL_VERSION, handle_mcp_message
from ai_agent.tools.base import ToolContext, ToolRegistry

BODY_LIMIT = 512_000


@dataclass
class AccessScope:
    registry: ToolRegistry
    deadline: float | None
    sessions: dict[str, bool] = field(default_factory=dict)


class ForegroundMcpHost:
    """One local listener owned and closed by the foreground CLI."""

    def __init__(self, workspace: Path):
        self.context = ToolContext(workspace.resolve())
        self.scopes: dict[str, AccessScope] = {}
        self.lock = threading.RLock()
        self.operations = threading.Lock()
        self.closed = False
        self.request_statuses: deque[int] = deque(maxlen=32)
        host = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, format, *args):
                pass  # Never log headers, credentials, tool arguments or output.

            def reply(self, status: int, body: Any = None, session: str | None = None):
                host.request_statuses.append(status)
                raw = json.dumps(body).encode() if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                if session:
                    self.send_header("Mcp-Session-Id", session)
                self.end_headers()
                self.wfile.write(raw)

            def dispatch(self):
                with host.lock:
                    if self.path != "/mcp":
                        self.reply(404)
                        return
                    if self.headers.get("Host") != host.url.removeprefix("http://").split("/")[0]:
                        self.reply(403)
                        return
                    origin = self.headers.get("Origin")
                    if origin is not None and origin != host.url.removesuffix("/mcp"):
                        self.reply(403)
                        return
                    authorization = self.headers.get("Authorization", "")
                    token = authorization.removeprefix("Bearer ")
                    scope = host.scopes.get(token) if authorization.startswith("Bearer ") else None
                    if (
                        host.closed
                        or scope is None
                        or (scope.deadline is not None and time.perf_counter() >= scope.deadline)
                    ):
                        self.reply(401)
                        return
                    if self.command == "GET":
                        self.reply(405)
                        return
                    session = self.headers.get("Mcp-Session-Id")
                    if self.command == "DELETE":
                        if session not in scope.sessions:
                            self.reply(404)
                        else:
                            del scope.sessions[session]
                            self.reply(204)
                        return
                    if self.headers.get("Transfer-Encoding") or (
                        self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                    ):
                        self.reply(400)
                        return
                    accept = self.headers.get("Accept", "")
                    if "application/json" not in accept or "text/event-stream" not in accept:
                        self.reply(406)
                        return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= BODY_LIMIT:
                            self.reply(413)
                            return
                        message = json.loads(self.rfile.read(length))
                    except (ValueError, OSError):
                        self.reply(400)
                        return
                    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                        self.reply(400, {"error": "Invalid JSON-RPC envelope"})
                        return
                    method = message.get("method")
                    if method == "server/discover" and session is None and "id" in message:
                        # New clients probe this before falling back to classic initialization.
                        self.reply(
                            200,
                            handle_mcp_message(
                                message, registry=scope.registry, context=host.context
                            ),
                        )
                        return
                    if method == "initialize":
                        if session is not None or "id" not in message:
                            self.reply(400, {"error": "Invalid initialization session"})
                            return
                        session = secrets.token_urlsafe(32)
                        scope.sessions[session] = False
                    else:
                        if session not in scope.sessions:
                            self.reply(404 if session else 400, {"error": "Unknown MCP session"})
                            return
                        if self.headers.get("MCP-Protocol-Version") != PROTOCOL_VERSION:
                            self.reply(400, {"error": "Unsupported MCP protocol version"})
                            return
                        if method == "notifications/initialized":
                            scope.sessions[session] = True
                        elif not scope.sessions[session]:
                            self.reply(400, {"error": "MCP session not initialized"})
                            return
                with host.operations:
                    # Revocation must stay possible while a human considers an approval.
                    if not host.active(token):
                        self.reply(401)
                        return
                    response = handle_mcp_message(
                        message, registry=scope.registry, context=host.context
                    )
                    self.reply(200 if response is not None else 202, response, session)

            do_POST = dispatch
            do_GET = dispatch
            do_DELETE = dispatch

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = False
        self.url = f"http://127.0.0.1:{self.server.server_port}/mcp"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def grant(self, registry: ToolRegistry, *, deadline: float | None = None) -> str:
        with self.lock:
            if self.closed:
                raise ValueError("Foreground MCP host has closed")
            token = secrets.token_urlsafe(32)
            self.scopes[token] = AccessScope(registry, deadline)
            return token

    def active(self, token: str) -> bool:
        with self.lock:
            scope = self.scopes.get(token)
            return (
                not self.closed
                and scope is not None
                and (scope.deadline is None or time.perf_counter() < scope.deadline)
            )

    def revoke(self, token: str) -> None:
        with self.lock:
            self.scopes.pop(token, None)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            self.scopes.clear()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
