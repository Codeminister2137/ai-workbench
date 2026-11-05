"""Claim-file run drain against the real JsonCollection store (tmp dirs, no store mocks).

Queued runs use the exact step-2 chat wake-path shapes; approvals use the P6
decision shape. Fixture executors observe calls to prove the approval gate.
"""

import sys
from pathlib import Path

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "apps" / "workbench_dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from ai_agent.run_tracking import request_run_cancel  # noqa: E402
from ai_agent.supervisor_drain import RunDrain  # noqa: E402
from dashboard_stores import DashboardStores  # noqa: E402


@pytest.fixture
def stores(tmp_path):
    return DashboardStores(tmp_path / "data")


@pytest.fixture
def calls():
    return []


@pytest.fixture
def drain(stores, calls):
    def executor(run):
        calls.append(run)
        run["injected_by_executor"] = True
        return {"status": "completed", "summary": "done"}

    return RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=executor,
    )


def _queue_chat_run(stores, run_id="run1", session_id="chat1", answer=None):
    """Mirror the step-2 chat wake-path record shapes exactly."""
    approval = stores.create_inbox_task(
        title="Approve agent run: test",
        body="Chat requested an agent run.",
        task_type="decision",
        task_id=run_id,
        context_refs=[f"run:{run_id}", f"chat:{session_id}"],
        options=["Approve", "Reject"],
    )
    stores.runs.put(
        run_id,
        {
            "id": run_id,
            "title": "test",
            "status": "queued",
            "body": "do it",
            "origin": "chat",
            "session_id": session_id,
            "fanout_policy": "restricted",
            "fanout_effective": "restricted",
            "inbox_id": approval["id"],
            "created_at_utc": "2026-11-05T00:00:00+00:00",
            "updated_at_utc": "2026-11-05T00:00:00+00:00",
        },
    )
    if answer is not None:
        stores.answer_inbox_task(
            approval["id"], answer="", option_index=0 if answer == "Approve" else 1
        )
    return run_id, approval["id"]


def _claim_files(stores):
    return list((stores.data_dir / "runs").glob("*.json.claim"))


def test_approved_run_executes_and_records_receipt(drain, stores, calls) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "completed"}]
    assert [call["id"] for call in calls] == [run_id]
    assert calls[0]["status"] == "running"
    stored = stores.runs.get(run_id)
    assert stored["status"] == "completed"
    assert stored["attempts"] == 1
    assert stored["receipts"] == [{"status": "completed", "summary": "done"}]
    assert [entry["kind"] for entry in stored["events"]] == ["run_started", "run_finished"]
    assert stored["finished_at_utc"]
    assert "injected_by_executor" not in stored
    assert "error" not in stored
    assert _claim_files(stores) == []


def test_open_approval_parks_without_executing(drain, stores, calls) -> None:
    run_id, _inbox_id = _queue_chat_run(stores)
    before = (stores.data_dir / "runs" / f"{run_id}.json").read_bytes()
    outcomes = drain.drain()
    assert outcomes == [
        {
            "run_id": run_id,
            "status": "queued",
            "action": "parked",
            "reason": "awaiting owner approval",
        }
    ]
    assert calls == []
    after = (stores.data_dir / "runs" / f"{run_id}.json").read_bytes()
    assert after == before
    assert _claim_files(stores) == []


def test_rejected_approval_parks(drain, stores, calls) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Reject")
    outcomes = drain.drain()
    assert outcomes[0]["action"] == "parked"
    assert outcomes[0]["reason"] == "owner answered 'Reject'"
    assert calls == []
    assert stores.runs.get(run_id)["status"] == "queued"


def test_closed_without_approval_parks(drain, stores, calls) -> None:
    run_id, inbox_id = _queue_chat_run(stores)
    stores.close_inbox_task(inbox_id)
    outcomes = drain.drain()
    assert outcomes[0]["action"] == "parked"
    assert outcomes[0]["reason"] == "approval is closed"
    assert calls == []


def test_closed_after_approve_executes(drain, stores, calls) -> None:
    """Close is archival: a recorded Approve survives close-before-drain."""
    run_id, inbox_id = _queue_chat_run(stores, answer="Approve")
    stores.close_inbox_task(inbox_id)
    assert stores.inbox.get(inbox_id)["answer"] == "Approve"
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "completed"}]
    assert [call["id"] for call in calls] == [run_id]


