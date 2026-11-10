"""Owner restriction toggles: persisted on/off switches enforced by runs.

Each toggle maps to real executor behavior (not a label): auto-routing,
shell tools, workspace sandbox, and subagent delegation. Unknown names are
refused; defaults keep the previous behavior.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TOGGLE_DEFAULTS: dict[str, bool] = {
    "auto_routing": False,
    "shell_tools": True,
    "sandbox": False,
    "delegation": False,
}

TOGGLE_DESCRIPTIONS: dict[str, str] = {
    "auto_routing": "Resolve the model per run via the orchestrator (free and allowance tiers plus owner exemptions); off uses the configured provider/model.",
    "shell_tools": "Allow shell and Python execution tools; off hides and denies them.",
    "sandbox": "Pin shell commands to the workspace root and refuse outside-workspace files.",
    "delegation": "Allow subagent fan-out by default; per-run policy still wins.",
}

_FILENAME = "restrictions.json"


def load_toggles(data_dir: Path) -> dict[str, bool]:
    """Load toggles; missing/corrupt files yield defaults (never raise)."""
    toggles = dict(TOGGLE_DEFAULTS)
    path = Path(data_dir) / _FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return toggles
    if isinstance(raw, dict):
        for name, default in TOGGLE_DEFAULTS.items():
            value = raw.get(name, default)
            toggles[name] = bool(value) if isinstance(value, bool) else default
    return toggles


def save_toggle(data_dir: Path, name: str, enabled: bool) -> dict[str, bool]:
    """Persist one toggle; unknown names raise ValueError."""
    if name not in TOGGLE_DEFAULTS:
        raise ValueError(f"Unknown restriction toggle: {name!r}")
    if not isinstance(enabled, bool):
        raise ValueError("Toggle value must be boolean")
    toggles = load_toggles(data_dir)
    toggles[name] = enabled
    path = Path(data_dir) / _FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(toggles, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)
    return toggles


def describe_toggles(toggles: Mapping[str, bool]) -> list[dict[str, Any]]:
    """UI-ready toggle list with descriptions."""
    return [
        {
            "name": name,
            "enabled": bool(toggles.get(name, default)),
            "description": TOGGLE_DESCRIPTIONS[name],
        }
        for name, default in TOGGLE_DEFAULTS.items()
    ]
