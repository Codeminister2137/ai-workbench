"""Provider-neutral speech-to-text flow for short dictation clips.

One-shot flow only: validate caps, convert the clip to 16 kHz mono WAV, and
forward it to an injected engine. Provider wire contracts live in
``adapters/`` (see ``adapters/meta_asr.py``); spend metering arrives through
an injected hook the orchestrator binds to its ledger. This module never
imports an adapter or the orchestrator.

Audio bytes and transcripts are never persisted, logged, or stored in
receipts: only coarse counters and redacted provider diagnostics leave here.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import threading
import wave
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import HTTP
from typing import Protocol

logger = logging.getLogger(__name__)

MAX_DURATION_S = 60
MAX_AUDIO_BYTES = 4 * 1024 * 1024
# Middleware body cap: one max-size clip plus multipart framing.
STT_BODY_MAX_BYTES = MAX_AUDIO_BYTES + 65536
TARGET_RATE = 16000
REQUEST_TIMEOUT_S = 60
MAX_CONCURRENT_TRANSCRIPTIONS = 4

ACCEPTED_AUDIO_TYPES = frozenset({"audio/webm", "audio/wav", "audio/mp4"})
# Day-one set; maps request tags to engine language-bias names.
LANGUAGE_BIAS = {"en": "English", "pl": "Polish"}

# Coarse cent-ceiling prototype pricing: a full 60 s clip at $0.18/hour costs
# $0.003, below one cent. Every clip reserves and settles whole cents with a
# one-cent floor until P5 prices sub-cent usage.
AUDIO_RESERVATION_CENTS = 1

_SEMAPHORE = threading.Semaphore(MAX_CONCURRENT_TRANSCRIPTIONS)


class SttFailure(Exception):
    """A bounded transcription diagnostic with its HTTP mapping."""

    def __init__(
        self,
        category: str,
        detail: str,
        http_status: int,
        retry_after: str | None = None,
    ) -> None:
        self.category = category
        self.detail = detail
        self.http_status = http_status
        self.retry_after = retry_after
        super().__init__(f"stt {category}: {detail}")


@dataclass(frozen=True, slots=True)
class TranscribeResult:
    """Engine transcript for one clip (source language, never persisted)."""

    text: str


class TranscribeEngine(Protocol):
    """Narrow engine interface; each provider adapter implements it."""

    @property
    def id(self) -> str: ...

    def transcribe(
        self, wav_bytes: bytes, *, language_bias: list[str], timeout_s: int
    ) -> TranscribeResult: ...


class MeteringHook(Protocol):
    """Narrow spend interface; the orchestrator binds it to its ledger."""

    def reserve(self, *, operation: str, estimated_cents: int, **kwargs: object) -> str: ...

    def commit(self, receipt_id: str, actual_cents: int) -> None: ...


def parse_transcribe_form(content_type: str | None, body: bytes) -> tuple[bytes, str, str]:
    """Split a multipart/transcribe upload into (audio, audio_type, language).

    Raises SttFailure (422) for a missing audio part, missing language, or a
    body that is not multipart at all.
    """
    if not content_type or "multipart/form-data" not in content_type.split(";")[0]:
        raise SttFailure("request", "multipart/form-data with audio and language is required", 422)
    try:
        raw = b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + bytes(body)
        message = BytesParser(policy=HTTP).parsebytes(raw)
    except (ValueError, TypeError):
        raise SttFailure("request", "Upload could not be parsed", 422) from None
    if not message.is_multipart():
        raise SttFailure("request", "multipart/form-data with audio and language is required", 422)
    audio: bytes | None = None
    audio_type: str | None = None
    language: str | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name == "audio" and audio is None:
            raw_audio = part.get_payload(decode=True)
            if not isinstance(raw_audio, bytes):
                raise SttFailure("request", "audio file is required", 422)
            audio = raw_audio
            audio_type = (part.get_content_type() or "").split(";")[0].strip().lower()
        elif name == "language" and language is None:
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                raise SttFailure("request", "language tag is required", 422)
            try:
                language = payload.decode("utf-8").strip()
            except UnicodeDecodeError:
                raise SttFailure("request", "language tag is not decodable", 422) from None
    if not audio:
        raise SttFailure("request", "audio file is required", 422)
    if language is None or not language:
        raise SttFailure("request", "language tag is required", 422)
    return audio, audio_type or "", language


def _decode_wav(audio_bytes: bytes) -> tuple[bytes, float] | None:
    """Return (pcm, duration) for ready-made WAV, else None when ffmpeg is needed.

    Only 16 kHz mono 16-bit PCM passes straight through; anything else still
    needs a converting decode. Reads every frame so truncated data fails here
    instead of billing a partial clip. Raises SttFailure (422) for corrupt WAV.
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as clip:
            channels = clip.getnchannels()
            width = clip.getsampwidth()
            rate = clip.getframerate()
            if (channels, width, rate) != (1, 2, TARGET_RATE):
                return None
            frames = clip.readframes(clip.getnframes())
    except (wave.Error, EOFError):
        raise SttFailure("request", "Audio could not be decoded", 422) from None
    if not frames:
        raise SttFailure("request", "Audio clip is empty", 422) from None
    return frames, len(frames) / 2 / TARGET_RATE


