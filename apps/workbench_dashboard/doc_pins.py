"""Pinned key documents: owner-curated important list (JSON overlay).

Documents themselves are a read-only filesystem scan; pins live beside
them in the data dir so "currently important" survives rescans without
touching the library. Unknown ids are kept verbatim (a renamed file
unpins itself by missing, never by error).
"""

from __future__ import annotations

import json
from pathlib import Path

PIN_FILE = "doc_pins.json"


def load_pinned(data_dir: Path) -> set[str]:
    """Return pinned document ids, tolerating a missing file."""
    path = data_dir / PIN_FILE
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        return set()
    if not isinstance(raw, dict) or not isinstance(raw.get("pinned"), list):
        return set()
    return {str(item) for item in raw["pinned"]}


def save_pin(data_dir: Path, doc_id: str, pinned: bool) -> set[str]:
    """Pin or unpin one document id; returns the full pinned set."""
    if not doc_id or not isinstance(doc_id, str):
        raise ValueError("doc id must be a non-empty string")
    current = load_pinned(data_dir)
    if pinned:
        current.add(doc_id)
    else:
        current.discard(doc_id)
    path = data_dir / PIN_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"pinned": sorted(current)}, indent=2), encoding="utf-8")
    tmp.replace(path)
    return current
