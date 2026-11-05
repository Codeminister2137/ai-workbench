"""Provider-neutral STT flow plus the Meta ASR wire engine."""

from __future__ import annotations

import io
import wave

import pytest
from ai_provider import stt
from ai_provider.adapters.meta_asr import MetaAsrEngine
from ai_provider.stt import (
    SttFailure,
    TranscribeResult,
    decode_audio,
    parse_transcribe_form,
    transcribe_audio,
)


def _wav_bytes(*, seconds: float = 1.0, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


class _FakeEngine:
    id = "fake:asr"

    def __init__(self, text: str = "hello") -> None:
        self.text = text
        self.calls: list[dict] = []

    def transcribe(self, wav_bytes: bytes, *, language_bias, timeout_s: int):
        self.calls.append(
            {"bytes": len(wav_bytes), "bias": list(language_bias), "timeout": timeout_s}
        )
        return TranscribeResult(text=self.text)


class _FakeMetering:
    def __init__(self) -> None:
        self.reserved: list[dict] = []
        self.committed: list[dict] = []

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str:
        receipt = f"rcpt-{len(self.reserved)}"
        self.reserved.append({"operation": operation, "estimated": estimated_cents})
        return receipt

    def commit(self, receipt_id: str, actual_cents: int) -> None:
        self.committed.append({"receipt": receipt_id, "actual": actual_cents})


def _multipart(audio: bytes, language: str) -> tuple[str, bytes]:
    boundary = "----testboundary"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="audio"; filename="clip.webm"\r\n'
            "Content-Type: audio/webm\r\n\r\n"
        ).encode("latin-1")
        + audio
        + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="language"\r\n\r\n'
            f"{language}\r\n--{boundary}--\r\n"
        ).encode("latin-1")
    )
    return f"multipart/form-data; boundary={boundary}", body


class TestTranscribeForm:
    def test_round_trip(self):
        content_type, body = _multipart(b"bytes", "pl")
        audio, audio_type, language = parse_transcribe_form(content_type, body)
        assert (audio, audio_type, language) == (b"bytes", "audio/webm", "pl")

    def test_missing_audio_is_422(self):
        with pytest.raises(SttFailure) as excinfo:
            parse_transcribe_form("text/plain", b"nope")
        assert excinfo.value.http_status == 422


class TestDecodeAudio:
    def test_wav_fast_path(self):
        pcm, duration = decode_audio(_wav_bytes(seconds=2.0), "audio/wav")
        assert duration == pytest.approx(2.0)
        assert len(pcm) == 2 * 16000 * 2

    def test_oversize_is_413(self):
        with pytest.raises(SttFailure) as excinfo:
            decode_audio(b"x" * (stt.MAX_AUDIO_BYTES + 1), "audio/webm")
        assert excinfo.value.http_status == 413

    def test_unsupported_type_is_422(self):
        with pytest.raises(SttFailure) as excinfo:
            decode_audio(b"x", "audio/ogg")
        assert excinfo.value.http_status == 422

    def test_missing_ffmpeg_is_502(self):
        def no_ffmpeg(audio_bytes, timeout=30):
            raise FileNotFoundError("ffmpeg is not installed")

        with pytest.raises(SttFailure) as excinfo:
            decode_audio(b"not-wav", "audio/webm", run_ffmpeg=no_ffmpeg)
        assert excinfo.value.http_status == 502

    def test_corrupt_wav_is_422(self):
        with pytest.raises(SttFailure) as excinfo:
            decode_audio(b"garbage", "audio/wav")
        assert excinfo.value.http_status == 422


