from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tests.helpers import write_config
from web_app import CouncilRequestHandler


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
