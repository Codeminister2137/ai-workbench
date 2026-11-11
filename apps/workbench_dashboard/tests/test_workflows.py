"""Workflow builder: graph store, endpoints, dry-run validation."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest
from dashboard_stores import DashboardStores, StoreError
from dashboard_test_http import get_json, post_json


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


NODES = [
    {"id": "plan", "type": "agent_run", "label": "Plan", "config": {"mode": "plan"}},
    {"id": "check", "type": "scrutiny", "config": {"focus": "risks"}},
    {"id": "gate", "type": "owner_checkpoint", "config": {"question": "Proceed?"}},
]


def test_create_get_and_archive(stores) -> None:
    record = stores.create_workflow(name="Loop", description="d", nodes=NODES)
    assert record["status"] == "active"
    assert [node["id"] for node in record["nodes"]] == ["plan", "check", "gate"]
    assert stores.workflows.get(record["id"]) == record
    archived = stores.set_workflow_status(record["id"], status="archived")
    assert archived["status"] == "archived"
    with pytest.raises(StoreError, match="status"):
        stores.set_workflow_status(record["id"], status="nope")
    with pytest.raises(StoreError, match="not found"):
        stores.set_workflow_status("ghost", status="archived")


def test_create_refuses_bad_graphs(stores) -> None:
    with pytest.raises(StoreError, match="non-empty string"):
        stores.create_workflow(name="  ", nodes=[])
    with pytest.raises(StoreError, match="Unknown workflow node type"):
        stores.create_workflow(name="x", nodes=[{"id": "a", "type": "nope"}])
    with pytest.raises(StoreError, match="unknown skill"):
        stores.create_workflow(
            name="x", nodes=[{"id": "a", "type": "skill", "config": {"skill": "nope"}}]
        )


def test_workflow_endpoints(dashboard_server) -> None:
    options = get_json(dashboard_server, "/api/workflows/options")
    assert options["node_types"] == ["skill", "scrutiny", "agent_run", "owner_checkpoint"]
    assert "git-safety" in options["skills"] and "implement" in options["modes"]
    created = post_json(
        dashboard_server,
        "/api/workflows",
        {"name": "Loop", "description": "d", "nodes": NODES},
    )
    assert created["ok"] is True
    workflow_id = created["id"]
    listed = get_json(dashboard_server, "/api/workflows")
    assert [item["id"] for item in listed["items"]] == [workflow_id]
    item = get_json(dashboard_server, f"/api/workflows/{workflow_id}")
    assert item["item"]["name"] == "Loop"
    planned = post_json(
        dashboard_server, "/api/workflows/validate", {"name": "Loop", "nodes": NODES}
    )
    assert [step["runner"] for step in planned["plan"]] == [
        "repo-assistant:plan",
        "run_orchestrated_scrutiny",
        "ask_owner",
    ]
    with pytest.raises(HTTPError) as exc:
        post_json(
            dashboard_server,
            "/api/workflows/validate",
            {"name": "x", "nodes": [{"id": "a", "type": "nope"}]},
        )
    assert exc.value.code == 400
    moved = post_json(
        dashboard_server, f"/api/workflows/{workflow_id}/status", {"status": "archived"}
    )
    assert moved == {"ok": True, "status": "archived"}
    assert get_json(dashboard_server, "/api/workflows?status=active")["items"] == []
    with pytest.raises(HTTPError) as exc:
        post_json(dashboard_server, "/api/workflows", {"name": "x", "nodes": "nope"})
    assert exc.value.code == 400
    with pytest.raises(HTTPError) as exc:
        get_json(dashboard_server, "/api/workflows/ghost")
    assert exc.value.code == 404
