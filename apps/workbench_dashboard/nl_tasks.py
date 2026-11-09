"""Natural-language task proposals: free text into a scheduled-task draft.

Deterministic parsing only (no model inference): duration extraction,
keyword model routing, and slug ids. Every proposal still flows through
inbox approval before anything is planned or executed.
"""

from __future__ import annotations

import re
import secrets

MAX_TEXT_CHARS = 2000
DEFAULT_SECONDS = 600.0
MIN_SECONDS = 60.0
MAX_SECONDS = 7200.0

DEFAULT_MODEL = "gpt-oss:20b"
CODER_MODEL = "qwen2.5-coder:14b"
THINKER_MODEL = "qwen3:14b"

CODER_WORDS = ("code", "coding", "review", "refactor", "test", "debug", "implement", "fix")
THINKER_WORDS = ("plan", "planning", "analy", "compare", "design", "decide", "investigat")

_DURATION_RE = re.compile(r"(\d+)\s*(h(?:ours?)?|m(?:in(?:utes?)?)?|s(?:ec(?:onds?)?)?)\b", re.I)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _route_model(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in CODER_WORDS):
        return CODER_MODEL
    if any(word in lowered for word in THINKER_WORDS):
        return THINKER_MODEL
    return DEFAULT_MODEL


def _parse_seconds(text: str) -> float:
    match = _DURATION_RE.search(text)
    if match is None:
        return DEFAULT_SECONDS
    value = int(match.group(1))
    unit = match.group(2).lower()
    seconds = float(
        value * 3600 if unit.startswith("h") else value * 60 if unit.startswith("m") else value
    )
    return min(max(seconds, MIN_SECONDS), MAX_SECONDS)


def _slug(text: str) -> str:
    words = _WORD_RE.findall(text.lower())[:8]
    slug = "-".join(words)[:48].strip("-")
    return slug or f"task-{secrets.token_hex(4)}"


def propose_task(text: str) -> dict:
    """Build one scheduled-task proposal from free text.

    Raises ``ValueError`` for empty or overlong input. Returns a dict
    with ``task_id``, ``prompt``, ``model``, and ``required_seconds``.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Task text is required")
    cleaned = " ".join(text.split())
    if len(cleaned) > MAX_TEXT_CHARS:
        raise ValueError(f"Task text exceeds {MAX_TEXT_CHARS} characters")
    return {
        "task_id": _slug(cleaned),
        "prompt": cleaned,
        "model": _route_model(cleaned),
        "required_seconds": _parse_seconds(cleaned),
    }
