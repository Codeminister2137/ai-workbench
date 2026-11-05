"""Project registry: named work roots backed by data/projects.json.

One JSON object mapping project id to record. The id is the stable
``root_id`` digest of the resolved root directory, so a registry id
plugs directly into ``ProjectRoots.select`` anywhere runs, staged
approvals, and the executor resolve project scope. One project per
root; the root must be an existing directory at creation time.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_agent.staged_edits import StagedEditError, root_id

PROJECTS_FILENAME = "projects.json"
MAX_NAME_CHARS = 200
MAX_DESCRIPTION_CHARS = 2000


def _projects_path(data_dir: Path) -> Path:
    return Path(data_dir) / PROJECTS_FILENAME


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_registry(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Return the id -> record mapping; a missing file reads as empty."""
    path = _projects_path(data_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise StagedEditError(f"Project registry is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise StagedEditError("Project registry must be a JSON object")
    registry: dict[str, dict[str, Any]] = {}
    for key, record in payload.items():
        if isinstance(key, str) and isinstance(record, dict):
            registry[key] = record
    return registry


def _save_registry(data_dir: Path, registry: dict[str, dict[str, Any]]) -> None:
    path = _projects_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_projects(data_dir: Path) -> list[dict[str, Any]]:
    """List registered projects, oldest first."""
    return sorted(
        load_registry(data_dir).values(), key=lambda item: str(item.get("created_at_utc", ""))
    )


def get_project(data_dir: Path, project_id: str) -> dict[str, Any] | None:
    """Return one project record, or None when absent."""
    return load_registry(data_dir).get(project_id)


def create_project(
    data_dir: Path, *, name: str, root: str, description: str = ""
) -> dict[str, Any]:
    """Register a project root; refuses duplicates, missing dirs, bad names."""
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_CHARS:
        raise StagedEditError("Project name requires 1-200 characters")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        raise StagedEditError("Project description allows up to 2000 characters")
    if not isinstance(root, str) or not root.strip():
        raise StagedEditError("Project root is required")
    resolved = Path(root.strip()).resolve()
    if not resolved.is_dir():
        raise StagedEditError("Project root is not a directory")
    project_id = root_id(resolved)
    registry = load_registry(data_dir)
    if project_id in registry:
        raise StagedEditError("Project root is already registered")
    record: dict[str, Any] = {
        "id": project_id,
        "name": name.strip(),
        "root": str(resolved),
        "description": description.strip(),
        "created_at_utc": _utc_now(),
    }
    registry[project_id] = record
    _save_registry(data_dir, registry)
    return record
