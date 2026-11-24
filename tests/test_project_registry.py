"""Single project registry: seed, headers and map read one source."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "goals" / "registry.json"


def _load_seed():
    spec = importlib.util.spec_from_file_location(
        "seed_workbench_projects", ROOT / "scripts" / "seed-workbench-projects.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_add():
    spec = importlib.util.spec_from_file_location(
        "add_project", ROOT / "scripts" / "add-project.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_products_derive_from_registry():
    seed = _load_seed()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    expected_rows = tuple(
        (block["name"], block["root"], block["description"], block["explainer"])
        for entry in registry["projects"].values()
        if (block := entry.get("dashboard"))
    )
    assert seed.PRODUCTS == expected_rows
    expected_areas = {
        area: block["root"]
        for entry in registry["projects"].values()
        if (block := entry.get("dashboard"))
        for area in block.get("areas", [])
    }
    assert seed.AREA_PRODUCTS == expected_areas
    assert len(seed.PRODUCTS) >= 7  # root + six dashboard products


def test_registry_validates_clean():
    add = _load_add()
    assert add.validate_registry() == []


def test_add_project_roundtrip_in_isolation(tmp_path, monkeypatch):
    add = _load_add()
    repo = tmp_path / "repo"
    (repo / "docs" / "goals").mkdir(parents=True)
    (repo / "docs" / "projects").mkdir(parents=True)
    (repo / "docs" / "goals" / "registry.json").write_text(
        json.dumps({"version": 1, "projects": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(add, "REPO", repo)
    monkeypatch.setattr(add, "REGISTRY", repo / "docs" / "goals" / "registry.json")
    (repo / "apps" / "demo").mkdir(parents=True)
    entry = add.add_project(
        "demo",
        name="Demo",
        root="apps/demo",
        description="Demo product.",
        explainer=None,
        areas=("demo",),
        goal=None,
        health="on-track",
        dry_run=False,
    )
    assert entry["dashboard"]["root"] == "apps/demo"
    assert (repo / "docs" / "goals" / "demo.md").is_file()
    assert (repo / "docs" / "projects" / "demo.md").is_file()
    assert add.validate_registry() == []
    # Docs-only track: no dashboard block, no explainer.
    entry2 = add.add_project(
        "docsy",
        name="Docsy",
        root=None,
        description="",
        explainer=None,
        areas=(),
        goal=None,
        health="paused",
        dry_run=False,
    )
    assert "dashboard" not in entry2
    assert add.validate_registry() == []


def test_investor_registered_without_dashboard_block():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    investor = registry["projects"]["investor"]
    assert (ROOT / investor["goal"]).is_file()
    assert "dashboard" not in investor
