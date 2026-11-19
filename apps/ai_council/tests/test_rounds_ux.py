from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from storage import ConversationStore
from web_app import CouncilRequestHandler

from tests.helpers import write_config


class FakeAgent:
    def __init__(self, member, ollama_base_url=None):
        self.member = member

    def answer(self, conversation):
        return f"{self.member.name} answered"

    def stream_answer(self, conversation):
        yield f"{self.member.name} answered"

    def react(self, conversation, peer_answers):
        return f"{self.member.name} reacts"

    def stream_react(self, conversation, peer_answers):
        yield f"{self.member.name} reacts"

    def synthesize(self, conversation, answers):
        return "positions: A and B; agreements: none; disagreements: none"

    def stream_synthesize(self, conversation, answers):
        yield "synthesis streaming"


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    monkeypatch.setattr("council.LocalAgent", FakeAgent)

    captured: dict = {}

    class Handler(CouncilRequestHandler):
        pass

    Handler.config_path = config_path
    Handler.db_path = db_path

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()
        captured["done"] = True


def _post_ask(base: str, payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        f"{base}/api/ask",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def test_ask_rounds_two_streams_reactions(live_server) -> None:
    status, body = _post_ask(live_server, {"prompt": "Q?", "rounds": 2})
    assert status == 200
    assert '"type": "member_finished"' in body
    assert '"type": "reaction_finished"' in body
    assert "synthesis_finished" not in body


def test_ask_rounds_three_streams_synthesis(live_server) -> None:
    status, body = _post_ask(live_server, {"prompt": "Q?", "rounds": 3})
    assert status == 200
    assert '"type": "synthesis_finished"' in body
    assert '"partial": false' in body


def test_ask_rounds_rejects_invalid_values(live_server) -> None:
    for bad in (0, 4, "two", True, None):
        status, _ = _post_ask(live_server, {"prompt": "Q?", "rounds": bad})
        assert status == 400, bad
    status, _ = _post_ask(live_server, {"prompt": "Q?"})
    assert status == 200


def test_cli_rounds_flag_reaches_council(tmp_path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "council.json"
    db_path = tmp_path / "council.sqlite3"
    write_config(config_path)
    monkeypatch.setattr("council.LocalAgent", FakeAgent)
    import main as main_module

    monkeypatch.setattr(
        "sys.argv",
        [
            "council",
            "Question?",
            "--config",
            str(config_path),
            "--db",
            str(db_path),
            "--rounds",
            "2",
        ],
    )
    main_module.main()
    out = capsys.readouterr().out
    assert "[R2]" in out
    assert "Analyst reacts" in out
    store = ConversationStore(db_path)
    messages = store.list_messages(store.get_or_create_conversation("test-conversation"))
    store.close()
    assert [m["round"] for m in messages] == [1, 1, 1, 2, 2]
