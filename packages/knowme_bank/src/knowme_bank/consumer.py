"""Consumer helpers: turn bank entries into trainer context."""

from __future__ import annotations

from knowme_bank import KnowMeStore


def plan_context(store: KnowMeStore, category: str, *, limit: int = 10) -> str:
    """Format recent entries as a prompt-context block for a plan.

    Consumers (trainer, diet, career) call this instead of touching SQL.
    Empty banks yield an explicit empty block, never invented facts.
    """
    entries = store.find(category=category, limit=limit)
    if not entries:
        return f"# {category} bank: empty (interview the owner first)"
    lines = [f"# {category} bank ({len(entries)} entries)"]
    for entry in reversed(entries):
        lines.append(f"- [{entry.source}] {entry.text}")
    return "\n".join(lines)
