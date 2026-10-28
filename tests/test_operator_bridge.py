"""Workbench-side bridge to the Remote AI Operator external-action API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from ai_agent.contracts import ToolCall, ToolCategory
from ai_agent.operator_bridge import OperatorApprovalBridge, OperatorBridgeError


class _FakeResponse:
    def __init__(self, status_code: int, json_body: object):
        self.status_code = status_code
        self._json = json_body

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _RecordingClient:
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url: str, *, headers=None, json=None):
        self.calls.append(("POST", url, json))
        return self.responses.pop(0)

    def get(self, url: str, *, headers=None):
        self.calls.append(("GET", url, None))
        return self.responses.pop(0)


def _tool_call(name: str = "write_file", path: str = "src/x.py") -> ToolCall:
    return ToolCall(call_id="c1", name=name, arguments={"path": path, "content": "hello"})


def test_bridge_submits_and_approves(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "a" * 32, "status": "submitted", "nonce": "n1"}),
            _FakeResponse(200, {"status": "submitted"}),
            _FakeResponse(200, {"status": "approved"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: client,
    )

    assert bridge(_tool_call(), ToolCategory.WRITE) is True
    assert client.calls[0][0] == "POST"
    assert client.calls[0][1] == "http://operator.local/api/external-actions"
    payload = cast(dict[str, Any], client.calls[0][2])
    assert payload["description"].startswith("[write] write_file")
    assert len(payload["candidate_digest"]) == 64
    assert client.calls[-1][0] == "GET"


def test_bridge_rejects(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "b" * 32, "status": "submitted", "nonce": "n2"}),
            _FakeResponse(200, {"status": "rejected"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: client,
    )

    assert bridge(_tool_call(), ToolCategory.WRITE) is False


def test_bridge_truncates_long_arguments(tmp_path: Path) -> None:
    client = _RecordingClient(
        [
            _FakeResponse(200, {"id": "c" * 32, "status": "submitted", "nonce": "n3"}),
            _FakeResponse(200, {"status": "approved"}),
        ]
    )
    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: client,
    )

    long_content = "x" * 1000
    call = ToolCall(
        call_id="c2", name="write_file", arguments={"path": "src/x.py", "content": long_content}
    )
    bridge(call, ToolCategory.WRITE)
    payload = cast(dict[str, Any], client.calls[0][2])
    assert "\\u2026" in payload["description"]
    assert len(long_content) > 400


def test_bridge_raises_on_http_error(tmp_path: Path) -> None:
    import httpx

    class FailingClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise httpx.ConnectError("connection refused")

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "token",
        tmp_path,
        client_factory=lambda **kwargs: FailingClient(),
    )

    with pytest.raises(OperatorBridgeError):
        bridge(_tool_call(), ToolCategory.WRITE)


@pytest.mark.parametrize("resolution,approved", [("approved", True), ("rejected", False)])
def test_bridge_keeps_real_http_client_open_until_resolution(
    tmp_path: Path, resolution: str, approved: bool
) -> None:
    clients: list[httpx.Client] = []
    methods: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert not clients[0].is_closed
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"id": "a" * 32, "status": "submitted"})
        return httpx.Response(200, json={"status": resolution})

    def factory(**kwargs: Any) -> httpx.Client:
        client = httpx.Client(transport=httpx.MockTransport(handle), **kwargs)
        clients.append(client)
        return client

    bridge = OperatorApprovalBridge(
        "http://operator.local", "token", tmp_path, client_factory=factory
    )
    assert bridge(_tool_call(), ToolCategory.WRITE) is approved
    assert methods == ["POST", "GET"]
    assert clients[0].is_closed
