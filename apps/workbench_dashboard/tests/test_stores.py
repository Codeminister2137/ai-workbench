from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores, StoreError


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def test_create_answer_close_inbox_task(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick a model",
        body="Which backend answers first?",
        task_type="decision",
        options=["Local", "Hosted"],
    )
    assert record["status"] == "open"
    assert stores.open_inbox_count() == 1

    answered = stores.answer_inbox_task(record["id"], answer="", option_index=1)
    assert answered["status"] == "answered"
    assert answered["answer"] == "Hosted"

    closed = stores.close_inbox_task(record["id"])
    assert closed["status"] == "closed"
    with pytest.raises(StoreError, match="re-answered"):
        stores.answer_inbox_task(record["id"], answer="Changed mind")


def test_inbox_create_validates_type_and_title(stores) -> None:
    with pytest.raises(StoreError, match="title"):
        stores.create_inbox_task(title="  ", body="b", task_type="decision")
    with pytest.raises(StoreError, match="type"):
        stores.create_inbox_task(title="t", body="b", task_type="manual_test")


def test_supervisor_token_gate(stores) -> None:
    assert stores.check_supervisor_token(None) is True
    stores.token_path.parent.mkdir(parents=True, exist_ok=True)
    stores.token_path.write_text("s3cret\n", encoding="utf-8")
    assert stores.check_supervisor_token(None) is False
    assert stores.check_supervisor_token("wrong") is False
    assert stores.check_supervisor_token("s3cret") is True


def test_collection_rejects_path_escape(stores) -> None:
    with pytest.raises(StoreError, match="Invalid item id"):
        stores.plans.get("../evil")
    with pytest.raises(StoreError, match="Invalid item id"):
        stores.runs.get("..\\evil")


def test_plans_round_trip(stores) -> None:
    stores.plans.put("plan-1", {"id": "plan-1", "title": "First", "status": "active"})
    items, total = stores.plans.list()
    assert total == 1
    assert items[0]["title"] == "First"
    assert stores.plans.get("missing") is None


def test_idea_capture_and_triage(stores) -> None:
    idea = stores.create_idea(
        title="Third-party wish",
        body="An app that waters plants.",
        source="third-party",
        contact="Friend",
    )
    assert idea["status"] == "new"
    assert idea["source"] == "third-party"
    assert stores.new_idea_count() == 1

    reviewed = stores.set_idea_status(idea["id"], status="adopted", decision="Prototype it")
    assert reviewed["status"] == "adopted"
    assert reviewed["decision"] == "Prototype it"
    assert stores.new_idea_count() == 0


def test_idea_create_validates_source_and_title(stores) -> None:
    with pytest.raises(StoreError, match="title"):
        stores.create_idea(title="  ", body="b", source="owner")
    with pytest.raises(StoreError, match="source"):
        stores.create_idea(title="t", body="b", source="stranger")
    with pytest.raises(StoreError, match="not found"):
        stores.set_idea_status("missing", status="adopted")
