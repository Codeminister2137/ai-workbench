"""Run-scoped HTTP inference boundary; provider admission stays in the host callback.

This is a reverse inference endpoint, never a CONNECT/URL forwarding proxy.
The caller owns the server lifetime and must supply the existing admitted model
executor. No provider credentials, URLs or host commands come from the worker.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024


class RunGrant:
    """One run's short-lived, revocable bearer capability and fixed model."""

    def __init__(self, run_id: str, token: str, model: str, *, ttl: float = 300) -> None:
        if not run_id or len(token) < 32 or not model or not 0 < ttl <= 3600:
            raise ValueError("A run, strong token, model and bounded TTL are required")
        self.run_id = run_id
        self._token = token
        self.model = model
        self._deadline = time.monotonic() + ttl
        self._revoked = threading.Event()

    def revoke(self) -> None:
        """Deny subsequent requests; caller also cancels any admitted inference."""
        self._revoked.set()

    def accepts(self, authorization: str) -> bool:
        return (
            not self._revoked.is_set()
            and time.monotonic() < self._deadline
            and hmac.compare_digest(authorization.encode(), f"Bearer {self._token}".encode())
        )


def make_server(
    address: tuple[str, int],
    grant: RunGrant,
    complete: Callable[[str, list[dict[str, str]]], dict],
) -> HTTPServer:
    """Bind an explicit interface; serial requests bound callback concurrency.

    Use 127.0.0.1 in host tests. A container may bind its container interface.
    Callback must enforce provider/privacy/usage admission, timeout and cancel.
    """
    if address[0] in ("", "0.0.0.0", "::"):
        raise ValueError("Bind a specific interface, never a host wildcard")

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format: str, *args: object) -> None:
            pass  # Tokens and prompts must not enter access logs.

        def reply(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode()
            if len(body) > MAX_RESPONSE_BYTES:
                status, body = 502, b'{"error":"response too large"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def do_POST(self) -> None:
            if not grant.accepts(self.headers.get("Authorization", "")):
                self.reply(401, {"error": "invalid run grant"})
                return
            if self.path != f"/runs/{grant.run_id}/inference":
                self.reply(404, {"error": "unknown endpoint"})
                return
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                self.reply(400, {"error": "one content length required"})
                return
            try:
                size = int(lengths[0])
                if not 0 < size <= MAX_REQUEST_BYTES:
                    self.reply(413, {"error": "request size refused"})
                    return
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError("incomplete body")
                payload = json.loads(body)
                if not isinstance(payload, dict) or set(payload) != {"messages"}:
                    raise ValueError("only messages accepted")
                messages = payload["messages"]
                if not isinstance(messages, list) or not 1 <= len(messages) <= 128:
                    raise ValueError("messages required")
                for message in messages:
                    if (
                        not isinstance(message, dict)
                        or set(message) != {"role", "content"}
                        or message["role"] not in ("system", "user", "assistant")
                        or not isinstance(message["content"], str)
                    ):
                        raise ValueError("invalid message")
            except (ValueError, TypeError, TimeoutError, OSError):
                self.reply(400, {"error": "invalid inference request"})
                return
            if not grant.accepts(self.headers.get("Authorization", "")):
                self.reply(401, {"error": "expired or revoked"})
                return
            try:
                result = complete(grant.model, messages)
                self.reply(200, result)
            except Exception:  # noqa: BLE001 - never leak provider exceptions/secrets
                self.reply(502, {"error": "inference failed"})

    return HTTPServer(address, Handler)
