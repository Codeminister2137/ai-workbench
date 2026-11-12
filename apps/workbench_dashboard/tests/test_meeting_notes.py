"""Meeting transcription + slice-2 allowance-routed AI analysis.

A WAV upload splits into <=60s clips, each transcribed through the
metered engine, and the assembled transcript is stored locally with a
retention sidecar. Analysis extracts action items through an injected
client only on explicit per-call external confirmation. All fixtures
synthetic.
"""

from __future__ import annotations

import io
import json
import threading
import wave
from datetime import UTC, datetime, timedelta
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_web_app import DashboardRequestHandler
from meeting_notes import (
    DEFAULT_RETENTION_DAYS,
    analyze_meeting,
    assemble_transcript,
    expired_meetings,
    format_timestamp,
    get_meeting,
    list_meetings,
    parse_meeting_form,
    purge_meeting,
    split_wav_clips,
    store_meeting,
)


def _wav_bytes(*, seconds: float = 1.0, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def test_split_chunks_long_meetings_on_frame_boundaries() -> None:
    clips = split_wav_clips(_wav_bytes(seconds=130.0))
    assert [offset for offset, _ in clips] == [0.0, 60.0, 120.0]
    for _, clip in clips:
        with wave.open(io.BytesIO(clip), "rb") as parsed:
            assert parsed.getframerate() == 16000
            assert parsed.getnchannels() == 1
    durations = []
    for _, clip in clips:
        with wave.open(io.BytesIO(clip), "rb") as parsed:
            durations.append(parsed.getnframes() / parsed.getframerate())
    assert durations == [60.0, 60.0, 10.0]


def test_split_rejects_garbage_and_empty() -> None:
    with pytest.raises(ValueError, match="readable WAV"):
        split_wav_clips(b"not a wav at all")
    with pytest.raises(ValueError, match="readable WAV|empty audio"):
        split_wav_clips(b"")


def test_timestamps_and_assembly() -> None:
    assert format_timestamp(0) == "[00:00]"
    assert format_timestamp(61) == "[01:01]"
    assert format_timestamp(3661) == "[1:01:01]"
    out = assemble_transcript(
        [
            {"start_s": 0.0, "text": "hello  "},
            {"start_s": 61.0, "text": "world"},
        ]
    )
    assert out == "[00:00] hello\n[01:01] world"


def test_parse_meeting_form_fields() -> None:
    audio = _wav_bytes()
    boundary = "----m"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="audio"; filename="m.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("latin-1")
        + audio
        + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"pl\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="consent"\r\n\r\n'
            f"yes\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="retention_days"\r\n\r\n'
            f"30\r\n--{boundary}--\r\n"
        ).encode("latin-1")
    )
    parsed = parse_meeting_form(f"multipart/form-data; boundary={boundary}", body)
    assert parsed[0] == audio
    assert parsed[1:] == ("pl", True, 30)


def test_parse_meeting_form_defaults_and_rejections() -> None:
    audio = _wav_bytes()

    def build(*fields: tuple) -> bytes:
        boundary = "----m"
        chunks = [
            b'Content-Disposition: form-data; name="audio"; filename="m.wav"\r\n'
            b"Content-Type: audio/wav\r\n\r\n" + audio
        ]
        for name, value in fields:
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}'.encode("latin-1")
            )
        sep = f"\r\n--{boundary}\r\n".encode("latin-1")
        return (
            f"--{boundary}\r\n".encode("latin-1")
            + sep.join(chunks)
            + f"\r\n--{boundary}--\r\n".encode("latin-1")
        )

    ct = "multipart/form-data; boundary=----m"
    assert parse_meeting_form(ct, build(("language", "en")))[1:] == (
        "en",
        False,
        DEFAULT_RETENTION_DAYS,
    )
    with pytest.raises(ValueError, match="language tag is required"):
        parse_meeting_form(ct, build(("consent", "yes")))
    with pytest.raises(ValueError, match="retention_days must be positive"):
        parse_meeting_form(ct, build(("language", "en"), ("retention_days", "0")))
    with pytest.raises(ValueError, match="multipart/form-data"):
        parse_meeting_form("text/plain", b"nope")