def test_broken_approval_link_parks_fail_closed(drain, stores, calls) -> None:
    stores.runs.put("nolink", {"id": "nolink", "title": "t", "status": "queued"})
    stores.runs.put(
        "ghost", {"id": "ghost", "title": "t", "status": "queued", "inbox_id": "0" * 32}
    )
    stores.runs.put("evil", {"id": "evil", "title": "t", "status": "queued", "inbox_id": "../x"})
    outcomes = drain.drain()
    by_id = {outcome["run_id"]: outcome for outcome in outcomes}
    assert by_id["nolink"]["reason"] == "run has no linked inbox approval"
    assert by_id["ghost"]["reason"] == "linked approval not found"
    assert by_id["evil"]["reason"].startswith("approval lookup failed")
    assert all(outcome["action"] == "parked" for outcome in outcomes)
    assert calls == []


def test_terminal_runs_never_replay(drain, stores, calls) -> None:
    for run_id, status in (("c", "completed"), ("f", "failed"), ("x", "cancelled")):
        stores.runs.put(run_id, {"id": run_id, "title": "t", "status": status, "receipts": []})
    before = {
        run_id: (stores.data_dir / "runs" / f"{run_id}.json").read_bytes()
        for run_id in ("c", "f", "x")
    }
    assert drain.drain() == []
    assert calls == []
    for run_id, content in before.items():
        assert (stores.data_dir / "runs" / f"{run_id}.json").read_bytes() == content


def test_executor_failure_marks_failed_once(stores, calls) -> None:
    _queue_chat_run(stores, answer="Approve")

    def boom(run):
        calls.append(run)
        raise RuntimeError("boom")

    drain = RunDrain(runs_dir=stores.data_dir / "runs", get_inbox=stores.inbox.get, executor=boom)
    assert drain.drain() == [{"run_id": "run1", "status": "failed"}]
    stored = stores.runs.get("run1")
    assert stored["status"] == "failed"
    assert stored["error"] == "RuntimeError: boom"
    assert stored["receipts"] == [
        {
            "status": "failed",
            "error": "RuntimeError: boom",
            "source": "drain",
            "at_utc": stored["finished_at_utc"],
        }
    ]
    assert drain.drain() == []
    assert len(calls) == 1
    assert _claim_files(stores) == []


def test_pause_resumes_on_next_drain(stores, calls) -> None:
    _queue_chat_run(stores, answer="Approve")

    def flaky(run):
        calls.append(run)
        if len(calls) == 1:
            return {"status": "paused", "note": "transport wobbled"}
        return {"status": "completed"}

    drain = RunDrain(runs_dir=stores.data_dir / "runs", get_inbox=stores.inbox.get, executor=flaky)
    assert drain.drain() == [{"run_id": "run1", "status": "paused"}]
    assert stores.runs.get("run1")["attempts"] == 1
    assert drain.drain() == [{"run_id": "run1", "status": "completed"}]
    stored = stores.runs.get("run1")
    assert stored["attempts"] == 2
    assert stored["receipts"] == [
        {"status": "paused", "note": "transport wobbled"},
        {"status": "completed"},
    ]
    assert [entry["kind"] for entry in stored["events"]] == [
        "run_started",
        "run_paused",
        "run_started",
        "run_finished",
    ]


def test_bad_receipts_fail_closed(stores, calls) -> None:
    _queue_chat_run(stores, run_id="a-nondict", answer="Approve")
    _queue_chat_run(stores, run_id="b-bogus", answer="Approve")

    def odd(run) -> dict:
        calls.append(run)
        if run["id"] == "a-nondict":
            return "nope"  # type: ignore[return-value]
        return {"status": "bogus"}

    drain = RunDrain(runs_dir=stores.data_dir / "runs", get_inbox=stores.inbox.get, executor=odd)
    outcomes = drain.drain()
    assert outcomes == [
        {"run_id": "a-nondict", "status": "failed"},
        {"run_id": "b-bogus", "status": "failed"},
    ]
    assert "non-dict receipt" in stores.runs.get("a-nondict")["error"]
    assert "Unexpected receipt status: 'bogus'" in stores.runs.get("b-bogus")["error"]


def test_paused_resumes_without_reapproval(drain, stores, calls) -> None:
    run_id, _inbox_id = _queue_chat_run(stores)
    record = stores.runs.get(run_id)
    record["status"] = "paused"
    record["attempts"] = 1
    stores.runs.put(run_id, record)
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "completed"}]
    assert [call["id"] for call in calls] == [run_id]


