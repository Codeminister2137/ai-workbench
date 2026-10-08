from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from web_app import CouncilRequestHandler

from tests.helpers import write_config


class FakeAgent:
    def __init__(self, member, ollama_base_url=None):
        self.member = member

    def stream_answer(self, conversation):
        yield self.member.name
        yield " answer"


@pytest.fixture
def council_server(tmp_path):
    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)

    class TestHandler(CouncilRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.db_path = db_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def test_config_endpoint_returns_public_member_metadata(council_server) -> None:
    with urlopen(f"{council_server}/api/config", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))

    assert payload["default_conversation"] == "test-conversation"
    assert [member["name"] for member in payload["members"]] == ["Analyst", "Skeptic"]
    assert "system_prompt" not in payload["members"][0]


def test_ask_endpoint_rejects_empty_prompt(council_server) -> None:
    request = Request(
        f"{council_server}/api/ask",
        data=json.dumps({"prompt": " "}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with pytest.raises(HTTPError) as raised:
        urlopen(request, timeout=5)

    assert raised.value.code == 400
    raised.value.close()


def test_ask_endpoint_streams_server_sent_events(council_server, monkeypatch) -> None:
    request = Request(
        f"{council_server}/api/ask",
        data=json.dumps({"prompt": "Question?"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    monkeypatch.setattr("council.LocalAgent", FakeAgent)
    with urlopen(request, timeout=5) as response:
        content_type = response.headers["Content-Type"]
        body = response.read().decode("utf-8")

    assert "text/event-stream" in content_type
    assert '"type": "council_started"' in body
    assert '"type": "member_delta"' in body
    assert '"type": "council_finished"' in body


@pytest.mark.parametrize(
    "headers,body,status",
    [
        ({"Origin": "https://untrusted.invalid"}, b'{"prompt":"hello"}', 403),
        ({"Host": "untrusted.invalid"}, b'{"prompt":"hello"}', 403),
        ({"Content-Type": "text/plain"}, b'{"prompt":"hello"}', 415),
        ({}, b"{broken", 400),
        ({}, b"[]", 400),
        ({}, b'{"prompt":null}', 400),
        ({}, b'{"prompt":123}', 400),
        ({"Content-Length": "999999999"}, b"x", 413),
        ({"Content-Length": "-1"}, b"x", 413),
        ({"Content-Length": "invalid"}, b"x", 400),
        ({"Transfer-Encoding": "chunked"}, b"x", 400),
    ],
)
def test_rejected_request_never_loads_council(council_server, monkeypatch, headers, body, status):
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected request reached configuration/model/storage")

    monkeypatch.setattr("web_app.load_config", forbidden)
    request = Request(
        council_server + "/api/ask",
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=2)
    assert error.value.code == status
    error.value.close()


def test_incomplete_body_has_total_deadline(council_server, monkeypatch):
    import socket
    import time
    from urllib.parse import urlsplit

    monkeypatch.setattr("web_app.REQUEST_TIMEOUT_SECONDS", 0.15)
    monkeypatch.setattr("web_app.load_config", lambda *args: pytest.fail("Request had effects"))
    address = urlsplit(council_server)
    with socket.create_connection((address.hostname, address.port), timeout=2) as client:
        started = time.monotonic()
        client.sendall(
            (
                f"POST /api/ask HTTP/1.1\r\nHost: {address.netloc}\r\n"
                "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"
            ).encode()
        )
        response = client.recv(4096)
        assert b"408" in response
        assert time.monotonic() - started < 1