def test_store_requires_consent_and_computes_purge(tmp_path) -> None:
    now = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="consent"):
        store_meeting(
            tmp_path,
            transcript="x",
            segments=[],
            consent=False,
            retention_days=90,
            engine_id="e",
            source_name="s",
        )
    meta = store_meeting(
        tmp_path,
        transcript="[00:00] hi",
        segments=[{"start_s": 0.0, "text": "hi"}],
        consent=True,
        retention_days=30,
        engine_id="fake:asr",
        source_name="m.wav",
        recorded_at=now,
    )
    assert meta["id"].startswith("mtg-20261109T200000Z-")
    assert meta["purge_after_utc"] == (now + timedelta(days=30)).isoformat()
    assert meta["segments"] == [{"start_s": 0.0, "chars": 2}]
    stored = tmp_path / "meetings" / meta["id"]
    assert (stored / "transcript.md").read_text(encoding="utf-8") == "[00:00] hi"
    assert json.loads((stored / "meta.json").read_text(encoding="utf-8"))["id"] == meta["id"]


def test_expired_and_purge_roundtrip(tmp_path) -> None:
    base = datetime(2026, 11, 9, 20, 0, tzinfo=UTC)
    old = store_meeting(
        tmp_path,
        transcript="o",
        segments=[],
        consent=True,
        retention_days=1,
        engine_id="e",
        source_name="s",
        recorded_at=base - timedelta(days=5),
    )
    fresh = store_meeting(
        tmp_path,
        transcript="n",
        segments=[],
        consent=True,
        retention_days=90,
        engine_id="e",
        source_name="s",
        recorded_at=base,
    )
    assert expired_meetings(tmp_path, base) == [old["id"]]
    assert purge_meeting(tmp_path, "../escape") is False
    assert purge_meeting(tmp_path, "mtg-missing") is False
    assert purge_meeting(tmp_path, old["id"]) is True
    assert expired_meetings(tmp_path, base) == []
    assert (tmp_path / "meetings" / fresh["id"] / "meta.json").exists()


class _CountingEngine:
    id = "fake:asr"

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, wav_bytes: bytes, *, language_bias, timeout_s: int):
        from ai_provider.stt import TranscribeResult

        self.calls += 1
        return TranscribeResult(text=f"clip{self.calls}")


class _CountingMetering:
    def __init__(self) -> None:
        self.reserves = 0

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str:
        self.reserves += 1
        return f"rcpt-{self.reserves}"

    def commit(self, receipt_id: str, actual_cents: int) -> None:
        return None


@pytest.fixture
def meeting_server(tmp_path, monkeypatch):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(
        json.dumps({"provider": "ollama", "model": "fake", "title": "Test Board"}),
        encoding="utf-8",
    )

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = tmp_path / "data"
    TestHandler.repo_root = tmp_path
    engine = _CountingEngine()
    metering = _CountingMetering()
    TestHandler.stt_engine_factory = staticmethod(lambda: engine)  # pyright: ignore[reportAttributeAccessIssue]
    TestHandler.stt_metering = metering
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", tmp_path, engine, metering
    finally:
        server.shutdown()
        server.server_close()


def _meeting_multipart(audio: bytes, **fields: str) -> tuple[str, bytes]:
    boundary = "----m"
    chunks = [
        b'Content-Disposition: form-data; name="audio"; filename="m.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n" + audio
    ]
    for name, value in fields.items():
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}'.encode("latin-1")
        )
    sep = f"\r\n--{boundary}\r\n".encode("latin-1")
    body = (
        f"--{boundary}\r\n".encode("latin-1")
        + sep.join(chunks)
        + f"\r\n--{boundary}--\r\n".encode("latin-1")
    )
    return f"multipart/form-data; boundary={boundary}", body


