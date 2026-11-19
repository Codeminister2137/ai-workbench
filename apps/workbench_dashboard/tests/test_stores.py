from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores, StoreError, effective_fanout_policy


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


def test_attention_inbox_counts_owner_waiting_only(stores) -> None:
    record = stores.create_inbox_task(
        title="Q?", body="b", task_type="decision", options=["A", "B"], assignee="owner"
    )
    assert stores.attention_inbox_count() == 1
    stores.answer_inbox_task(record["id"], answer="", option_index=0)
    assert stores.attention_inbox_count() == 0  # AI close-out owns it now
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    stored["waiting_on"] = "owner"  # AI re-asks: back to the owner
    stores.inbox.put(record["id"], stored)
    assert stores.attention_inbox_count() == 1
    stores.create_inbox_task(title="work", body="b", task_type="task", assignee="agent")
    assert stores.attention_inbox_count() == 1


def test_answer_queues_ai_closeout_once(stores) -> None:
    record = stores.create_inbox_task(
        title="Q?", body="b", task_type="decision", options=["A", "B"], assignee="owner"
    )
    stores.answer_inbox_task(record["id"], answer="", option_index=0)
    stored = stores.inbox.get(record["id"])
    assert stored is not None
    assert stored["waiting_on"] == "agent"
    closeout_id = (stored.get("metadata") or {}).get("closeout_id")
    assert closeout_id
    closeout = stores.inbox.get(closeout_id)
    assert closeout is not None
    assert closeout["assignee"] == "agent"
    assert closeout["status"] == "open"
    assert "A" in (closeout.get("body") or "")
    stores.answer_inbox_task(record["id"], answer="changed")
    items, _ = stores.inbox.list(limit=100)
    assert sum(1 for i in items if (i.get("title") or "").startswith("Close out:")) == 1


def test_followup_close_with_owner_wait_badges_agent_thread(stores) -> None:
    record = stores.create_inbox_task(title="work", body="b", task_type="task", assignee="agent")
    assert stores.attention_inbox_count() == 0
    stores.close_inbox_task(
        record["id"],
        resolution="needs owner choice",
        resolution_kind="followup",
        waiting_on="owner",
    )
    assert stores.attention_inbox_count() == 1
    plain = stores.create_inbox_task(title="work2", body="b", task_type="task", assignee="agent")
    stores.close_inbox_task(
        plain["id"], resolution="agent will continue", resolution_kind="followup"
    )
    assert stores.attention_inbox_count() == 1  # agent-owned follow-up stays quiet


def test_followup_waiting_on_validated(stores) -> None:
    record = stores.create_inbox_task(title="work", body="b", task_type="task", assignee="agent")
    with pytest.raises(StoreError):
        stores.close_inbox_task(
            record["id"], resolution="x", resolution_kind="final", waiting_on="owner"
        )
    with pytest.raises(StoreError):
        stores.close_inbox_task(
            record["id"], resolution="x", resolution_kind="followup", waiting_on="crowd"
        )


def test_attention_e2e_counts_open_only_not_drafts(stores) -> None:
    items = [{"id": "a", "behavior": "b", "kind": "behavior", "area": "dashboard"}]
    open_task = stores.create_e2e_task(merge_commit="aaa", title="open", items=items)
    assert open_task["status"] == "open"
    draft_task = stores.create_e2e_task(merge_commit="bbb", title="draft", items=items, draft=True)
    assert draft_task["status"] == "draft"
    assert stores.attention_e2e_count() == 1
    assert stores.open_e2e_count() == 1


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


def test_idea_count_includes_stale_reviewing(stores) -> None:
    from datetime import UTC, datetime, timedelta

    fresh = stores.create_idea(title="fresh", body="b", source="owner")
    stores.set_idea_status(fresh["id"], status="reviewing")
    assert stores.new_idea_count() == 0
    old = stores.create_idea(title="old", body="b", source="owner")
    record = stores.ideas.get(old["id"])
    record["created_at"] = (datetime.now(UTC) - timedelta(days=9)).isoformat()
    record["status"] = "reviewing"
    stores.ideas.put(old["id"], record)
    assert stores.new_idea_count() == 1


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


def _pointer_draft(stores):
    return stores.create_e2e_task(
        merge_commit="abc123",
        title="t",
        items=[
            {
                "id": "behavior:dashboard",
                "kind": "behavior",
                "area": "dashboard",
                "status": "pending",
                "steps": [{"action": "x", "expected": "y", "grounded": False}],
                "needs_pointers": True,
            }
        ],
        draft=True,
    )


