"""Meeting transcription slice 1: chunked WAV upload to stored transcript.

The founder records externally with client consent, uploads the file,
and gets a timestamped transcript stored locally with a retention
sidecar. AI analysis (action items, summary) is slice 2 with a model.
WAV-only in slice 1: splitting needs PCM frame access.
"""

from __future__ import annotations

import io
import json
import secrets
import shutil
import wave
from datetime import UTC, datetime, timedelta
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path

MEETING_BODY_MAX_BYTES = 256 * 1024 * 1024
MEETING_MAX_SECONDS = 3 * 3600
CLIP_MAX_SECONDS = 60.0
DEFAULT_RETENTION_DAYS = 90
CONSENT_VALUES = frozenset({"1", "true", "yes"})


def split_wav_clips(
    wav_bytes: bytes, *, max_seconds: float = CLIP_MAX_SECONDS
) -> list[tuple[float, bytes]]:
    """Split WAV into <=max_seconds clips; returns (offset_s, clip_wav).

    Each clip is a valid standalone WAV with the source params.
    Raises ValueError for unreadable/empty audio or >3h meetings.
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as clip:
            params = clip.getparams()
            rate = clip.getframerate()
            frame_bytes = max(1, params.sampwidth) * max(1, params.nchannels)
            if rate <= 0:
                raise ValueError("invalid framerate")
            frames_per_clip = max(1, int(rate * max_seconds))
            chunks: list[tuple[float, bytes]] = []
            start_frame = 0
            while True:
                frames = clip.readframes(frames_per_clip)
                if not frames:
                    break
                buf = io.BytesIO()
                with wave.open(buf, "wb") as out:
                    out.setparams(params)
                    out.writeframes(frames)
                chunks.append((start_frame / rate, buf.getvalue()))
                start_frame += len(frames) // frame_bytes
            total_seconds = start_frame / rate
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"not a readable WAV file: {exc}") from None
    if not chunks:
        raise ValueError("empty audio: no frames")
    if total_seconds > MEETING_MAX_SECONDS:
        raise ValueError("meeting exceeds 3h; split it before upload")
    return chunks


def format_timestamp(seconds: float) -> str:
    """[MM:SS] (or [H:MM:SS] past one hour) for transcript lines."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"[{hours}:{minutes:02d}:{secs:02d}]"
    return f"[{minutes:02d}:{secs:02d}]"


def assemble_transcript(segments: list[dict]) -> str:
    """Join {start_s, text} segments into timestamped lines."""
    return "\n".join(
        f"{format_timestamp(seg['start_s'])} {str(seg.get('text', '')).strip()}" for seg in segments
    )


def parse_meeting_form(content_type: str | None, body: bytes) -> tuple[bytes, str, bool, int]:
    """Split a meeting upload into (audio, language, consent, retention_days).

    Raises ValueError (the endpoint maps it to 422) for a non-multipart
    body, missing audio/language, or an invalid retention value.
    """
    if not content_type or "multipart/form-data" not in content_type.split(";")[0]:
        raise ValueError("multipart/form-data with audio and language is required")
    try:
        raw = b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + bytes(body)
        message = BytesParser(policy=HTTP).parsebytes(raw)
    except (ValueError, TypeError):
        raise ValueError("upload could not be parsed") from None
    if not message.is_multipart():
        raise ValueError("multipart/form-data with audio and language is required")
    audio: bytes | None = None
    language: str | None = None
    consent = False
    retention = DEFAULT_RETENTION_DAYS
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        payload = part.get_payload(decode=True)
        if name == "audio" and audio is None:
            if not isinstance(payload, bytes) or not payload:
                raise ValueError("audio file is required")
            audio = payload
        elif name == "language" and language is None:
            language = _text_field(payload, "language tag")
        elif name == "consent":
            consent = _text_field(payload, "consent flag", default="").lower() in CONSENT_VALUES
        elif name == "retention_days":
            retention = _retention_days(payload)
    if not audio:
        raise ValueError("audio file is required")
    if not language:
        raise ValueError("language tag is required")
    return audio, language, consent, retention


def _text_field(payload: object, label: str, default: str | None = None) -> str:
    if not isinstance(payload, bytes):
        if default is not None:
            return default
        raise ValueError(f"{label} is required")
    try:
        text = payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ValueError(f"{label} is not decodable") from None
    if not text and default is None:
        raise ValueError(f"{label} is required")
    return text or (default or "")


def _retention_days(payload: object) -> int:
    text = _text_field(payload, "retention_days", default=str(DEFAULT_RETENTION_DAYS))
    try:
        days = int(text)
    except ValueError:
        raise ValueError("retention_days must be an integer") from None
    if days <= 0:
        raise ValueError("retention_days must be positive")
    return days


def store_meeting(
    data_dir: Path,
    *,
    transcript: str,
    segments: list[dict],
    consent: bool,
    retention_days: int,
    engine_id: str,
    source_name: str,
    recorded_at: datetime | None = None,
) -> dict:
    """Store a transcript + retention sidecar; returns the meta record.

    Consent is an attestation that the client agreed to the recording;
    without it nothing is stored. Transcripts stay local by design.
    """
    if not consent:
        raise ValueError("client consent attestation is required")
    if int(retention_days) <= 0:
        raise ValueError("retention_days must be positive")
    now = recorded_at or datetime.now(UTC)
    meeting_id = f"mtg-{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
    target = Path(data_dir) / "meetings" / meeting_id
    target.mkdir(parents=True, exist_ok=False)
    (target / "transcript.md").write_text(transcript, encoding="utf-8")
    meta = {
        "id": meeting_id,
        "consent": True,
        "recorded_at_utc": now.isoformat(),
        "purge_after_utc": (now + timedelta(days=int(retention_days))).isoformat(),
        "engine_id": engine_id,
        "source_name": source_name,
        "clips": len(segments),
        "segments": [
            {"start_s": seg["start_s"], "chars": len(str(seg.get("text", "")))} for seg in segments
        ],
    }
    (target / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def expired_meetings(data_dir: Path, now: datetime | None = None) -> list[str]:
    """Ids whose purge_after_utc passed; malformed records never match."""
    moment = now or datetime.now(UTC)
    expired: list[str] = []
    root = Path(data_dir) / "meetings"
    if not root.is_dir():
        return expired
    for meta_path in sorted(root.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            purge = datetime.fromisoformat(str(meta["purge_after_utc"]))
        except (ValueError, KeyError, OSError):
            continue
        if purge <= moment:
            expired.append(meta_path.parent.name)
    return expired


def purge_meeting(data_dir: Path, meeting_id: str) -> bool:
    """Delete one stored meeting; False when the id is invalid/missing."""
    if not meeting_id.replace("-", "").replace("_", "").isalnum():
        return False
    target = Path(data_dir) / "meetings" / meeting_id
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    return True
