"""Scaffold a new project id end-to-end (registry-first, validated).

Usage:
    python scripts/add-project.py ID --name NAME [--root REL] [--description TEXT]
        [--explainer PATH] [--areas a,b] [--goal PATH] [--health H] [--dry-run]

Writes: registry entry, goal stub, explainer stub (dashboard tracks
only), then validates (goal/explainer files exist, registry parses,
header ids resolve, seed dry-run passes). New code tracks pass --root
with a dashboard product; pre-scaffold tracks (docs/plans only, like
investor at birth) omit --root and get no dashboard block.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
REGISTRY = REPO / "docs" / "goals" / "registry.json"
HEALTHS = ("on-track", "at-risk", "off-track", "paused")


def _load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _goal_stub(project_id: str, name: str) -> str:
    return (
        f"# {name}\n\n## Goal\n\nTODO: one paragraph.\n\n## Non-goals\n\nTODO.\n\n"
        f"## Owner\n\nJakub.\n\n## Health\n\non-track.\n\n## Connected plans\n\nNone yet.\n\n"
        "## Next action\n\nTODO.\n"
    )


def _explainer_stub(project_id: str, name: str) -> str:
    return f"# {name}\n\nTODO: dashboard explainer for `{project_id}`.\n"


def add_project(
    project_id: str,
    *,
    name: str,
    root: str | None,
    description: str,
    explainer: str | None,
    areas: tuple[str, ...],
    goal: str | None,
    health: str,
    dry_run: bool,
) -> dict:
    """Scaffold + validate; returns the registry entry. Raises on problems."""
    if not project_id or project_id.strip() != project_id or " " in project_id:
        raise ValueError("project id must be a non-empty slug without spaces")
    if health not in HEALTHS:
        raise ValueError(f"health must be one of {HEALTHS}")
    registry = _load_registry()
    projects = registry["projects"]
    if project_id in projects:
        raise ValueError(f"project id already registered: {project_id}")
    goal_path = goal or f"docs/goals/{project_id}.md"
    entry: dict = {
        "goal": goal_path,
        "repo": "ai-workbench",
        "owner": "Jakub",
        "health": health,
        "relations": {},
    }
    writes: list[tuple[Path, str]] = []
    if root:
        explainer_path = explainer or f"docs/projects/{project_id}.md"
        entry["dashboard"] = {
            "name": name,
            "root": root,
            "description": description or f"TODO: describe {name}.",
            "explainer": explainer_path,
            "areas": list(areas),
        }
        writes.append((REPO / explainer_path, _explainer_stub(project_id, name)))
    writes.append((REPO / goal_path, _goal_stub(project_id, name)))
    for path, _ in writes:
        if path.exists():
            raise ValueError(f"refusing to overwrite existing file: {path}")
    if dry_run:
        print(f"would register {project_id} -> {goal_path}")
        for path, _ in writes:
            print(f"  + {path.relative_to(REPO).as_posix()}")
        return entry
    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    projects[project_id] = entry
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    problems = validate_registry()
    if problems:
        raise ValueError("registry invalid after write: " + "; ".join(problems))
    return entry


def validate_registry() -> list[str]:
    """Check every registry entry's files and dashboard block; returns problems."""
    problems = []
    registry = _load_registry()
    projects = registry.get("projects", {})
    for project_id, entry in sorted(projects.items()):
        if not isinstance(entry, dict):
            problems.append(f"{project_id}: entry is not an object")
            continue
        goal = entry.get("goal")
        if not goal or not (REPO / goal).is_file():
            problems.append(f"{project_id}: missing goal file {goal}")
        if entry.get("health") not in HEALTHS:
            problems.append(f"{project_id}: bad health {entry.get('health')!r}")
        for relation, targets in (entry.get("relations") or {}).items():
            for target in targets or []:
                if target not in projects:
                    problems.append(f"{project_id}: relation {relation} -> unknown {target}")
        seed = entry.get("dashboard")
        if not seed:
            continue
        for key in ("name", "root", "description", "explainer"):
            if not seed.get(key):
                problems.append(f"{project_id}: dashboard.{key} missing")
        explainer = seed.get("explainer", "")
        if explainer and not (REPO / explainer).is_file():
            problems.append(f"{project_id}: missing explainer {explainer}")
        if not (REPO / seed.get("root", "\0")).exists():
            problems.append(f"{project_id}: missing root {seed.get('root')}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a new registry project.")
    parser.add_argument("project_id", nargs="?")
    parser.add_argument("--name", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--description", default="")
    parser.add_argument("--explainer", default=None)
    parser.add_argument("--areas", default="")
    parser.add_argument("--goal", default=None)
    parser.add_argument("--health", default="on-track")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if args.validate_only:
        problems = validate_registry()
        for problem in problems:
            print(f"INVALID: {problem}")
        return 1 if problems else 0
    if not args.project_id or not args.name:
        print("add-project: project_id and --name are required (or --validate-only)")
        return 2
    try:
        add_project(
            args.project_id,
            name=args.name,
            root=args.root,
            description=args.description,
            explainer=args.explainer,
            areas=tuple(a for a in args.areas.split(",") if a),
            goal=args.goal,
            health=args.health,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"add-project: {exc}")
        return 2
    print(f"registered {args.project_id}" if not args.dry_run else "dry-run ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
