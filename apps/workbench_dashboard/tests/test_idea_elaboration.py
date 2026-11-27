from __future__ import annotations

from dashboard_stores import MAX_OPEN_TASKS, DashboardStores


def _elaboration_tasks(stores: DashboardStores, idea_id: str) -> list[dict]:
    items, _total = stores.inbox.list(limit=1000)
    return [
        item
        for item in items
        if isinstance(item, dict) and (item.get("metadata") or {}).get("elaboration_for") == idea_id
    ]


def test_adopt_files_elaboration_task(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    stores.plans.put("plan-1", {"id": "plan-1", "title": "First", "status": "active"})
    idea = stores.create_idea(title="Plant app", body="An app that waters plants.", source="owner")

    reviewed = stores.set_idea_status(
        idea["id"], status="adopted", decision="Prototype it", plan_id="plan-1"
    )
    assert reviewed["status"] == "adopted"

    filed = _elaboration_tasks(stores, idea["id"])
    assert len(filed) == 1
    task = filed[0]
    assert task["title"] == "Elaborate adopted idea: Plant app"
    assert task["type"] == "task"
    assert task["assignee"] == "agent"
    assert task["status"] == "open"
    assert task["context_refs"] == [f"idea:{idea['id']}"]
    assert task["metadata"] == {"elaboration_for": idea["id"], "author_source": "rule"}
    assert "An app that waters plants." in task["body"]
    assert "Prototype it" in task["body"]
    assert "plan-1" in task["body"]
    stored = stores.ideas.get(idea["id"])
    assert stored is not None
    assert stored.get("elaboration_pending") is None


def test_adopt_without_plan_notes_no_plan_link(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    idea = stores.create_idea(title="Solo thought", body="Faster loop.", source="owner")

    stores.set_idea_status(idea["id"], status="adopted", decision="Explore")

    filed = _elaboration_tasks(stores, idea["id"])
    assert len(filed) == 1
    assert "no plan link" in filed[0]["body"]


def test_park_and_decline_file_nothing(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    parked = stores.create_idea(title="Later", body="Not now.", source="owner")
    stores.set_idea_status(parked["id"], status="parked", decision="Revisit")
    assert _elaboration_tasks(stores, parked["id"]) == []

    declined = stores.create_idea(title="Nope", body="Out of scope.", source="owner")
    stores.set_idea_status(declined["id"], status="declined", decision="Drop")
    assert _elaboration_tasks(stores, declined["id"]) == []

    items, _total = stores.inbox.list(limit=1000)
    assert items == []


def test_readopt_files_nothing(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    idea = stores.create_idea(title="Keeper", body="Worth doing.", source="owner")
    stores.set_idea_status(idea["id"], status="adopted", decision="Go")
    assert len(_elaboration_tasks(stores, idea["id"])) == 1

    stores.set_idea_status(idea["id"], status="adopted", decision="Still go")
    assert len(_elaboration_tasks(stores, idea["id"])) == 1

    stores.set_idea_status(idea["id"], status="parked", decision="Pause")
    stores.set_idea_status(idea["id"], status="adopted", decision="Resume")
    assert len(_elaboration_tasks(stores, idea["id"])) == 1


def test_cap_refusal_flags_pending_without_raising(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    for index in range(MAX_OPEN_TASKS):
        stores.create_inbox_task(title=f"filler {index}", body="b", task_type="task")
    idea = stores.create_idea(title="Capped", body="No room.", source="owner")

    reviewed = stores.set_idea_status(idea["id"], status="adopted", decision="Go anyway")

    assert reviewed["status"] == "adopted"
    assert reviewed["elaboration_pending"] is True
    stored = stores.ideas.get(idea["id"])
    assert stored is not None
    assert stored["elaboration_pending"] is True
    assert _elaboration_tasks(stores, idea["id"]) == []
    assert stores.open_inbox_count() == MAX_OPEN_TASKS
