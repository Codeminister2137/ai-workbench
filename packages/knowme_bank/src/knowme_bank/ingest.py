"""Reviewed atomic ingest: propose facts from text, bank them with provenance.

Answer A (owner, 2026-11-17): facts are persisted individually at ingest with
an explicit source filename; the original input is retained on every banked
fact. ``propose_facts`` is deliberately conservative — ambiguous prose stays
whole — because arbitrary prose cannot safely be split on punctuation alone.
Callers review proposals before banking; ``import_facts`` also accepts an
explicit fact list that overrides the proposals. No model calls, no network.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowme_bank import KnowMeEntry, KnowMeStore

_LABEL_RE = re.compile(r"^[^:()\s]{1,32}:\s+")
_LEADING_COLON_RE = re.compile(r"^:\s+")


def _top_level_split(line: str, separators: frozenset[str]) -> list[str]:
    """Split on separators outside () and [] spans (quotes are not spans)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in line:
        if char in "([":
            depth += 1
            current.append(char)
        elif char in ")]":
            depth = max(0, depth - 1)
            current.append(char)
        elif depth == 0 and char in separators:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _strip_label(line: str) -> str:
    """Drop a leading `Label:` or bare `: ` prefix (category labels)."""
    stripped = _LEADING_COLON_RE.sub("", line, count=1)
    if stripped != line:
        return stripped
    return _LABEL_RE.sub("", line, count=1)


def propose_facts(text: str) -> list[str]:
    """Propose atomic facts for review; never raises on odd input.

    Rules: blank lines separate; a leading label/colon is dropped;
    top-level semicolons always split; top-level commas split only when
    every segment is a single token (multi-word segments stay whole, so
    dated career facts and ambiguous prose survive intact).
    """
    facts: list[str] = []
    for raw_line in text.splitlines():
        line = _strip_label(raw_line.strip())
        if not line:
            continue
        for chunk in _top_level_split(line, frozenset({";"})):
            chunk = chunk.strip()
            if not chunk:
                continue
            segments = [segment.strip() for segment in _top_level_split(chunk, frozenset({","}))]
            segments = [segment for segment in segments if segment]
            if len(segments) > 1 and all(" " not in segment for segment in segments):
                facts.extend(segments)
            else:
                facts.append(chunk)
    return facts


def import_facts(
    store: KnowMeStore,
    category: str,
    text: str,
    source: str = "import",
    *,
    source_file: str | None = None,
    facts: list[str] | None = None,
) -> list[KnowMeEntry]:
    """Bank one row per fact with origin + filename; repeats bank again.

    ``facts`` overrides the splitter when the caller already reviewed (or
    hand-split) the proposals. Repeat imports are explicit, never silently
    deduplicated: the same input banks the same rows again.
    """
    proposed = list(facts) if facts is not None else propose_facts(text)
    return [
        store.add(
            category,
            fact,
            source,
            source_file=source_file,
            origin_text=text,
        )
        for fact in proposed
    ]
