"""Seed the product projects and migrate records onto project ids.

Idempotent: registered roots are skipped (explainer backfilled when
missing), and migration only rewrites the legacy "workbench" stamp plus
deterministic E2E area links — never guesses. Usage:

    python scripts/seed-workbench-projects.py [--dry-run] [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "apps" / "workbench_dashboard"))

from dashboard_projects import (  # noqa: E402
    create_project,
    load_registry,
    repo_project_id,
)
from dashboard_stores import DashboardStores  # noqa: E402


def _registry_dashboard() -> tuple[tuple[str, str, str, str], ...]:
    """Product seed rows from the single registry (docs/goals/registry.json).

    Only entries carrying a ``dashboard`` block seed dashboard projects;
    code-only areas (provider, orchestrator, ...) and pre-scaffold tracks
    (investor) stay out until they grow one. Order follows the registry.
    """
    import json

    registry = json.loads((REPO / "docs" / "goals" / "registry.json").read_text())
    rows = []
    for entry in registry["projects"].values():
        seed = entry.get("dashboard")
        if not seed:
            continue
        rows.append((seed["name"], seed["root"], seed["description"], seed["explainer"]))
    return tuple(rows)


def _registry_area_products() -> dict[str, str]:
    """E2E area -> product root, inverted from registry dashboard blocks."""
    import json

    registry = json.loads((REPO / "docs" / "goals" / "registry.json").read_text())
    mapping = {}
    for entry in registry["projects"].values():
        seed = entry.get("dashboard")
        if not seed:
            continue
        for area in seed.get("areas", []):
            mapping[area] = seed["root"]
    return mapping


PRODUCTS: tuple[tuple[str, str, str, str], ...] = _registry_dashboard()

LEGACY_ROOT_STAMP = "workbench"

# E2E area -> product root (relative). Areas outside this map stay on root.
AREA_PRODUCTS = _registry_area_products()


def seed_projects(data_dir: Path, *, dry_run: bool) -> dict[str, str]:
    """Register the product projects; returns name -> id. Skips registered."""
    import json

    from dashboard_projects import PROJECTS_FILENAME

    ids: dict[str, str] = {}
    for name, rel, description, explainer in PRODUCTS:
        root = str((REPO / rel).resolve())
        digest = repo_project_id(root)
        ids[name] = digest
        registry = load_registry(data_dir)
        if digest in registry:
            record = registry[digest]
            if not record.get("explainer") and not dry_run:
                record["explainer"] = explainer
                path = data_dir / PROJECTS_FILENAME
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(registry, indent=2), encoding="utf-8")
                tmp.replace(path)
            print(f"  keep {name} ({digest[:8]})")
            continue
        if dry_run:
            print(f"  + {name} ({digest[:8]}) {rel}")
            continue
        record = create_project(
            data_dir, name=name, root=root, description=description, explainer=explainer
        )
        print(f"  + {name} ({record['id'][:8]}) {rel}")
    return ids


def migrate_records(data_dir: Path, root_id: str, *, dry_run: bool) -> dict[str, int]:
    """Rewrite legacy stamps and deterministic E2E links. Returns counts."""
    stores = DashboardStores(data_dir)
    counts = {"legacy": 0, "e2e_tasks": 0, "runs": 0, "inbox": 0}
    area_ids = {area: repo_project_id(REPO / rel) for area, rel in AREA_PRODUCTS.items()}

    def task_project(task: dict) -> str:
        products = set()
        for item in task.get("items", []) or []:
            if not isinstance(item, dict) or item.get("status") == "auto-pass":
                continue
            product = area_ids.get(str(item.get("area") or ""))
            if product is None:
                return root_id
            products.add(product)
        return products.pop() if len(products) == 1 else root_id

    tasks, _ = stores.e2e_tasks.list(limit=10000)
    by_merge = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        merge = task.get("merge_commit")
        if merge:
            by_merge[merge] = task
        if task.get("project_id") == LEGACY_ROOT_STAMP or not task.get("project_id"):
            counts["legacy"] += 1
            if not dry_run:
                task["project_id"] = root_id
                stores.e2e_tasks.put(task["id"], task)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        target = task_project(task)
        if target != root_id and task.get("project_id") != target:
            counts["e2e_tasks"] += 1
            if not dry_run:
                task["project_id"] = target
                stores.e2e_tasks.put(task["id"], task)
        if task.get("merge_commit"):
            by_merge[task["merge_commit"]] = target

    runs, _ = stores.runs.list(limit=10000)
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("project_id") == LEGACY_ROOT_STAMP or not run.get("project_id"):
            counts["legacy"] += 1
            title = str(run.get("title") or "")
            target = root_id
            if title.startswith("E2E pointers: "):
                linked = by_merge.get(title[len("E2E pointers: ") :])
                if linked is not None and linked != root_id:
                    target = linked
                    counts["runs"] += 1
            if not dry_run:
                run["project_id"] = target
                stores.runs.put(run["id"], run)

    inbox, _ = stores.inbox.list(limit=10000)
    for item in inbox:
        if not isinstance(item, dict):
            continue
        if item.get("project_id") == LEGACY_ROOT_STAMP or not item.get("project_id"):
            counts["legacy"] += 1
            title = str(item.get("title") or "")
            target = root_id
            if title.startswith("E2E pointers needed: "):
                linked = by_merge.get(title[len("E2E pointers needed: ") :])
                if linked is not None and linked != root_id:
                    target = linked
                    counts["inbox"] += 1
            if not dry_run:
                item["project_id"] = target
                stores.inbox.put(item["id"], item)

    plans, _ = stores.plans.list(limit=10000)
    for plan in plans:
        if not isinstance(plan, dict):
            continue
        if plan.get("project_id") == LEGACY_ROOT_STAMP or not plan.get("project_id"):
            counts["legacy"] += 1
            if not dry_run:
                plan["project_id"] = root_id
                stores.plans.put(plan["id"], plan)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed product projects and migrate records.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default=str(REPO / "apps" / "workbench_dashboard" / "data"))
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir)
    for _name, _rel, _desc, explainer in PRODUCTS:
        if not (REPO / explainer).is_file():
            print(f"missing explainer: {explainer}")
            return 2
    print("seeding projects:")
    seed_projects(data_dir, dry_run=args.dry_run)
    root_id = repo_project_id(REPO)
    print(f"migrating records (root {root_id[:8]}):")
    counts = migrate_records(data_dir, root_id, dry_run=args.dry_run)
    print("counts:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
