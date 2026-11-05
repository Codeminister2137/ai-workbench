"""Project registry: named roots in data/projects.json with HTTP CRUD-lite."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from ai_agent.staged_edits import ProjectRoots, root_id
from dashboard_projects import create_project, get_project, list_projects
from dashboard_web_app import DashboardRequestHandler


@pytest.fixture
def dashboard_server(tmp_path):
    config_path = tmp_path / "dashboard.json"
    config_path.write_text(json.dumps({"title": "Test Board"}), encoding="utf-8")

    class TestHandler(DashboardRequestHandler):
        def log_message(self, format, *args):
            return

    TestHandler.config_path = config_path
    TestHandler.data_dir = tmp_path / "data"
    TestHandler.repo_root = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def get_json(base: str, path: str) -> dict:
    with urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


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
