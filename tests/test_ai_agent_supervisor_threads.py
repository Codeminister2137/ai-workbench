"""Supervisor threads over the real file-backed collections (no store mocks).

Threads and plans live in real ``JsonCollection`` stores under tmp dirs;
executable approval enqueues step-2-shaped runs plus linked inbox decisions
through the real ``DashboardStores`` gates.
"""

import os
import sys
import time
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "apps" / "workbench_dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from ai_agent.supervisor_threads import (  # noqa: E402
    PLAN_APPROVAL_SECONDS,
    SupervisorThreads,
)
from dashboard_stores import DashboardStores, JsonCollection  # noqa: E402


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


@pytest.fixture
def clock():
    return {"t": 1000.0}


@pytest.fixture
def threads(stores, clock):
    return SupervisorThreads(
        threads=JsonCollection(stores.data_dir / "threads"),
        plans=stores.plans,
        runs=stores.runs,
        create_approval=stores.create_inbox_task,
        now=lambda: clock["t"],
    )


def _planned(threads, topic="Build a widget"):
    opened = threads.open_thread(topic)
    threads.post_message(opened["id"], "It must slice bread.")
    return threads.write_plan(opened["id"]), opened["id"]


def test_open_thread_stores_record(threads, stores) -> None:
    opened = threads.open_thread("Build a widget", title="Widget")
    stored = JsonCollection(stores.data_dir / "threads").get(opened["id"])
    assert stored is not None
    assert opened == {"id": opened["id"], "topic": "Build a widget", "status": "open"}
    assert stored["supervisor_thread"] is True
    assert stored["status"] == "open"
    assert stored["history"] == []
    assert stored["title"] == "Widget"


def test_open_thread_validates_topic(threads) -> None:
    with pytest.raises(ValueError, match="topic"):
        threads.open_thread("   ")
    with pytest.raises(ValueError, match="topic"):
        threads.open_thread("x" * 4001)


def test_get_thread_rejects_unknown(threads) -> None:
    with pytest.raises(ValueError, match="Unknown supervisor thread"):
        threads.get_thread("0" * 32)
    with pytest.raises(ValueError, match="Invalid thread identifier"):
        threads.get_thread("../evil")


def test_post_message_appends_scripted_turn(threads) -> None:
    opened = threads.open_thread("Build a widget")
    first = threads.post_message(opened["id"], "It must slice bread.")
    assert first["route"] == "scripted"
    assert "SCRIPTED" in first["reply"]
    assert "message 1" in first["reply"]
    second = threads.post_message(opened["id"], "And toast.")
    assert "message 2" in second["reply"]
    history = threads.get_thread(opened["id"])["history"]
    assert [turn["role"] for turn in history] == ["user", "assistant", "user", "assistant"]


def test_post_message_accepts_host_reply(stores, clock) -> None:
    threads = SupervisorThreads(
        threads=JsonCollection(stores.data_dir / "threads"),
        plans=stores.plans,
        reply_fn=lambda thread: f"host saw {len(thread['history'])} turns",
        now=lambda: clock["t"],
    )
    opened = threads.open_thread("Build a widget")
    posted = threads.post_message(opened["id"], "Hello?")
    assert posted == {"reply": "host saw 1 turns", "route": "host"}


def test_post_message_closed_once_planned(threads) -> None:
    _plan, thread_id = _planned(threads)
    with pytest.raises(ValueError, match="closed to new messages"):
        threads.post_message(thread_id, "One more thing.")


def test_list_threads_newest_first(stores, threads) -> None:
    first = threads.open_thread("First")
    threads.post_message(first["id"], "requirements one")
    first_path = stores.data_dir / "threads" / f"{first['id']}.json"
    old = time.time() - 3600
    os.utime(first_path, (old, old))
    second = threads.open_thread("Second")
    assert [item["id"] for item in threads.list_threads()] == [second["id"], first["id"]]
    assert threads.list_threads()[0]["topic"] == "Second"
    with pytest.raises(ValueError, match="limit"):
        threads.list_threads(limit=0)


def test_write_plan_publishes_proposed_plan(threads, stores) -> None:
    opened = threads.open_thread("Build a widget")
    threads.post_message(opened["id"], "It must slice bread.")
    plan = threads.write_plan(opened["id"], title="Widget plan")
    assert plan["expires"] == 1000.0 + PLAN_APPROVAL_SECONDS
    assert len(plan["nonce"]) == 32
    assert plan["markdown"].startswith("# Plan: Build a widget")
    assert "1. It must slice bread." in plan["markdown"]
    record = stores.plans.get(plan["plan_id"])
    assert record["status"] == "proposed"
    assert record["body"] == plan["markdown"]
    assert record["thread_id"] == opened["id"]
    assert record["title"] == "Widget plan"
    assert threads.get_thread(opened["id"])["status"] == "planned"


def test_write_plan_needs_requirements(threads) -> None:
    opened = threads.open_thread("Empty")
    with pytest.raises(ValueError, match="no requirements"):
        threads.write_plan(opened["id"])


def test_write_plan_refuses_double_pending(threads, clock) -> None:
    _plan, thread_id = _planned(threads)
    with pytest.raises(ValueError, match="already pending"):
        threads.write_plan(thread_id)
    clock["t"] += PLAN_APPROVAL_SECONDS + 1
    fresh = threads.write_plan(thread_id)
    assert fresh["expires"] == clock["t"] + PLAN_APPROVAL_SECONDS


