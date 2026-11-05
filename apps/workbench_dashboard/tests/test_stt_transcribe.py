"""Transcribe endpoint and ingestion-language wiring over real HTTP."""

from __future__ import annotations

import io
import json
import threading
import wave
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ai_provider.stt import TranscribeResult
from ai_provider.translation import TranslationResult
from dashboard_web_app import DashboardRequestHandler


class _FakeEngine:
    id = "fake:asr"

    def transcribe(self, wav_bytes: bytes, *, language_bias, timeout_s: int):
        return TranscribeResult(text="hello dictated")


class _FakeMetering:
    def __init__(self) -> None:
        self.calls: list = []

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str:
        self.calls.append(("reserve", operation, estimated_cents))
        return "rcpt-1"

    def commit(self, receipt_id: str, actual_cents: int) -> None:
        self.calls.append(("commit", receipt_id, actual_cents))


class _FakeTranslator:
    id = "fake:t"

    def __init__(self) -> None:
        self.last_receipt: dict | None = None

    def supported_languages(self) -> list[str]:
        return ["en", "pl"]

    def needs_key(self) -> bool:
        return False

    def estimate_cents(self, text: str) -> int:
        return 1

    def translate(self, text: str, source_lang: str) -> TranslationResult:
        self.last_receipt = {"translator": "fake:t"}
        return TranslationResult(
            text=f"EN[{text}]", source_lang=source_lang, translator_id="fake:t"
        )


@pytest.fixture
def stt_server(tmp_path, monkeypatch):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = data_dir
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def fake_execute(self, request):
        from ai_agent.coding_chat import CodingTurnResult

        return CodingTurnResult(0, "Fake answer.", "completed", provider="ollama")

    monkeypatch.setattr("dashboard_chat.DashboardChat._execute", fake_execute)

    def configure(
        *,
        engine: Callable[[], _FakeEngine] | None = None,
        metering: _FakeMetering | None = None,
        translator: _FakeTranslator | None = None,
    ) -> None:
        TestHandler.stt_engine_factory = engine  # type: ignore[assignment]
        TestHandler.stt_metering = metering  # type: ignore[assignment]
        TestHandler.chat_translator = translator  # type: ignore[assignment]

    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path, configure
    finally:
        server.shutdown()
        server.server_close()


def _wav_bytes(*, seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        clip.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def _multipart(audio: bytes, language: str) -> tuple[str, bytes]:
    boundary = "----testboundary"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="audio"; filename="clip.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("latin-1")
        + audio
        + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{language}\r\n--{boundary}--\r\n"
        ).encode("latin-1")
    )
    return f"multipart/form-data; boundary={boundary}", body


def post_raw(base: str, path: str, content_type: str, body: bytes) -> dict:
    request = Request(
        f"{base}{path}", data=body, headers={"Content-Type": content_type}, method="POST"
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_status_raw(base: str, path: str, content_type: str, body: bytes) -> int:
    request = Request(
        f"{base}{path}", data=body, headers={"Content-Type": content_type}, method="POST"
    )
    try:
        with urlopen(request, timeout=10):
            return 200
    except HTTPError as exc:
        return exc.code


def test_transcribe_round_trip(stt_server) -> None:
    base, _tmp_path, configure = stt_server
    metering = _FakeMetering()
    configure(engine=_FakeEngine, metering=metering)
    content_type, body = _multipart(_wav_bytes(), "en")
    payload = post_raw(base, "/api/stt/transcribe", content_type, body)
    assert payload["ok"] is True
    assert payload["text"] == "hello dictated"
    assert payload["language"] == "en"
    assert metering.calls[0][0] == "reserve"


def test_transcribe_unconfigured_is_409(stt_server) -> None:
    base, _tmp_path, _configure = stt_server
    content_type, body = _multipart(_wav_bytes(), "en")
    assert post_status_raw(base, "/api/stt/transcribe", content_type, body) == 409


def test_transcribe_bad_form_is_422(stt_server) -> None:
    base, _tmp_path, configure = stt_server
    configure(engine=_FakeEngine, metering=_FakeMetering())
    assert post_status_raw(base, "/api/stt/transcribe", "text/plain", b"nope") == 422


def test_chat_accepts_language_and_translates(stt_server) -> None:
    base, _tmp_path, configure = stt_server
    configure(translator=_FakeTranslator())
    created = post_json(base, "/api/chat/sessions", {"title": "Lang"})
    answer = post_json(
        base,
        f"/api/chat/sessions/{created['id']}/messages",
        {"text": "Czesc", "language": "pl"},
    )
    assert answer["ok"] is True
    messages = get_json(base, f"/api/chat/sessions/{created['id']}/messages")
    user_turns = [m for m in messages["messages"] if m["role"] == "user"]
    assert user_turns[0]["content"] == "EN[Czesc]"
    assert user_turns[0]["metadata"]["source_text"] == "Czesc"
    assert user_turns[0]["metadata"]["translated"] is True


def test_chat_non_english_without_translator_is_409(stt_server) -> None:
    base, _tmp_path, _configure = stt_server
    created = post_json(base, "/api/chat/sessions", {"title": "Lang"})
    request = Request(
        f"{base}/api/chat/sessions/{created['id']}/messages",
        data=json.dumps({"text": "Czesc", "language": "pl"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            raise AssertionError("expected 409")
    except HTTPError as exc:
        assert exc.code == 409
    messages = get_json(base, f"/api/chat/sessions/{created['id']}/messages")
    assert messages["messages"] == []
