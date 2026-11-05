"""Agent window/activity status for the owner dashboard.

Adapted from remote-operator ``window_status.py``: the agent maintains
``window-status.json`` at the checkout root, rewriting it at work
boundaries (which task is active, its phase, when it started, the last
heartbeat, a short note, and the active worker list). The loader below
only reads; it never raises. A missing file means no agent activity
(``{"running": False}``) and malformed content yields safe defaults.

The status file is gitignored local state, not a record: durable
history belongs in run receipts and session handoffs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATUS_FILENAME = "window-status.json"

FIELDS = (
    "slice",
    "phase",
    "started_utc",
    "last_heartbeat_utc",
    "next_heartbeat_utc",
    "sleep_state",
    "note",
)


def _clean_agents(value: object) -> list[dict[str, str]]:
    """Keep only well-formed agent entries (name/task/status strings)."""
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        task = entry.get("task", "")
        state = entry.get("status", "")
        if not isinstance(name, str) or not name:
            continue
        cleaned.append(
            {
                "name": name,
                "task": task if isinstance(task, str) else "",
                "status": state if isinstance(state, str) else "",
            }
        )
    return cleaned


def load_window_status(root: Path | str) -> dict[str, Any]:
    """Return the agent window status stored under ``root`` (never raises)."""
    defaults: dict[str, Any] = {"running": False, **dict.fromkeys(FIELDS, ""), "agents": []}
    try:
        raw = (Path(root) / STATUS_FILENAME).read_text(encoding="utf-8")
    except OSError:
        return {"running": False}
    try:
        data = json.loads(raw)
    except ValueError:
        return defaults
    if not isinstance(data, dict):
        return defaults
    status: dict[str, Any] = {"running": True}
    for field in FIELDS:
        value = data.get(field, "")
        status[field] = value if isinstance(value, str) else ""
    status["agents"] = _clean_agents(data.get("agents", []))
    return status


def write_window_status(root: Path | str, **fields: object) -> dict[str, Any]:
    """Atomically write the agent window status under ``root``.

    Only known fields and well-formed agent entries are kept; unknown
    keys are dropped so writers cannot smuggle shapes past the reader.
    Returns the stored payload.
    """
    payload: dict[str, Any] = {"running": True}
    for field in FIELDS:
        value = fields.get(field, "")
        payload[field] = value if isinstance(value, str) else ""
    payload["agents"] = _clean_agents(fields.get("agents", []))
    path = Path(root) / STATUS_FILENAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return payload
