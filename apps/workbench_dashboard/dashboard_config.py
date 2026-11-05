"""Dashboard-local configuration: provider choice, titles, budgets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent
DEFAULT_CONFIG_PATH = ROOT / "dashboard.json"
DEFAULT_DATA_DIR = ROOT / "data"


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    """Local-first dashboard settings; no secrets live here."""

    provider: str = "ollama"
    model: str = "gpt-oss:20b"
    base_url: str | None = None
    title: str = "Workbench Dashboard"
    history_budget_chars: int = 20000
    chat_fanout_policy: str = "restricted"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> DashboardConfig:
    """Load dashboard config; a missing file yields local defaults."""
    if not path.exists():
        return DashboardConfig()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Dashboard config is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Dashboard config must be a JSON object")
    known = {
        "provider": str,
        "model": str,
        "base_url": (str, type(None)),
        "title": str,
        "history_budget_chars": int,
        "chat_fanout_policy": str,
    }
    values: dict[str, object] = {}
    for key, types in known.items():
        if key not in payload or payload[key] is None and key == "base_url":
            continue
        value = payload[key]
        if key == "base_url" and value is None:
            continue
        if not isinstance(value, types):
            raise ValueError(f"Dashboard config key {key!r} has the wrong type")
        values[key] = value
    budget = values.get("history_budget_chars")
    if isinstance(budget, int) and budget < 0:
        raise ValueError("history_budget_chars must be zero or greater")
    return DashboardConfig(**values)  # type: ignore[arg-type]