def _post_raw(base: str, path: str, content_type: str, body: bytes) -> dict:
    request = Request(
        f"{base}{path}", data=body, headers={"Content-Type": content_type}, method="POST"
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def test_endpoint_transcribes_chunks_and_stores(meeting_server) -> None:
    base, tmp_path, engine, metering = meeting_server
    content_type, body = _meeting_multipart(
        _wav_bytes(seconds=65.0), language="pl", consent="yes", retention_days="30"
    )
    out = _post_raw(base, "/api/meetings/transcribe", content_type, body)
    assert out["ok"] is True
    assert out["clips"] == 2
    assert out["transcript"] == "[00:00] clip1\n[01:00] clip2"
    assert engine.calls == 2
    assert metering.reserves == 2
    stored = tmp_path / "data" / "meetings" / out["id"]
    assert (stored / "transcript.md").read_text(encoding="utf-8") == out["transcript"]
    assert "purge_after_utc" in out


def test_endpoint_refuses_without_consent(meeting_server) -> None:
    base, _, _, _ = meeting_server
    content_type, body = _meeting_multipart(_wav_bytes(), language="en")
    with pytest.raises(HTTPError) as exc:
        _post_raw(base, "/api/meetings/transcribe", content_type, body)
    assert exc.value.code == 409


def test_endpoint_rejects_non_wav(meeting_server) -> None:
    base, _, _, _ = meeting_server
    content_type, body = _meeting_multipart(b"nope", language="en", consent="yes")
    with pytest.raises(HTTPError) as exc:
        _post_raw(base, "/api/meetings/transcribe", content_type, body)
    assert exc.value.code == 422


def _stored_meeting(tmp_path, *, transcript="[00:00] hello", recorded="2026-11-10T10:00:00+00:00"):
    from datetime import datetime

    data_dir = tmp_path / "data"
    return store_meeting(
        data_dir,
        transcript=transcript,
        segments=[{"start_s": 0.0, "text": "hello"}],
        consent=True,
        retention_days=30,
        engine_id="fake",
        source_name="m.wav",
        recorded_at=datetime.fromisoformat(recorded),
    )


class _FakeAnalysisClient:
    def __init__(self, text="- [ ] do the thing") -> None:
        from types import SimpleNamespace

        self.text = text
        self.requests = []
        self._ns = SimpleNamespace

    def complete(self, request):
        self.requests.append(request)
        return self._ns(message=self._ns(content=self.text))


def test_list_and_get_meeting_roundtrip(tmp_path) -> None:
    data_dir = tmp_path / "data"
    first = _stored_meeting(tmp_path, recorded="2026-11-10T10:00:00+00:00")
    second = _stored_meeting(tmp_path, recorded="2026-11-11T10:00:00+00:00")
    items = list_meetings(data_dir)
    assert [item["id"] for item in items] == [second["id"], first["id"]]
    assert all(item["has_analysis"] is False for item in items)
    record = get_meeting(data_dir, first["id"])
    assert record is not None
    assert record["meta"]["id"] == first["id"]
    assert "hello" in record["transcript"]
    assert record["transcript_truncated"] is False
    assert record["analysis"] is None
    assert get_meeting(data_dir, "mtg-ghost") is None
    assert get_meeting(data_dir, "../escape") is None
    assert list_meetings(tmp_path / "missing") == []


def test_analyze_requires_confirmation_and_stores_result(tmp_path) -> None:
    data_dir = tmp_path / "data"
    meta = _stored_meeting(tmp_path)
    client = _FakeAnalysisClient()
    with pytest.raises(ValueError, match="explicit confirmation"):
        analyze_meeting(
            data_dir,
            meta["id"],
            client=client,
            model_id="m",
            route_id="r",
            confirm_external=False,
        )
    assert client.requests == []
    out = analyze_meeting(
        data_dir,
        meta["id"],
        client=client,
        model_id="m",
        route_id="r",
        confirm_external=True,
    )
    assert out["analysis"] == "- [ ] do the thing"
    assert out["truncated"] is False
    prompt_text = client.requests[0].messages[1].content
    assert "hello" in prompt_text  # transcript reaches the model
    stored_meta = json.loads(
        (data_dir / "meetings" / meta["id"] / "meta.json").read_text(encoding="utf-8")
    )
    assert stored_meta["external_confirmed"] is True
    assert (stored_meta["analysis_model"], stored_meta["analysis_route"]) == ("m", "r")
    reread = get_meeting(data_dir, meta["id"])
    assert reread is not None
    assert reread["analysis"] == "- [ ] do the thing"
    with pytest.raises(KeyError):
        analyze_meeting(
            data_dir,
            "mtg-ghost",
            client=client,
            model_id="m",
            route_id="r",
            confirm_external=True,
        )


def test_analyze_truncates_huge_transcripts_with_marker(tmp_path) -> None:
    data_dir = tmp_path / "data"
    meta = _stored_meeting(tmp_path, transcript="x" * 70_000)
    client = _FakeAnalysisClient()
    out = analyze_meeting(
        data_dir,
        meta["id"],
        client=client,
        model_id="m",
        route_id="r",
        confirm_external=True,
    )
    assert out["truncated"] is True
    sent = client.requests[0].messages[1].content
    assert len(sent) < 70_000 and "truncated to fit" in sent


def test_analyze_refuses_empty_model_content(tmp_path) -> None:
    data_dir = tmp_path / "data"
    meta = _stored_meeting(tmp_path)
    client = _FakeAnalysisClient(text="   ")
    with pytest.raises(ValueError, match="no content"):
        analyze_meeting(
            data_dir,
            meta["id"],
            client=client,
            model_id="m",
            route_id="r",
            confirm_external=True,
        )
    assert not (data_dir / "meetings" / meta["id"] / "analysis.md").exists()


def _get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def test_meeting_endpoints_list_get_and_analyze(meeting_server, monkeypatch) -> None:
    base, tmp_path, _, _ = meeting_server
    content_type, body = _meeting_multipart(
        _wav_bytes(seconds=1.0), language="en", consent="yes", retention_days="30"
    )
    created = _post_raw(base, "/api/meetings/transcribe", content_type, body)
    meeting_id = created["id"]
    listed = _get_json(base, "/api/meetings")
    assert [item["id"] for item in listed["items"]] == [meeting_id]
    detail = _get_json(base, f"/api/meetings/{meeting_id}")
    assert detail["meta"]["id"] == meeting_id and "clip1" in detail["transcript"]
    with pytest.raises(HTTPError) as exc:
        _get_json(base, "/api/meetings/mtg-ghost")
    assert exc.value.code == 404

    client = _FakeAnalysisClient()
    monkeypatch.setattr(
        DashboardRequestHandler,
        "analysis_client_factory",
        staticmethod(lambda: (client, "fake-model", "fake/route")),
        raising=False,
    )
    with pytest.raises(HTTPError) as exc:
        _post_json(base, f"/api/meetings/{meeting_id}/analyze", {"confirm_external": False})
    assert exc.value.code == 409
    out = _post_json(base, f"/api/meetings/{meeting_id}/analyze", {"confirm_external": True})
    assert out["ok"] is True and "do the thing" in out["analysis"]
    assert out["route"] == "fake/route"
    refetched = _get_json(base, f"/api/meetings/{meeting_id}")
    assert refetched["analysis"] is not None
    with pytest.raises(HTTPError) as exc:
        _post_json(base, "/api/meetings/mtg-ghost/analyze", {"confirm_external": True})
    assert exc.value.code == 404
