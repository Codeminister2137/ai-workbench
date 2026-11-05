"""Meta speech-to-text wire engine.

Batch ASR contract: multipart ``request`` JSON + ``audio`` WAV; JSON
``{transcript, turns[]}`` reply, turns empty in PUSH_TO_TALK; languageBias
takes language *names*. Raises the provider-neutral ``SttFailure`` so the
flow in ``ai_provider.stt`` stays provider-agnostic.

Wire shape follows the remote-operator STT module, whose contract was proven
with a live probe tone (HTTP 200 via muse-voice-transcribe-1.0). This port
still needs its own synthetic-clip probe before it may claim end-to-end
success.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from ai_provider.stt import SttFailure, TranscribeResult

STT_MODEL = "muse-voice-transcribe-1.0"
STT_ENDPOINT = "https://api.meta.ai/v1/asr/transcribe"
STT_MODE = "PUSH_TO_TALK"
DETAIL_CHAR_LIMIT = 700


def _redact(text: str, key: str) -> str:
    if key:
        return text.replace(key, "[redacted]")
    return text


def _provider_detail(raw: bytes, key: str) -> str:
    try:
        data = json.loads(raw or b"")
    except ValueError:
        data = None
    detail = "No structured provider detail"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            detail = error["message"]
        elif isinstance(data.get("message"), str):
            detail = data["message"]
    return str(_redact(detail, key))[:DETAIL_CHAR_LIMIT]


def _transcript_text(data: Any) -> str:
    """Extract utterance text from a Meta ASR JSON reply.

    PUSH_TO_TALK answers carry the top-level ``transcript`` (turns empty);
    turn modes carry ``turns[].transcript``. Accept either; empty string means
    nothing heard. Raises SttFailure (502) for a malformed reply.
    """
    if not isinstance(data, dict):
        raise SttFailure("protocol", "Malformed provider response", 502)
    transcript = data.get("transcript")
    if isinstance(transcript, str):
        return transcript
    turns = data.get("turns")
    if not isinstance(turns, list):
        raise SttFailure("protocol", "Malformed provider response", 502)
    parts = []
    for turn in turns:
        if isinstance(turn, str):
            parts.append(turn)
        elif isinstance(turn, dict) and isinstance(turn.get("transcript"), str):
            parts.append(turn["transcript"])
        else:
            raise SttFailure("protocol", "Malformed provider response", 502)
    return " ".join(part for part in (text.strip() for text in parts) if part)


class MetaAsrEngine:
    """Meta batch-ASR engine behind the neutral TranscribeEngine protocol."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = STT_ENDPOINT,
        model: str = STT_MODEL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("Meta ASR needs a session API key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._transport = transport

    @property
    def id(self) -> str:
        """Engine identity for receipts (never carries key material)."""
        return f"meta:{self._model}"

    def transcribe(
        self, wav_bytes: bytes, *, language_bias: list[str], timeout_s: int
    ) -> TranscribeResult:
        """Send one WAV clip to Meta ASR and return its transcript."""
        request_payload = {
            "model": self._model,
            "audioEncoding": "WAV",
            "mode": STT_MODE,
            "languageBias": list(language_bias),
        }
        # Random per-request correlation id; never a user, subject or task id.
        correlation = uuid.uuid4().hex
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=httpx.Timeout(timeout_s),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    self._base_url,
                    params={"sessionId": correlation},
                    headers={
                        "Authorization": "Bearer " + self._api_key,
                        "Accept": "application/json",
                    },
                    files={
                        "request": (None, json.dumps(request_payload), "application/json"),
                        "audio": ("clip.wav", wav_bytes, "audio/wav"),
                    },
                )
                raw = response.read()
        except httpx.TimeoutException as exc:
            raise SttFailure("timeout", type(exc).__name__, 502) from None
        except httpx.HTTPError as exc:
            raise SttFailure("transport", type(exc).__name__, 502) from None
        if response.status_code == 429:
            raise SttFailure(
                "rate_limit",
                "Transcription busy; retry or use browser dictation",
                429,
                retry_after=response.headers.get("retry-after"),
            )
        if response.status_code in (401, 403):
            raise SttFailure(
                "authentication",
                "Provider refused the session key; re-attach and retry",
                409,
            )
        if response.status_code in (400, 413):
            raise SttFailure("request", _provider_detail(raw, self._api_key), 422)
        if response.status_code != 200:
            if response.status_code >= 500:
                raise SttFailure("availability", "Transcription provider unavailable", 502)
            raise SttFailure("request", _provider_detail(raw, self._api_key), 422)
        try:
            data = json.loads(raw)
        except ValueError:
            raise SttFailure("protocol", "Malformed provider response", 502) from None
        return TranscribeResult(text=_transcript_text(data))


__all__ = ["STT_ENDPOINT", "STT_MODEL", "STT_MODE", "MetaAsrEngine"]
