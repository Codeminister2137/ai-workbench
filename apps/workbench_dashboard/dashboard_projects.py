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
PROJECT_TYPES = ("general", "book")
BOOK_CHECKS = ("discrepancy", "scrutiny")


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
            record.setdefault("type", "general")
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
    data_dir: Path,
    *,
    name: str,
    root: str,
    description: str = "",
    project_type: str = "general",
) -> dict[str, Any]:
    """Register a project root; refuses duplicates, missing dirs, bad names."""
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME_CHARS:
        raise StagedEditError("Project name requires 1-200 characters")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        raise StagedEditError("Project description allows up to 2000 characters")
    if project_type not in PROJECT_TYPES:
        raise StagedEditError(f"Project type must be one of {PROJECT_TYPES}")
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
        "type": project_type,
        "created_at_utc": _utc_now(),
    }
    registry[project_id] = record
    _save_registry(data_dir, registry)
    return record


def set_project_manuscript(data_dir: Path, project_id: str, rel_path: str) -> dict[str, Any]:
    """Point a book project at its manuscript file (root-relative, must exist).

    Only book projects carry a manuscript; the path must stay inside the
    project root. Stored relative so the registry survives root moves.
    """
    registry = load_registry(data_dir)
    record = registry.get(project_id)
    if record is None:
        raise StagedEditError("Project not found")
    if record.get("type", "general") != "book":
        raise StagedEditError("Only book projects carry a manuscript")
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise StagedEditError("Manuscript path is required")
    candidate = (Path(str(record["root"])) / rel_path.strip()).resolve()
    if not candidate.is_relative_to(Path(str(record["root"])).resolve()):
        raise StagedEditError("Manuscript path must stay inside the project root")
    if not candidate.is_file():
        raise StagedEditError("Manuscript file does not exist")
    record["manuscript"] = candidate.relative_to(Path(str(record["root"])).resolve()).as_posix()
    _save_registry(data_dir, registry)
    return record


def book_check_task(project: dict[str, Any], check: str, focus: str = "") -> tuple[str, str]:
    """Render the owner->agent inbox task for a manuscript check.

    Beta-reader framing: discrepancy checks and scrutiny on demand. The
    agent never pushes generative prose; it reports findings on the text.
    """
    if project.get("type", "general") != "book":
        raise StagedEditError("Only book projects take manuscript checks")
    manuscript = project.get("manuscript")
    if not manuscript:
        raise StagedEditError("Set the project manuscript before requesting a check")
    if check not in BOOK_CHECKS:
        raise StagedEditError(f"Check must be one of {BOOK_CHECKS}")
    focus = focus.strip()
    if check == "discrepancy":
        title = f"Manuscript discrepancy check: {project['name']}"
        body = (
            f"Beta-read the manuscript at {project['root']}/{manuscript} "
            f"(project {project['id']}) and report continuity/discrepancy findings: "
            "names, timelines, facts contradicting earlier chapters. "
            "Report findings only; do not rewrite prose."
        )
    else:
        title = f"Manuscript scrutiny on demand: {project['name']}"
        body = (
            f"Scrutinize the manuscript at {project['root']}/{manuscript} "
            f"(project {project['id']}) as a demanding editor. "
            "Report concrete issues with chapter/paragraph pointers. "
            "Do not rewrite prose unless asked."
        )
    if focus:
        body += f" Focus: {focus[:500]}."
    return title, body
