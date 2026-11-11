"""Project registry: named roots in data/projects.json with HTTP CRUD-lite."""

from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest
from ai_agent.staged_edits import ProjectRoots, root_id
from dashboard_projects import (
    book_check_task,
    create_project,
    get_project,
    list_projects,
    set_project_manuscript,
)
from dashboard_test_http import get_json, post_json


def test_registry_round_trip(tmp_path) -> None:
    data_dir = tmp_path / "data"
    assert list_projects(data_dir) == []
    root = tmp_path / "proj"
    root.mkdir()
    record = create_project(data_dir, name="Shop", root=str(root), description="client site")
    assert record["id"] == root_id(root.resolve())
    assert record["name"] == "Shop"
    assert get_project(data_dir, record["id"]) == record
    assert [item["id"] for item in list_projects(data_dir)] == [record["id"]]
    stored = json.loads((data_dir / "projects.json").read_text(encoding="utf-8"))
    assert stored[record["id"]]["root"] == str(root.resolve())


def test_registry_id_selects_work_root(tmp_path) -> None:
    data_dir = tmp_path / "data"
    root = tmp_path / "proj"
    root.mkdir()
    record = create_project(data_dir, name="Shop", root=str(root))
    roots = ProjectRoots((str(root),))
    assert roots.select(record["id"]) == root.resolve()


def test_registry_refusals(tmp_path) -> None:
    from ai_agent.staged_edits import StagedEditError

    data_dir = tmp_path / "data"
    root = tmp_path / "proj"
    root.mkdir()
    create_project(data_dir, name="Shop", root=str(root))
    with pytest.raises(StagedEditError, match="already registered"):
        create_project(data_dir, name="Again", root=str(root))
    with pytest.raises(StagedEditError, match="not a directory"):
        create_project(data_dir, name="Ghost", root=str(tmp_path / "nope"))
    with pytest.raises(StagedEditError, match="1-200"):
        create_project(data_dir, name="  ", root=str(root))


def test_projects_endpoints(dashboard_server, tmp_path) -> None:
    assert get_json(dashboard_server, "/api/projects") == {"ok": True, "projects": []}
    root = tmp_path / "proj"
    root.mkdir()
    created = post_json(dashboard_server, "/api/projects", {"name": "Shop", "root": str(root)})
    assert created["ok"] is True
    project_id = created["project"]["id"]
    listed = get_json(dashboard_server, "/api/projects")
    assert [item["id"] for item in listed["projects"]] == [project_id]
    item = get_json(dashboard_server, f"/api/projects/{project_id}")
    assert item["project"]["name"] == "Shop"
    with pytest.raises(HTTPError) as exc:
        get_json(dashboard_server, "/api/projects/ghost")
    assert exc.value.code == 404
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/projects", {"name": "Dup", "root": str(root)})
    assert exc.value.code == 400
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/projects", {"name": "NoRoot", "root": "x"})
    assert exc.value.code == 400


def test_book_type_and_manuscript(tmp_path) -> None:
    from ai_agent.staged_edits import StagedEditError

    data_dir = tmp_path / "data"
    root = tmp_path / "novel"
    root.mkdir()
    (root / "draft.md").write_text("# Chapter 1\n", encoding="utf-8")
    record = create_project(data_dir, name="Novel", root=str(root), project_type="book")
    assert record["type"] == "book"
    with pytest.raises(StagedEditError, match="type must be"):
        create_project(data_dir, name="Zine", root=str(tmp_path), project_type="zine")
    with pytest.raises(StagedEditError, match="does not exist"):
        set_project_manuscript(data_dir, record["id"], "missing.md")
    with pytest.raises(StagedEditError, match="inside the project root"):
        set_project_manuscript(data_dir, record["id"], "../escape.md")
    updated = set_project_manuscript(data_dir, record["id"], "draft.md")
    assert updated["manuscript"] == "draft.md"
    reread = get_project(data_dir, record["id"])
    assert reread is not None
    assert reread["manuscript"] == "draft.md"
    shop = tmp_path / "shop"
    shop.mkdir()
    general = create_project(data_dir, name="Shop", root=str(shop))
    assert general["type"] == "general"
    with pytest.raises(StagedEditError, match="Only book projects"):
        set_project_manuscript(data_dir, general["id"], "draft.md")


def test_legacy_record_without_type_reads_general(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "projects.json").write_text(
        json.dumps({"abc": {"id": "abc", "name": "Old", "root": str(root)}}), encoding="utf-8"
    )
    legacy = get_project(data_dir, "abc")
    assert legacy is not None
    assert legacy["type"] == "general"


def test_book_check_task_framing(tmp_path) -> None:
    from ai_agent.staged_edits import StagedEditError

    data_dir = tmp_path / "data"
    root = tmp_path / "novel"
    root.mkdir()
    (root / "draft.md").write_text("# Chapter 1\n", encoding="utf-8")
    record = create_project(data_dir, name="Novel", root=str(root), project_type="book")
    with pytest.raises(StagedEditError, match="manuscript before"):
        book_check_task(record, "discrepancy")
    record = set_project_manuscript(data_dir, record["id"], "draft.md")
    title, body = book_check_task(record, "discrepancy", focus="timeline")
    assert "discrepancy" in title and "timeline" in body
    assert "do not rewrite prose" in body
    title, body = book_check_task(record, "scrutiny")
    assert "scrutiny" in title.lower() and "draft.md" in body
    with pytest.raises(StagedEditError, match="Check must be"):
        book_check_task(record, "rewrite")


def test_book_endpoints(dashboard_server, tmp_path) -> None:
    root = tmp_path / "novel"
    root.mkdir()
    (root / "draft.md").write_text("# Chapter 1\n", encoding="utf-8")
    created = post_json(
        dashboard_server,
        "/api/projects",
        {"name": "Novel", "root": str(root), "type": "book"},
    )
    project_id = created["project"]["id"]
    assert created["project"]["type"] == "book"
    with pytest.raises(HTTPError) as exc:
        post_json(
            dashboard_server,
            f"/api/projects/{project_id}/check",
            {"check": "discrepancy"},
        )
    assert exc.value.code == 400
    pointed = post_json(
        dashboard_server, f"/api/projects/{project_id}/manuscript", {"path": "draft.md"}
    )
    assert pointed == {"ok": True, "manuscript": "draft.md"}
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, f"/api/projects/{project_id}/manuscript", {"path": "../x.md"})
    assert exc.value.code == 400
    filed = post_json(
        dashboard_server,
        f"/api/projects/{project_id}/check",
        {"check": "scrutiny", "focus": "pacing"},
    )
    assert filed["ok"] is True
    task = get_json(dashboard_server, f"/api/inbox/{filed['inbox_id']}")
    assert task["item"]["assignee"] == "agent"
    assert "pacing" in task["item"]["body"]
    general = post_json(dashboard_server, "/api/projects", {"name": "Shop", "root": str(tmp_path)})
    with pytest.raises(HTTPError) as exc:
        post_json(
            dashboard_server,
            f"/api/projects/{general['project']['id']}/check",
            {"check": "discrepancy"},
        )
    assert exc.value.code == 400