def test_approve_rejects_bad_nonce_and_expiry(threads, clock) -> None:
    plan, thread_id = _planned(threads)
    with pytest.raises(ValueError, match="Invalid or expired"):
        threads.approve_plan(thread_id, "f" * 32)
    with pytest.raises(ValueError, match="Invalid or expired"):
        threads.approve_plan(thread_id, " Héllo ")
    clock["t"] += PLAN_APPROVAL_SECONDS + 1
    with pytest.raises(ValueError, match="Invalid or expired"):
        threads.approve_plan(thread_id, plan["nonce"])


def test_approve_rejects_tampered_plan(threads, stores) -> None:
    plan, thread_id = _planned(threads)
    record = stores.plans.get(plan["plan_id"])
    record["body"] += "\n- sneaked in after review"
    stores.plans.put(plan["plan_id"], record)
    with pytest.raises(ValueError, match="Reviewed plan changed"):
        threads.approve_plan(thread_id, plan["nonce"])
    assert threads.get_thread(thread_id)["status"] == "open"
    assert stores.plans.get(plan["plan_id"])["status"] == "invalidated"
    # A fresh review cycle recovers.
    threads.write_plan(thread_id)


def test_approve_validates_execute_flag(threads) -> None:
    plan, thread_id = _planned(threads)
    with pytest.raises(ValueError, match="execute must be"):
        threads.approve_plan(thread_id, plan["nonce"], execute="yes")  # type: ignore[arg-type]


def test_approve_without_pending_fails(threads) -> None:
    opened = threads.open_thread("Nothing planned")
    with pytest.raises(ValueError, match="No pending plan approval"):
        threads.approve_plan(opened["id"], "0" * 32)


def test_approve_honours_cancellation_hook(stores, clock) -> None:
    threads = SupervisorThreads(
        threads=JsonCollection(stores.data_dir / "threads"),
        plans=stores.plans,
        is_cancelled=lambda thread_id: True,
        now=lambda: clock["t"],
    )
    opened = threads.open_thread("Build a widget")
    threads.post_message(opened["id"], "It must slice bread.")
    plan = threads.write_plan(opened["id"])
    with pytest.raises(ValueError, match="Cancellation invalidated"):
        threads.approve_plan(opened["id"], plan["nonce"], execute=False)


def test_planning_only_approval_queues_nothing(threads, stores) -> None:
    plan, thread_id = _planned(threads)
    outcome = threads.approve_plan(thread_id, plan["nonce"], execute=False)
    assert outcome == {"plan_id": plan["plan_id"], "run_id": None, "status": "approved"}
    assert stores.plans.get(plan["plan_id"])["status"] == "approved"
    assert threads.get_thread(thread_id)["status"] == "approved"
    assert stores.runs.list()[1] == 0
    assert stores.inbox.list()[1] == 0
    with pytest.raises(ValueError, match="No pending plan approval"):
        threads.approve_plan(thread_id, plan["nonce"], execute=False)
    with pytest.raises(ValueError, match="closed to new plans"):
        threads.write_plan(thread_id)


def test_executable_approval_enqueues_gated_run(threads, stores) -> None:
    plan, thread_id = _planned(threads)
    outcome = threads.approve_plan(thread_id, plan["nonce"], execute=True)
    assert outcome["status"] == "queued"
    run = stores.runs.get(outcome["run_id"])
    assert run["status"] == "queued"
    assert run["origin"] == "plan"
    assert run["plan_id"] == plan["plan_id"]
    assert run["thread_id"] == thread_id
    assert run["plan_digest"] == plan["digest"]
    assert run["fanout_policy"] == "restricted"
    assert run["fanout_effective"] == "restricted"
    assert run["inbox_id"] == outcome["inbox_id"]
    assert run["body_truncated"] is False
    approval = stores.inbox.get(outcome["inbox_id"])
    assert approval["type"] == "decision"
    assert approval["options"] == ["Approve", "Reject"]
    assert approval["task_id"] == outcome["run_id"]
    assert approval["status"] == "open"
    assert stores.plans.get(plan["plan_id"])["status"] == "approved"


def test_executable_approval_truncates_long_body(threads, stores) -> None:
    opened = threads.open_thread("Big plan")
    threads.post_message(opened["id"], "x" * 4000)
    plan = threads.write_plan(opened["id"])
    outcome = threads.approve_plan(opened["id"], plan["nonce"], execute=True)
    run = stores.runs.get(outcome["run_id"])
    assert len(run["body"]) == 4000
    assert run["body_truncated"] is True


def test_executable_approval_validates_fanout(threads, stores) -> None:
    plan, thread_id = _planned(threads)
    with pytest.raises(ValueError, match="Unknown fan-out policy"):
        threads.approve_plan(thread_id, plan["nonce"], execute=True, fanout_policy="maybe")
    assert threads.get_thread(thread_id)["status"] == "planned"
    assert stores.plans.get(plan["plan_id"])["status"] == "proposed"


def test_executable_approval_needs_sinks(stores, clock) -> None:
    threads = SupervisorThreads(
        threads=JsonCollection(stores.data_dir / "threads"),
        plans=stores.plans,
        now=lambda: clock["t"],
    )
    plan, thread_id = _planned(threads)
    with pytest.raises(ValueError, match="runs and inbox sinks"):
        threads.approve_plan(thread_id, plan["nonce"], execute=True)
