"""Project filters: runs by project_id, inbox via linked runs."""

from __future__ import annotations

from dashboard_stores import DashboardStores
from dashboard_test_http import get_json


def _seed(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    stores.runs.put("ra", {"id": "ra", "title": "a", "status": "queued", "project_id": "pa"})
    stores.runs.put("rb", {"id": "rb", "title": "b", "status": "queued", "project_id": "pb"})
    stores.runs.put("rc", {"id": "rc", "title": "c", "status": "queued"})
    stores.create_inbox_task(
        title="Approve A",
        body="x",
        task_type="decision",
        task_id="ra",
        context_refs=["run:ra"],
        options=["Approve", "Reject"],
    )
    stores.create_inbox_task(
        title="Approve B",
        body="x",
        task_type="decision",
        task_id="rb",
        context_refs=["run:rb"],
        options=["Approve", "Reject"],
    )
    stores.create_inbox_task(title="Loose", body="x", task_type="task")


def test_runs_filter_by_project(dashboard_server, tmp_path) -> None:
    _seed(tmp_path)
    payload = get_json(dashboard_server, "/api/runs?project_id=pa")
    assert [item["id"] for item in payload["items"]] == ["ra"]
    assert payload["total"] == 1
    payload = get_json(dashboard_server, "/api/runs?project_id=missing")
    assert payload["items"] == []
    assert get_json(dashboard_server, "/api/runs")["total"] == 3


def test_inbox_filter_by_project_via_runs(dashboard_server, tmp_path) -> None:
    _seed(tmp_path)
    payload = get_json(dashboard_server, "/api/inbox?project_id=pa")
    assert [item["title"] for item in payload["items"]] == ["Approve A"]
    payload = get_json(dashboard_server, "/api/inbox?project_id=pb&status=open")
    assert [item["title"] for item in payload["items"]] == ["Approve B"]
    assert get_json(dashboard_server, "/api/inbox?project_id=missing")["items"] == []
    assert get_json(dashboard_server, "/api/inbox")["total"] == 3