def test_reconcile_restores_stale_claim(drain, stores, calls) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    path = stores.data_dir / "runs" / f"{run_id}.json"
    path.rename(path.with_suffix(".json.claim"))
    outcomes = drain.reconcile()
    assert outcomes == [{"run_id": run_id, "action": "released", "reason": "stale claim restored"}]
    assert drain.drain() == [{"run_id": run_id, "status": "completed"}]
    assert [call["id"] for call in calls] == [run_id]


def test_reconcile_drops_claim_when_job_exists(drain, stores) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    (stores.data_dir / "runs" / f"{run_id}.json.claim").write_text("{stale", encoding="utf-8")
    assert drain.reconcile() == [{"run_id": run_id, "action": "cleaned"}]
    assert stores.runs.get(run_id)["status"] == "queued"


def test_reconcile_requeues_interrupted_running(drain, stores) -> None:
    stores.runs.put("live", {"id": "live", "title": "t", "status": "running", "attempts": 1})
    stores.runs.put("done", {"id": "done", "title": "t", "status": "completed"})
    outcomes = drain.reconcile()
    assert outcomes == [{"run_id": "live", "action": "requeued"}]
    stored = stores.runs.get("live")
    assert stored["status"] == "queued"
    assert stored["note"] == "Interrupted run reconciled; will resume"
    assert stored["events"][-1]["kind"] == "run_requeued"


def test_cancel_race_marks_cancelled_without_executing(drain, stores, calls) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    record = stores.runs.get(run_id)
    request_run_cancel(record)
    stores.runs.put(run_id, record)
    assert drain.drain() == [{"run_id": run_id, "status": "cancelled"}]
    assert calls == []
    stored = stores.runs.get(run_id)
    assert stored["status"] == "cancelled"
    assert stored["events"][-1]["kind"] == "run_cancelled"
    assert stored["finished_at_utc"]


def test_max_runs_budgets_claims_not_parks(drain, stores, calls) -> None:
    _queue_chat_run(stores, run_id="0-parked")
    _queue_chat_run(stores, run_id="a-one", answer="Approve")
    _queue_chat_run(stores, run_id="b-two", answer="Approve")
    outcomes = drain.drain(max_runs=1)
    assert [outcome["run_id"] for outcome in outcomes] == ["0-parked", "a-one"]
    assert outcomes[0]["action"] == "parked"
    assert outcomes[1]["status"] == "completed"
    assert stores.runs.get("b-two")["status"] == "queued"
    with pytest.raises(ValueError, match="max_runs"):
        drain.drain(max_runs=0)
    with pytest.raises(ValueError, match="max_runs"):
        drain.drain(max_runs=101)


def test_terminal_hook_fires_on_completed(stores, calls) -> None:
    _queue_chat_run(stores, answer="Approve")
    seen: list[dict] = []
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed"},
        on_terminal=seen.append,
    )
    assert drain.drain() == [{"run_id": "run1", "status": "completed"}]
    assert seen == [{"run_id": "run1", "status": "completed", "title": "test", "error": None}]


def test_terminal_hook_fires_on_failed_with_error(stores) -> None:
    _queue_chat_run(stores, answer="Approve")
    seen: list[dict] = []

    def boom(run):
        raise RuntimeError("boom")

    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=boom,
        on_terminal=seen.append,
    )
    assert drain.drain() == [{"run_id": "run1", "status": "failed"}]
    assert seen == [
        {"run_id": "run1", "status": "failed", "title": "test", "error": "RuntimeError: boom"}
    ]


def test_terminal_hook_fires_on_cancelled(stores) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    record = stores.runs.get(run_id)
    request_run_cancel(record)
    stores.runs.put(run_id, record)
    seen: list[dict] = []
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed"},
        on_terminal=seen.append,
    )
    assert drain.drain() == [{"run_id": run_id, "status": "cancelled"}]
    assert [entry["status"] for entry in seen] == ["cancelled"]


def test_terminal_hook_failure_never_breaks_drain(stores) -> None:
    _queue_chat_run(stores, answer="Approve")

    def bad_hook(summary):
        raise RuntimeError("mailer down")

    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed"},
        on_terminal=bad_hook,
    )
    assert drain.drain() == [{"run_id": "run1", "status": "completed"}]
    assert stores.runs.get("run1")["status"] == "completed"


def test_parked_and_paused_runs_do_not_notify(stores) -> None:
    _queue_chat_run(stores, run_id="parked")
    _queue_chat_run(stores, run_id="pauser", answer="Approve")
    seen: list[dict] = []
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "paused"},
        on_terminal=seen.append,
    )
    outcomes = drain.drain()
    assert [outcome["run_id"] for outcome in outcomes] == ["parked", "pauser"]
    assert seen == []
