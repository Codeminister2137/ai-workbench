"""Stdio compatibility adapter to a scoped foreground MCP HTTP host."""

import json
import os
import sys
from collections.abc import Iterable
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ai_agent.mcp_server import PROTOCOL_VERSION


def validate_loopback_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.port
    ):
        raise ValueError("MCP endpoint must be an explicit credential-free loopback HTTP URL")


class HttpMcpConnection:
    """No retries of calls: a lost response may represent an uncertain effect."""

    def __init__(self, url: str, token: str):
        validate_loopback_url(url)
        if not token:
            raise ValueError("Foreground MCP bearer is missing")
        self.url, self.token = url, token
        self.session: str | None = None

        class RefuseRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        self.opener = build_opener(ProxyHandler({}), RefuseRedirect())

    def send(self, message: dict[str, Any]) -> dict[str, Any] | None:
        headers = {
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
            headers["MCP-Protocol-Version"] = PROTOCOL_VERSION
        request = Request(self.url, json.dumps(message).encode(), headers, method="POST")
        with self.opener.open(request, timeout=300) as response:
            self.session = response.headers.get("Mcp-Session-Id", self.session)
            raw = response.read()
            return json.loads(raw) if raw else None

    def close(self) -> None:
        if self.session:
            request = Request(
                self.url,
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Mcp-Session-Id": self.session,
                    "MCP-Protocol-Version": PROTOCOL_VERSION,
                },
                method="DELETE",
            )
            try:
                with self.opener.open(request, timeout=5):
                    pass
            except (OSError, HTTPError):
                pass
            self.session = None


def run_http_proxy(
    url: str,
    token_env: str,
    *,
    input_stream: Iterable[str] = sys.stdin,
    output_stream: Any = sys.stdout,
) -> int:
    token = os.environ.pop(token_env, "")
    if not token or token.startswith("${"):
        print("Foreground MCP credential environment variable was not forwarded", file=sys.stderr)
        return 1
    connection = HttpMcpConnection(url, token)
    try:
        for line in input_stream:
            if not line.strip():
                continue
            message = None
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("Expected a JSON-RPC object")
                # Preserve the existing stdio handler's implicit JSON-RPC version.
                message.setdefault("jsonrpc", "2.0")
                response = connection.send(message)
            except (ValueError, OSError) as exc:
                if isinstance(exc, HTTPError):
                    method = message.get("method") if isinstance(message, dict) else None
                    known_method = (
                        method
                        if method
                        in {
                            "server/discover",
                            "initialize",
                            "notifications/initialized",
                            "tools/list",
                            "tools/call",
                            "ping",
                        }
                        else "other"
                    )
                    try:
                        reason = json.loads(exc.read()).get("error")
                    except (ValueError, OSError):
                        reason = None
                    detail = (
                        reason
                        if reason
                        in {
                            "Invalid JSON-RPC envelope",
                            "Invalid initialization session",
                            "Unknown MCP session",
                            "Unsupported MCP protocol version",
                            "MCP session not initialized",
                        }
                        else "request rejected"
                    )
                    print(
                        f"Foreground MCP HTTP request refused: {exc.code}; "
                        f"method={known_method}; {detail}",
                        file=sys.stderr,
                    )
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id") if isinstance(message, dict) else None,
                    "error": {"code": -32000, "message": "Foreground MCP connection failed"},
                }
                output_stream.write(json.dumps(response) + "\n")
                output_stream.flush()
                return 1
            if response is not None:
                output_stream.write(json.dumps(response) + "\n")
                output_stream.flush()
    finally:
        connection.close()
    return 0