class TestTranscribeAudio:
    def test_flow_returns_text_and_receipt(self):
        engine = _FakeEngine("czesc")
        metering = _FakeMetering()
        result = transcribe_audio(
            engine=engine,
            metering=metering,
            audio_bytes=_wav_bytes(seconds=1.0),
            content_type="audio/wav",
            language="pl",
        )
        assert result["text"] == "czesc"
        assert result["language"] == "pl"
        assert result["duration_seconds"] == pytest.approx(1.0)
        assert engine.calls[0]["bias"] == ["Polish", "English"]
        assert metering.reserved[0]["operation"] == "audio"
        assert metering.committed[0]["actual"] >= 1

    def test_unsupported_language_is_422(self):
        with pytest.raises(SttFailure) as excinfo:
            transcribe_audio(
                engine=_FakeEngine(),
                metering=_FakeMetering(),
                audio_bytes=_wav_bytes(),
                content_type="audio/wav",
                language="de",
            )
        assert excinfo.value.http_status == 422

    def test_busy_pool_is_429(self):
        for _ in range(stt.MAX_CONCURRENT_TRANSCRIPTIONS):
            assert stt._SEMAPHORE.acquire(blocking=False)
        try:
            with pytest.raises(SttFailure) as excinfo:
                transcribe_audio(
                    engine=_FakeEngine(),
                    metering=_FakeMetering(),
                    audio_bytes=_wav_bytes(),
                    content_type="audio/wav",
                    language="en",
                )
            assert excinfo.value.http_status == 429
        finally:
            for _ in range(stt.MAX_CONCURRENT_TRANSCRIPTIONS):
                stt._SEMAPHORE.release()


class TestMetaAsrEngine:
    def test_success_parses_transcript(self):
        httpx_mod = pytest.importorskip("httpx")

        def handler(request):
            assert request.headers["Authorization"] == "Bearer key-1"
            return httpx_mod.Response(200, json={"transcript": "hi", "turns": []})

        engine = MetaAsrEngine("key-1", transport=httpx_mod.MockTransport(handler))
        result = engine.transcribe(b"wav", language_bias=["English"], timeout_s=5)
        assert result.text == "hi"

    def test_auth_refused_maps_409_without_key_leak(self):
        httpx_mod = pytest.importorskip("httpx")

        def handler(request):
            return httpx_mod.Response(401, json={"message": "bad key-1"})

        engine = MetaAsrEngine("key-1", transport=httpx_mod.MockTransport(handler))
        with pytest.raises(SttFailure) as excinfo:
            engine.transcribe(b"wav", language_bias=["English"], timeout_s=5)
        assert excinfo.value.http_status == 409
        assert "key-1" not in str(excinfo.value)

    def test_rate_limit_maps_429_with_retry_after(self):
        httpx_mod = pytest.importorskip("httpx")

        def handler(request):
            return httpx_mod.Response(429, headers={"retry-after": "7"})

        engine = MetaAsrEngine("key-1", transport=httpx_mod.MockTransport(handler))
        with pytest.raises(SttFailure) as excinfo:
            engine.transcribe(b"wav", language_bias=["English"], timeout_s=5)
        assert excinfo.value.http_status == 429
        assert excinfo.value.retry_after == "7"


class TestMetaAsrWireProbe:
    """Synthetic-clip probe: real WAV bytes through the real engine wire format."""

    def test_wire_shape_with_synthetic_clip(self):
        httpx_mod = pytest.importorskip("httpx")
        clip = _wav_bytes(seconds=0.5)
        seen: dict = {}

        def handler(request):
            seen["method"] = request.method
            seen["params"] = dict(request.url.params)
            seen["authorization"] = request.headers["Authorization"]
            body = request.read()
            seen["body"] = body
            return httpx_mod.Response(200, json={"transcript": "hello world", "turns": []})

        engine = MetaAsrEngine("key-1", transport=httpx_mod.MockTransport(handler))
        result = engine.transcribe(clip, language_bias=["English"], timeout_s=5)
        assert result.text == "hello world"
        assert seen["method"] == "POST"
        assert len(seen["params"].get("sessionId", "")) == 32
        assert seen["authorization"] == "Bearer key-1"
        body = seen["body"]
        assert b'"audioEncoding": "WAV"' in body
        assert b'"languageBias": ["English"]' in body
        assert b'"mode": ' in body and b'"model": ' in body
        assert clip in body
        assert b"key-1" not in body

    def test_full_flow_with_real_engine(self):
        httpx_mod = pytest.importorskip("httpx")

        def handler(request):
            return httpx_mod.Response(200, json={"transcript": "czesc", "turns": []})

        engine = MetaAsrEngine("key-1", transport=httpx_mod.MockTransport(handler))
        metering = _FakeMetering()
        result = transcribe_audio(
            engine=engine,
            metering=metering,
            audio_bytes=_wav_bytes(seconds=1.0),
            content_type="audio/wav",
            language="pl",
        )
        assert result["text"] == "czesc"
        assert result["language"] == "pl"
        assert result["duration_seconds"] == pytest.approx(1.0)
        assert metering.reserved[0]["operation"] == "audio"
        assert metering.committed[0]["actual"] >= 1
