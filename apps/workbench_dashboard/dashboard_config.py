"""Dashboard-local configuration: provider choice, titles, budgets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

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
    work_roots: tuple[str, ...] = ()
    supervision: str = "attended"
    trusted_hosts: tuple[str, ...] = ()
    drain_interval_seconds: int = 0
    max_iterations: int = 50
    loop_context_budget_chars: int = 100000
    require_grounded_reports: bool = True
    route_policy: str = "configured"
    catalog_path: str | None = None
    mai_backend: str = "in-process"
    seller: dict | None = None


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
        "work_roots": list,
        "supervision": str,
        "trusted_hosts": list,
        "drain_interval_seconds": int,
        "max_iterations": int,
        "loop_context_budget_chars": int,
        "require_grounded_reports": bool,
        "route_policy": str,
        "catalog_path": (str, type(None)),
        "mai_backend": str,
        "seller": (dict, type(None)),
    }
    values: dict[str, object] = {}
    for key, types in known.items():
        if key not in payload or payload[key] is None:
            continue
        value = payload[key]
        if not isinstance(value, types):
            raise ValueError(f"Dashboard config key {key!r} has the wrong type")
        values[key] = value
    budget = values.get("history_budget_chars")
    if isinstance(budget, int) and budget < 0:
        raise ValueError("history_budget_chars must be zero or greater")
    interval = values.get("drain_interval_seconds")
    if isinstance(interval, int) and interval < 0:
        raise ValueError("drain_interval_seconds must be zero or greater")
    roots = values.get("work_roots")
    if roots is not None:
        entries = cast("list[object]", roots)
        if any(not isinstance(entry, str) for entry in entries):
            raise ValueError("Dashboard config key 'work_roots' must hold strings")
        # Dumb carrier: existence/overlap checks happen per request, not here.
        values["work_roots"] = tuple(entries)
    hosts = values.get("trusted_hosts")
    if hosts is not None:
        entries = cast("list[object]", hosts)
        if any(
            not isinstance(entry, str) or not entry or any(char.isspace() for char in entry)
            for entry in entries
        ):
            raise ValueError("Dashboard config key 'trusted_hosts' must hold exact Host values")
        values["trusted_hosts"] = tuple(entries)
    supervision = values.get("supervision", "attended")
    if supervision not in ("attended", "unattended"):
        raise ValueError("Dashboard config key 'supervision' must be attended or unattended")
    backend = values.get("mai_backend", "in-process")
    if backend not in ("in-process", "subprocess"):
        raise ValueError("Dashboard config key 'mai_backend' must be in-process or subprocess")
    return DashboardConfig(**values)  # type: ignore[arg-type]


def save_supervision(path: Path, supervision: str) -> str:
    """Persist the supervision mode, preserving all other config keys.

    A missing config file is created; other keys round-trip untouched.
    Raises ``ValueError`` for an unknown mode or an unreadable file.
    """
    if supervision not in ("attended", "unattended"):
        raise ValueError("supervision must be attended or unattended")
    payload: dict[str, object] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"Dashboard config is not valid JSON: {path}") from exc
        if not isinstance(raw, dict):
            raise ValueError("Dashboard config must be a JSON object")
        payload = raw
    payload["supervision"] = supervision
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return supervision
