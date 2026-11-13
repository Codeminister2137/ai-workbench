"""Project registry: named work roots backed by data/projects.json.

One JSON object mapping project id to record. The id is the stable
``root_id`` digest of the resolved root directory, so a registry id
plugs directly into ``ProjectRoots.select`` anywhere runs, staged
approvals, and the executor resolve project scope. One project per
root; the root must be an existing directory at creation time.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_agent.staged_edits import StagedEditError, root_id

PROJECTS_FILENAME = "projects.json"
MAX_NAME_CHARS = 200
MAX_DESCRIPTION_CHARS = 2000
PROJECT_TYPES = ("general", "book")
BOOK_CHECKS = ("discrepancy", "scrutiny")
GOALS_REGISTRY = "docs/goals/registry.json"


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


def _next_action(repo_root: Path, goal_rel: str) -> str:
    """First paragraph of the goal doc's Next action section (fail-soft)."""
    try:
        lines = (repo_root / goal_rel).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    capture: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip() == "## Next action"
        elif inside and line.strip():
            capture.append(line.strip())
    return " ".join(capture)


PLAN_HEADER_RE = re.compile(
    r"<!-- Project: ([^|]+) \| Status: ([^|]+) \| Timebox: ([^|]+) \| Replaces: ([^-]+) -->"
)
PLAN_STALE_DAYS = {"draft": 60, "active": 60, "blocked": 30}


def list_plan_attention(repo_root: Path, *, now: float | None = None) -> list[dict[str, Any]]:
    """Plans needing eyes: unset timebox or untouched past threshold.

    Fail-soft: a missing plans dir reads empty. advisory, never a gate.
    """
    import time

    plans_dir = repo_root / "docs" / "plans"
    if not plans_dir.is_dir():
        return []
    moment = time.time() if now is None else now
    flagged: list[dict[str, Any]] = []
    for path in sorted(plans_dir.glob("*.md")):
        try:
            head = path.read_text(encoding="utf-8").splitlines()[:5]
            age_days = (moment - path.stat().st_mtime) / 86400
        except OSError:
            continue
        match = next((PLAN_HEADER_RE.fullmatch(line.strip()) for line in head), None)
        if match is None:
            continue
        status = match.group(2).strip()
        timebox = match.group(3).strip()
        if status not in PLAN_STALE_DAYS:
            continue
        reasons: list[str] = []
        if timebox == "triage":
            reasons.append("timebox unset")
        limit = PLAN_STALE_DAYS[status]
        if age_days > limit:
            reasons.append(f"untouched {int(age_days)} days (>{limit})")
        if reasons:
            flagged.append(
                {
                    "plan": path.name,
                    "project": match.group(1).strip(),
                    "status": status,
                    "reasons": reasons,
                }
            )
    return flagged


def list_goals(repo_root: Path) -> list[dict[str, Any]]:
    """Goal registry entries with next actions; missing registry reads empty."""
    try:
        payload = json.loads((repo_root / GOALS_REGISTRY).read_text(encoding="utf-8"))
        projects = payload.get("projects", {})
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(projects, dict):
        return []
    goals: list[dict[str, Any]] = []
    for project_id in sorted(projects):
        entry = projects[project_id]
        if not isinstance(entry, dict):
            continue
        goals.append(
            {
                "id": project_id,
                "goal": str(entry.get("goal", "")),
                "repo": str(entry.get("repo", "")),
                "owner": str(entry.get("owner", "")),
                "health": str(entry.get("health", "")),
                "relations": entry.get("relations", {}),
                "next_action": _next_action(repo_root, str(entry.get("goal", ""))),
            }
        )
    return goals


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
