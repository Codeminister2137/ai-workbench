"""Workbench-side bridge to the Remote AI Operator external-action API."""

from __future__ import annotations

import hashlib
import json
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


def test_bridge_sends_argument_metadata_without_content(tmp_path: Path) -> None:
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
    assert '"characters": 1000' in payload["description"]
    assert long_content not in payload["description"]
    assert "src/x.py" not in payload["description"]
    assert str(tmp_path) not in payload["description"]


def test_bridge_omits_nested_values_and_argument_names(tmp_path: Path) -> None:
    payloads = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "metadata-test"})
        return httpx.Response(200, json={"status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-access-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    arguments = {
        "PRIVATE_ARGUMENT_NAME": {"nested": "PRIVATE_NESTED_CONTENT"},
        "argv": ["PRIVATE_COMMAND", "PRIVATE_TOKEN"],
        "enabled": True,
        "number": 987654321,
        "missing": None,
    }
    assert bridge(ToolCall("run_command", arguments), ToolCategory.SHELL)
    payload = payloads[0]
    serialized = json.dumps(payload)
    for private in (
        "PRIVATE_ARGUMENT_NAME",
        "PRIVATE_NESTED_CONTENT",
        "PRIVATE_COMMAND",
        "PRIVATE_TOKEN",
        "987654321",
        str(tmp_path),
    ):
        assert private not in serialized
    metadata = json.loads(payload["description"].split("arguments_metadata: ")[1])
    assert metadata == {
        "count": 5,
        "items": [
            {"type": "object", "members": 1},
            {"type": "array", "items": 2},
            {"type": "boolean"},
            {"type": "number"},
            {"type": "null"},
        ],
    }
    expected = json.dumps(
        {"tool": "run_command", "arguments": arguments}, ensure_ascii=True, sort_keys=True
    )
    assert payload["candidate_digest"] == hashlib.sha256(expected.encode()).hexdigest()


def test_metadata_does_not_replace_exact_action_binding(tmp_path: Path) -> None:
    payloads = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            payloads.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "binding-test"})
        return httpx.Response(200, json={"status": "approved"})

    bridge = OperatorApprovalBridge(
        "http://operator.local",
        "synthetic-access-token",
        tmp_path,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handle), **kwargs
        ),
    )
    for content in ("first", "other"):
        assert bridge(ToolCall("create_file", {"content": content}), ToolCategory.WRITE)
    assert payloads[0]["description"] == payloads[1]["description"]
    assert payloads[0]["candidate_digest"] != payloads[1]["candidate_digest"]


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