def _run_ffmpeg(audio_bytes: bytes, timeout: int = 30) -> subprocess.CompletedProcess[bytes]:
    """Decode/convert any clip to 16 kHz mono raw PCM, capped at 61 s."""
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise FileNotFoundError("ffmpeg is not installed")
    return subprocess.run(
        [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            "pipe:0",
            "-ar",
            str(TARGET_RATE),
            "-ac",
            "1",
            "-f",
            "s16le",
            "-t",
            str(MAX_DURATION_S + 1),
            "pipe:1",
        ],
        input=audio_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def decode_audio(
    audio_bytes: bytes,
    content_type: str | None,
    *,
    run_ffmpeg=None,
) -> tuple[bytes, float]:
    """Validate and convert an upload to (pcm_bytes, duration_seconds).

    Raises SttFailure: 413 over the byte cap, 422 for unsupported/corrupt/empty
    audio or audio over the duration cap, 502 when conversion itself is
    unavailable (no ffmpeg). Never logs audio content.
    """
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ACCEPTED_AUDIO_TYPES:
        raise SttFailure(
            "request",
            "Unsupported audio type; send webm, wav or mp4",
            422,
        )
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise SttFailure("too_large", "Audio exceeds 4 MB limit", 413)
    if mime == "audio/wav":
        ready = _decode_wav(audio_bytes)
        if ready is not None:
            pcm, duration = ready
            if duration > MAX_DURATION_S:
                raise SttFailure("request", "Audio exceeds 60 s limit", 422)
            return pcm, duration
    runner = run_ffmpeg or _run_ffmpeg
    try:
        completed = runner(audio_bytes)
    except FileNotFoundError:
        raise SttFailure(
            "unavailable", "Audio conversion is unavailable on this server", 502
        ) from None
    except subprocess.TimeoutExpired:
        raise SttFailure("unavailable", "Transcription provider unavailable", 502) from None
    pcm = completed.stdout or b""
    if completed.returncode != 0 or not pcm:
        raise SttFailure("request", "Audio could not be decoded", 422) from None
    duration = len(pcm) / 2 / TARGET_RATE
    if duration > MAX_DURATION_S:
        raise SttFailure("request", "Audio exceeds 60 s limit", 422)
    return pcm, duration


def wav_bytes(pcm: bytes) -> bytes:
    """Wrap 16 kHz mono s16le PCM in a RIFF/WAVE container for engines."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(TARGET_RATE)
        clip.writeframes(pcm)
    return buffer.getvalue()


def transcribe_audio(
    *,
    engine: TranscribeEngine,
    metering: MeteringHook,
    audio_bytes: bytes,
    content_type: str | None,
    language: str,
    run_ffmpeg=None,
) -> dict[str, object]:
    """Reserve metering, convert, forward to the engine, and parse the reply.

    Consumes one worst-case USD reservation (operation ``audio``) before
    anything is decoded or sent. Failed calls stay consumed, like chat
    reservations. Raises SttFailure with the endpoint-contract HTTP mapping.
    """
    bias = LANGUAGE_BIAS.get((language or "").strip().lower())
    if bias is None:
        raise SttFailure(
            "request",
            "Unsupported language; send one of: " + ", ".join(sorted(LANGUAGE_BIAS)),
            422,
        )
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ACCEPTED_AUDIO_TYPES:
        raise SttFailure("request", "Unsupported audio type; send webm, wav or mp4", 422)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise SttFailure("too_large", "Audio exceeds 4 MB limit", 413)
    if not _SEMAPHORE.acquire(blocking=False):
        raise SttFailure("busy", "Transcription busy; retry or use browser dictation", 429)
    try:
        receipt = metering.reserve(operation="audio", estimated_cents=AUDIO_RESERVATION_CENTS)
        pcm, duration = decode_audio(audio_bytes, content_type, run_ffmpeg=run_ffmpeg)
        biases = [bias] if bias == "English" else [bias, "English"]
        result = engine.transcribe(
            wav_bytes(pcm), language_bias=biases, timeout_s=REQUEST_TIMEOUT_S
        )
        billed_seconds = int(duration)
        metering.commit(receipt, AUDIO_RESERVATION_CENTS)
        logger.info("stt transcribed %.1fs audio in %d billed seconds", duration, billed_seconds)
        return {
            "text": result.text,
            "language": (language or "").strip().lower(),
            "duration_seconds": round(duration, 1),
            "billed_seconds": billed_seconds,
            "receipt": {
                "engine": engine.id,
                "operation": "audio",
                "reservation_cents_estimate": AUDIO_RESERVATION_CENTS,
                "billed_cents_actual": AUDIO_RESERVATION_CENTS,
                "spending_control": "local_estimate_not_provider_cap",
            },
        }
    finally:
        _SEMAPHORE.release()


__all__ = [
    "ACCEPTED_AUDIO_TYPES",
    "AUDIO_RESERVATION_CENTS",
    "LANGUAGE_BIAS",
    "MAX_AUDIO_BYTES",
    "MAX_CONCURRENT_TRANSCRIPTIONS",
    "MAX_DURATION_S",
    "REQUEST_TIMEOUT_S",
    "STT_BODY_MAX_BYTES",
    "TARGET_RATE",
    "MeteringHook",
    "SttFailure",
    "TranscribeEngine",
    "TranscribeResult",
    "decode_audio",
    "parse_transcribe_form",
    "transcribe_audio",
    "wav_bytes",
]
