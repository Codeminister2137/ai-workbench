from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores, StoreError, effective_fanout_policy


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

    closed = stores.close_inbox_task(record["id"], resolution="Hosted won.")
    assert closed["status"] == "closed"
    assert closed["resolution"] == "Hosted won."
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


def test_idea_plan_link_marks_backlog_influence(stores) -> None:
    """Adopted ideas link a plan; missing plans are refused."""
    stores.plans.put("plan-1", {"id": "plan-1", "title": "First", "status": "active"})
    idea = stores.create_idea(title="t", body="b", source="owner")
    linked = stores.set_idea_status(idea["id"], status="adopted", plan_id="plan-1")
    assert linked["plan_id"] == "plan-1"
    cleared = stores.set_idea_status(idea["id"], status="adopted")
    assert cleared["plan_id"] is None
    with pytest.raises(StoreError, match="existing plan"):
        stores.set_idea_status(idea["id"], status="adopted", plan_id="ghost")
    with pytest.raises(StoreError, match="existing plan"):
        stores.set_idea_status(idea["id"], status="adopted", plan_id="../evil")


def test_answer_and_note_are_independent(stores) -> None:
    record = stores.create_inbox_task(
        title="Pick one",
        body="A or B?",
        task_type="decision",
        options=["Alpha", "Beta"],
    )
    answered = stores.answer_inbox_task(record["id"], answer=" leaning Beta ", option_index=1)
    assert answered["answer"] == "Beta"
    assert answered["option_index"] == 1
    assert answered["note"] == "leaning Beta"
    assert answered["status"] == "answered"

    typed = stores.create_inbox_task(
        title="Explain",
        body="Why?",
        task_type="clarification",
    )
    only = stores.answer_inbox_task(typed["id"], answer="Because.")
    assert only["answer"] == "Because."
    assert only["note"] is None


def test_effective_fanout_policy_prefers_effective() -> None:
    record = {"fanout_effective": "restricted", "fanout_policy": "allowed"}
    assert effective_fanout_policy(record) == "restricted"


def test_effective_fanout_policy_falls_back_to_policy() -> None:
    assert effective_fanout_policy({"fanout_policy": "denied"}) == "denied"


def test_effective_fanout_policy_unknown_for_legacy_record() -> None:
    assert effective_fanout_policy({"id": "w4", "status": "merged"}) == "unknown"
    assert effective_fanout_policy({"fanout_effective": "  ", "fanout_policy": None}) == "unknown"


def test_backlog_capture_groom_and_promote(stores) -> None:
    item = stores.create_backlog_item(
        title="Replicate fixture onto Go harness",
        body="Deferred item 3 leftover.",
        source="agent",
        ref="docs/plans/deferred-baseline-work-20261022.md §3",
    )
    assert item["status"] == "proposed"
    assert item["inbox_id"] is None
    assert stores.open_backlog_count() == 1

    groomed = stores.set_backlog_status(item["id"], status="ready", decision="Small slice")
    assert groomed["status"] == "ready"

    result = stores.promote_backlog_item(item["id"])
    assert result["inbox"]["type"] == "decision"
    assert result["inbox"]["options"] == ["A: Take into next run", "B: Hold"]
    assert "Deferred item 3" in result["inbox"]["body"]
    assert result["item"]["inbox_id"] == result["inbox"]["id"]


def test_backlog_create_validates_title_source_ref(stores) -> None:
    with pytest.raises(StoreError, match="title"):
        stores.create_backlog_item(title="  ", body="b")
    with pytest.raises(StoreError, match="source"):
        stores.create_backlog_item(title="t", body="b", source="stranger")
    with pytest.raises(StoreError, match="ref"):
        stores.create_backlog_item(title="t", body="b", ref="x" * 201)
    with pytest.raises(StoreError, match="not found"):
        stores.set_backlog_status("missing", status="ready")
    with pytest.raises(StoreError, match="status"):
        stores.set_backlog_status(
            stores.create_backlog_item(title="t", body="b")["id"], status="vibing"
        )


def test_promote_refuses_second_open_brief(stores) -> None:
    item = stores.create_backlog_item(title="t", body="b")
    first = stores.promote_backlog_item(item["id"])
    with pytest.raises(StoreError, match="already has an open inbox brief"):
        stores.promote_backlog_item(item["id"])
    stores.close_inbox_task(first["inbox"]["id"], resolution="Held.")
    second = stores.promote_backlog_item(item["id"])
    assert second["inbox"]["id"] != first["inbox"]["id"]


def test_close_marks_followup_kind_and_defaults_final(stores) -> None:
    record = stores.create_inbox_task(
        title="Need more info",
        body="Elaborate?",
        task_type="clarification",
    )
    marked = stores.close_inbox_task(
        record["id"], resolution="Waiting on elaboration.", resolution_kind="followup"
    )
    assert marked["status"] == "closed"
    assert marked["resolution_kind"] == "followup"

    other = stores.create_inbox_task(
        title="Done deal",
        body="Decided.",
        task_type="decision",
    )
    final = stores.close_inbox_task(other["id"], resolution="Implemented.")
    assert final["resolution_kind"] == "final"

    with pytest.raises(StoreError, match="resolution kind"):
        stores.close_inbox_task(other["id"], resolution="Again.", resolution_kind="bogus")
