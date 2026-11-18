"""Seed script: product projects register once, migration is idempotent."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts" / "seed-workbench-projects.py"


def _load():
    spec = importlib.util.spec_from_file_location("seed_workbench_projects", HERE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED = _load()


def test_seed_registers_seven_and_reruns_clean(tmp_path: Path, capsys) -> None:
    data_dir = tmp_path / "data"
    ids = SEED.seed_projects(data_dir, dry_run=False)
    assert len(ids) == 7
    registry = json.loads((data_dir / "projects.json").read_text(encoding="utf-8"))
    assert len(registry) == 7
    assert all(
        record.get("explainer", "").startswith("docs/projects/") for record in registry.values()
    )
    capsys.readouterr()
    SEED.seed_projects(data_dir, dry_run=False)
    out = capsys.readouterr().out
    assert "+ " not in out
    registry2 = json.loads((data_dir / "projects.json").read_text(encoding="utf-8"))
    assert len(registry2) == 7


def test_migrate_empty_is_zero(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    counts = SEED.migrate_records(data_dir, "rootid", dry_run=False)
    assert counts == {"legacy": 0, "e2e_tasks": 0, "runs": 0, "inbox": 0}


def test_roadmaps_seed_one_per_project(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "seed_roadmaps", Path(__file__).resolve().parent.parent / "scripts" / "seed-roadmaps.py"
    )
    assert spec is not None and spec.loader is not None
    roads = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(roads)
    data_dir = tmp_path / "data"
    SEED.seed_projects(data_dir, dry_run=False)
    seeded = roads.seed_roadmaps(data_dir, dry_run=False)
    assert len(seeded) == 7
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "workbench_dashboard"))
    from dashboard_stores import DashboardStores

    stores = DashboardStores(data_dir)
    items, total = stores.plans.list(limit=20)
    assert total == 7
    assert {i.get("kind") for i in items} == {"roadmap"}
    assert all("## Evolutions" in (i.get("body") or "") for i in items)
    assert all("## State" in (i.get("body") or "") for i in items)
    assert roads.seed_roadmaps(data_dir, dry_run=False) == seeded  # idempotent
