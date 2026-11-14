"""E2E task stores and HTTP surface (ADR-087)."""

from __future__ import annotations

import json
from urllib.request import Request, urlopen

import pytest
from dashboard_stores import DashboardStores, StoreError
from dashboard_test_http import get_json


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def _items() -> list[dict]:
    return [
        {
            "id": "behavior:dashboard",
            "kind": "behavior",
            "area": "dashboard",
            "behavior": "dashboard views and actions",
            "files": ["apps/workbench_dashboard/web/app.js"],
            "goals": ["docs/goals/dashboard.md"],
            "status": "pending",
        },
        {
            "id": "nonbehavioral:docs",
            "kind": "nonbehavioral",
            "area": "docs",
            "behavior": "documentation",
            "files": ["docs/notes.md"],
            "goals": ["docs/goals/meta.md"],
            "status": "auto-pass",
            "verdict_by": "nonbehavioral",
            "reason": "docs carry no user-visible behavior",
        },
    ]


def test_create_refuses_second_open_task_per_merge(stores) -> None:
    stores.create_e2e_task(merge_commit="abc", title="t", items=_items())
    assert stores.open_e2e_count() == 1
    with pytest.raises(StoreError, match="already exists"):
        stores.create_e2e_task(merge_commit="abc", title="t2", items=_items())


def test_create_validates_items(stores) -> None:
    with pytest.raises(StoreError, match="at least one"):
        stores.create_e2e_task(merge_commit="abc", title="t", items=[])
    bad = _items()
    bad[0]["kind"] = "vibes"
    with pytest.raises(StoreError, match="kind"):
        stores.create_e2e_task(merge_commit="abc", title="t", items=bad)


def test_submit_builds_report_and_freezes_task(stores) -> None:
    task = stores.create_e2e_task(merge_commit="abc", title="t", items=_items())
    outcome = stores.submit_e2e_task(
        task["id"],
        [{"item_id": "behavior:dashboard", "verdict": "pass", "notes": "clicked through"}],
    )
    assert outcome["task"]["status"] == "submitted"
    assert outcome["report"]["overall"] == "pass"
    assert outcome["report"]["items"][1]["verdict_by"] == "nonbehavioral"
    assert stores.open_e2e_count() == 0
    with pytest.raises(StoreError, match="already submitted"):
        stores.submit_e2e_task(task["id"], [])


def test_submit_requires_every_pending_verdict(stores) -> None:
    task = stores.create_e2e_task(merge_commit="abc", title="t", items=_items())
    with pytest.raises(StoreError, match="[Mm]issing verdict"):
        stores.submit_e2e_task(task["id"], [])


def post_json(base: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def test_e2e_http_roundtrip(dashboard_server) -> None:
    created = post_json(
        dashboard_server,
        "/api/e2e/tasks",
        {"merge_commit": "abc", "title": "t", "items": _items()},
    )
    assert created["ok"] is True
    listed = get_json(dashboard_server, "/api/e2e/tasks?status=open")
    assert listed["total"] == 1
    detail = get_json(dashboard_server, f"/api/e2e/tasks/{created['id']}")
    assert detail["item"]["merge_commit"] == "abc"
    submitted = post_json(
        dashboard_server,
        f"/api/e2e/tasks/{created['id']}/submit",
        {"results": [{"item_id": "behavior:dashboard", "verdict": "fail", "notes": "broken"}]},
    )
    assert submitted["overall"] == "fail"
    assert submitted["report_id"]
    report = get_json(dashboard_server, f"/api/e2e/reports/{submitted['report_id']}")
    assert report["item"]["overall"] == "fail"
    status = get_json(dashboard_server, "/api/status")
    assert status["open_e2e"] == 0