def _pointer_run(stores, task_id, *, status, summary):
    run_id = "run-pointer-1"
    stores.runs.put(
        run_id,
        {
            "id": run_id,
            "title": "E2E pointers: abc123",
            "status": status,
            "approval_mode": "e2e-followup",
            "metadata": {
                "kind": "e2e-pointers",
                "task_id": task_id,
                "merge": "abc123",
                "unclear": [
                    {
                        "id": "behavior:dashboard",
                        "behavior": "dashboard views and actions",
                        "what": ["sub"],
                        "files": ["apps/workbench_dashboard/web/app.js"],
                    },
                    {
                        "id": "behavior:agent-cli",
                        "behavior": "CLI agent runs and chat",
                        "what": ["sub"],
                        "files": ["packages/ai_agent/src/ai_agent/loop.py"],
                    },
                ],
            },
            "receipts": [{"status": "completed", "summary": summary}],
        },
    )
    return run_id


def test_pointer_run_completed_finalizes_task(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    steps = {"behavior:dashboard": [{"action": "Open X", "expected": "Y renders"}]}
    import json

    _pointer_run(stores, task["id"], status="completed", summary=f"STEPS:{json.dumps(steps)}")
    outcomes = route_pointer_runs(stores)
    assert outcomes == [{"run_id": "run-pointer-1", "action": "finalized", "task_id": task["id"]}]
    assert stores.e2e_tasks.get(task["id"])["status"] == "open"
    assert stores.attention_inbox_count() == 0


def test_pointer_run_first_decline_requeues_once(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    _pointer_run(stores, task["id"], status="completed", summary="DECLINE: needs human eyes")
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "requeued"
    assert stores.e2e_tasks.get(task["id"])["status"] == "draft"
    assert stores.attention_inbox_count() == 0
    retry = stores.runs.get(outcomes[0]["retry_run_id"])
    assert retry is not None
    assert retry["metadata"]["attempt"] == 1
    assert "needs human eyes" in retry["body"]


def test_pointer_run_second_decline_escalates_with_reason(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    run_id = _pointer_run(stores, task["id"], status="completed", summary="DECLINE: x")
    run = stores.runs.get(run_id)
    assert run is not None
    run["metadata"]["attempt"] = 1
    stores.runs.put(run_id, run)
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "escalated"
    items, _ = stores.inbox.list(limit=10)
    assert any("Agent decline reason: x" in (i.get("body") or "") for i in items)
    assert stores.attention_inbox_count() == 1


def test_owner_pointers_deduped_per_merge(stores) -> None:
    from e2e_promotion import file_owner_pointers

    first = file_owner_pointers(stores, "abc123", [])
    second = file_owner_pointers(stores, "abc123", [])
    assert first["id"] == second["id"]
    items, _ = stores.inbox.list(limit=100)
    assert sum(1 for i in items if i.get("title") == "E2E pointers needed: abc123") == 1


def test_pointer_run_failed_files_owner_item(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    _pointer_run(stores, task["id"], status="failed", summary="")
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "escalated"
    assert stores.attention_inbox_count() == 1


def test_pointer_router_skips_routed_and_running(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    run_id = _pointer_run(stores, task["id"], status="completed", summary="DECLINE: x")
    first = route_pointer_runs(stores)
    assert len(first) == 1
    assert first[0]["action"] == "requeued"
    assert route_pointer_runs(stores) == []
    run = stores.runs.get(run_id)
    assert run["metadata"]["routed"] == "requeued"


def test_pointer_router_stale_when_task_gone(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    _pointer_run(stores, task["id"], status="completed", summary="DECLINE: x")
    stores.e2e_tasks.delete(task["id"])
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "stale"
    assert stores.attention_inbox_count() == 0


def test_backlog_gate_manual_promotes_to_agent_task(stores) -> None:
    item = stores.create_backlog_item(
        title="Probe X",
        body="plan",
        gate={"kind": "manual", "condition": "owner says go"},
        task_spec={"title": "Probe X now", "body": "do it"},
    )
    assert item["gate"]["kind"] == "manual"
    result = stores.promote_backlog_to_task(item["id"])
    assert result["item"]["status"] == "doing"
    task = stores.inbox.get(result["item"]["inbox_id"])
    assert task["assignee"] == "agent" and task["status"] == "open"
    assert task["title"] == "Probe X now"


def test_backlog_gate_date_and_decision(stores) -> None:
    future = stores.create_backlog_item(
        title="F",
        body="b",
        gate={"kind": "date", "not_before": "2999-01-01T00:00:00+00:00"},
        task_spec={"title": "t", "body": "b"},
    )
    with pytest.raises(StoreError, match="gate closed"):
        stores.promote_backlog_to_task(future["id"])
    past = stores.create_backlog_item(
        title="P",
        body="b",
        gate={"kind": "date", "not_before": "2020-01-01T00:00:00+00:00"},
        task_spec={"title": "t", "body": "b"},
    )
    promoted = stores.promote_open_backlog()
    assert [p["id"] for p in promoted] == [past["id"]]
    assert stores.backlog.get(past["id"])["status"] == "doing"
    assert stores.backlog.get(future["id"])["status"] == "proposed"


def test_backlog_gate_rejects_bad_gates(stores) -> None:
    with pytest.raises(StoreError, match="gate"):
        stores.create_backlog_item(title="X", body="b", gate={"kind": "nope"})
    with pytest.raises(StoreError, match="gate"):
        stores.create_backlog_item(title="X", body="b", gate={"kind": "date"})
    item = stores.create_backlog_item(title="X", body="b")
    with pytest.raises(StoreError, match="task_spec"):
        stores.promote_backlog_to_task(item["id"])


def test_pointer_file_channel_beats_stdout(tmp_path) -> None:
    from dashboard_stores import DashboardStores
    from e2e_promotion import route_pointer_runs

    stores = DashboardStores(tmp_path / "data")
    task = stores.create_e2e_task(
        merge_commit="abc123",
        title="t",
        items=[
            {
                "id": "behavior:dashboard",
                "kind": "behavior",
                "area": "dashboard",
                "status": "pending",
                "steps": [{"action": "x", "expected": "y", "grounded": False}],
                "needs_pointers": True,
            }
        ],
        draft=True,
    )
    worktree = tmp_path / "wt"
    worktree.mkdir()
    import json

    steps = {"behavior:dashboard": [{"action": "Open X", "expected": "Y renders"}]}
    (worktree / "pointers.json").write_text(json.dumps(steps), encoding="utf-8")
    stores.runs.put(
        "run-file",
        {
            "id": "run-file",
            "title": "t",
            "status": "completed",
            "approval_mode": "e2e-followup",
            "metadata": {"kind": "e2e-pointers", "task_id": task["id"], "merge": "abc123"},
            "receipts": [{"status": "completed", "worktree": str(worktree)}],
        },
    )
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "finalized"
    opened = stores.e2e_tasks.get(task["id"])
    assert opened is not None and opened["status"] == "open"


def test_pointer_stdout_fallback_scans_anywhere(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    import json

    steps = {"behavior:dashboard": [{"action": "Open X", "expected": "Y renders"}]}
    body = "## **SUMMARY**\n- Changed: STEPS:" + json.dumps(steps) + "\n"
    _pointer_run(stores, task["id"], status="completed", summary="")
    run = stores.runs.get("run-pointer-1")
    run["receipts"] = [{"status": "completed", "stdout_tail": body}]
    stores.runs.put("run-pointer-1", run)
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "finalized"


def test_open_resolved_draft_opens_only_when_clear(stores) -> None:
    task = _pointer_draft(stores)
    with pytest.raises(StoreError, match="still needs pointers"):
        stores.open_resolved_draft(task["id"])
    record = stores.e2e_tasks.get(task["id"])
    record["items"][0]["needs_pointers"] = False
    stores.e2e_tasks.put(task["id"], record)
    opened = stores.open_resolved_draft(task["id"])
    assert opened["status"] == "open"


def test_pointer_stdout_tolerates_multiline_json(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = _pointer_draft(stores)
    body = 'STEPS:{"behavior:dashboard": [{"action": "Open X\nand Y", "expected": "ok"}]}'
    _pointer_run(stores, task["id"], status="completed", summary="")
    run = stores.runs.get("run-pointer-1")
    run["receipts"] = [{"status": "completed", "stdout_tail": body}]
    stores.runs.put("run-pointer-1", run)
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "finalized"


def test_pointer_partial_verdict_applies_covered_escalates_rest(stores) -> None:
    from e2e_promotion import route_pointer_runs

    task = stores.create_e2e_task(
        merge_commit="abc123",
        title="t",
        items=[
            {
                "id": "behavior:dashboard",
                "kind": "behavior",
                "area": "dashboard",
                "status": "pending",
                "steps": [{"action": "x", "expected": "y", "grounded": False}],
                "needs_pointers": True,
            },
            {
                "id": "behavior:agent-cli",
                "kind": "behavior",
                "area": "agent-cli",
                "status": "pending",
                "steps": [{"action": "x", "expected": "y", "grounded": False}],
                "needs_pointers": True,
            },
        ],
        draft=True,
    )
    import json

    steps = {"behavior:dashboard": [{"action": "Open X", "expected": "Y renders"}]}
    _pointer_run(stores, task["id"], status="completed", summary=f"STEPS:{json.dumps(steps)}")
    outcomes = route_pointer_runs(stores)
    assert outcomes[0]["action"] == "escalated"
    assert outcomes[0].get("partial") is True
    record = stores.e2e_tasks.get(task["id"])
    assert record["status"] == "draft"
    by_id = {item["id"]: item for item in record["items"]}
    assert by_id["behavior:dashboard"]["needs_pointers"] is False
    assert by_id["behavior:agent-cli"]["needs_pointers"] is True
    assert stores.attention_inbox_count() == 1


def test_queue_pointer_run_prefiled_and_runnable(stores) -> None:
    from e2e_promotion import queue_pointer_run

    task = _pointer_draft(stores)
    unclear = [
        {
            "id": "behavior:dashboard",
            "behavior": "dashboard views and actions",
            "what": ["sub"],
            "files": ["apps/workbench_dashboard/web/app.js"],
        }
    ]
    run = queue_pointer_run(stores, "abc123", task["id"], unclear)
    assert run["status"] == "queued"
    assert run["approval_mode"] == "e2e-followup"
    assert run["metadata"]["kind"] == "e2e-pointers"
    assert run["metadata"]["task_id"] == task["id"]
    assert "STEPS:" in run["body"] and "DECLINE:" in run["body"]


def test_related_links_cross_tab_records(stores) -> None:
    inbox_item = stores.create_inbox_task(
        title="Q?", body="b", task_type="task", assignee="agent", project_id="job-search"
    )
    stores.create_inbox_task(title="other", body="b", task_type="task", assignee="agent")
    stores.runs.put(
        "r1", {"id": "r1", "title": "t", "status": "queued", "project_id": "job-search"}
    )
    stores.runs.put("r2", {"id": "r2", "title": "t", "status": "queued"})
    items = [{"id": "a", "behavior": "b", "kind": "behavior", "area": "dashboard"}]
    stores.create_e2e_task(merge_commit="aaa", title="e2e", items=items, project_id="job-search")
    linked = stores.related("job-search")
    assert [i["id"] for i in linked["inbox"]] == [inbox_item["id"]]
    assert [i["id"] for i in linked["runs"]] == ["r1"]
    assert len(linked["e2e_tasks"]) == 1
    assert linked["plans"] == []
    bench = stores.related(stores.default_project_id())
    assert any(i["id"] == "r2" for i in bench["runs"])  # missing id, treated as workbench


def test_backfill_stamps_missing_project_ids(stores) -> None:
    stores.runs.put("r1", {"id": "r1", "title": "t", "status": "queued"})
    stores.runs.put("r2", {"id": "r2", "title": "t", "status": "queued", "project_id": "x"})
    stores.inbox.put("i1", {"id": "i1", "title": "t", "status": "open", "project_id": None})
    filled = stores.backfill_project_ids()
    assert filled == {"plans": 0, "inbox": 1, "runs": 1, "e2e_tasks": 0}
    assert stores.runs.get("r1")["project_id"] == stores.default_project_id()
    assert stores.runs.get("r2")["project_id"] == "x"
    assert stores.inbox.get("i1")["project_id"] == stores.default_project_id()


def test_creators_default_to_workbench_project(stores) -> None:
    item = stores.create_inbox_task(title="Q?", body="b", task_type="task", assignee="agent")
    assert item["project_id"] == stores.default_project_id()
    items = [{"id": "a", "behavior": "b", "kind": "behavior", "area": "dashboard"}]
    task = stores.create_e2e_task(merge_commit="aaa", title="e2e", items=items)
    assert task["project_id"] == stores.default_project_id()


def test_pointer_run_inherits_task_project(stores) -> None:
    from e2e_promotion import queue_pointer_run

    items = [{"id": "a", "behavior": "b", "kind": "behavior", "area": "dashboard"}]
    task = stores.create_e2e_task(
        merge_commit="aaa", title="e2e", items=items, project_id="dashboard"
    )
    run = queue_pointer_run(stores, "aaa", task["id"], [{"id": "a"}])
    assert run["project_id"] == "dashboard"


def test_append_plan_evolution_logs_entries(stores) -> None:
    stores.plans.put(
        "r1",
        {"id": "r1", "title": "R", "status": "active", "kind": "roadmap", "body": "# R\n"},
    )
    stores.append_plan_evolution("r1", "shipped the thing")
    body = stores.plans.get("r1")["body"]
    assert "## Evolutions" in body
    assert "shipped the thing" in body
    stores.append_plan_evolution("r1", "second wave")
    body = stores.plans.get("r1")["body"]
    assert body.count("## Evolutions") == 1
    assert body.index("shipped the thing") < body.index("second wave")
