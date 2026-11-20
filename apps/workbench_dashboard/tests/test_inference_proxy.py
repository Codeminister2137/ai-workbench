"""Exercise actual loopback HTTP, grant lifecycle and inference admission seam."""

from __future__ import annotations

import http.client
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from inference_proxy import RunGrant, make_server  # noqa: E402


@pytest.fixture
def proxy():
    calls = []
    grant = RunGrant("run-one", "x" * 40, "fixed-model")

    def complete(model, messages):
        calls.append((model, messages))
        return {"text": "ok"}

    server = make_server(("127.0.0.1", 0), grant, complete)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(payload, *, path="/runs/run-one/inference", token="x" * 40, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        conn.request(
            "POST",
            path,
            json.dumps(payload),
            {"Authorization": f"Bearer {token}", **(headers or {})},
        )
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    yield grant, calls, request
    grant.revoke()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


MESSAGE = {"messages": [{"role": "user", "content": "synthetic"}]}


def test_valid_request_uses_fixed_model(proxy):
    _, calls, request = proxy
    assert request(MESSAGE) == (200, {"text": "ok"})
    assert calls == [("fixed-model", MESSAGE["messages"])]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"messages": []},
        {"messages": "bad"},
        {**MESSAGE, "url": "http://host/api"},
        {**MESSAGE, "model": "other"},
        {"messages": [{"role": "tool", "content": "bad"}]},
        {"messages": [{"role": "user", "content": 42}]},
        {"messages": [{"role": "user", "content": "ok", "command": "bad"}]},
    ],
)
def test_invalid_requests_never_reach_callback(proxy, payload):
    _, calls, request = proxy
    assert request(payload)[0] == 400
    assert calls == []


def test_run_scope_auth_revocation_and_size(proxy):
    grant, calls, request = proxy
    assert request(MESSAGE, token="wrong")[0] == 401
    assert request(MESSAGE, token="é" * 32)[0] == 401
    assert request(MESSAGE, path="/runs/other/inference")[0] == 404
    assert request(MESSAGE, path="/api/inbox")[0] == 404
    assert request({"messages": [{"role": "user", "content": "x" * 70000}]})[0] == 413
    assert request(MESSAGE, headers={"Transfer-Encoding": "chunked"})[0] == 400
    grant.revoke()
    assert request(MESSAGE)[0] == 401
    assert calls == []


def test_expired_grant(monkeypatch):
    import inference_proxy

    monkeypatch.setattr(inference_proxy.time, "monotonic", lambda: 100)
    grant = RunGrant("run", "x" * 40, "fixed", ttl=1)
    assert grant.accepts("Bearer " + "x" * 40)
    monkeypatch.setattr(inference_proxy.time, "monotonic", lambda: 101)
    assert not grant.accepts("Bearer " + "x" * 40)


def test_wildcard_bind_refused():
    with pytest.raises(ValueError, match="specific interface"):
        make_server(("0.0.0.0", 8080), RunGrant("run", "x" * 40, "fixed"), lambda *_: {})


@pytest.mark.parametrize("result", [{"text": "x" * 300000}, None])
def test_callback_failure_is_bounded_and_redacted(result):
    grant = RunGrant("run", "x" * 40, "fixed")

    def complete(*_args):
        if result is None:
            raise RuntimeError("private upstream credential")
        return result

    server = make_server(("127.0.0.1", 0), grant, complete)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        conn.request(
            "POST",
            "/runs/run/inference",
            json.dumps(MESSAGE),
            {"Authorization": "Bearer " + "x" * 40},
        )
        response = conn.getresponse()
        assert response.status == 502
        body = response.read()
        assert len(body) < 100
        assert b"credential" not in body
        conn.close()
    finally:
        thread.join(timeout=2)
        server.server_close()
