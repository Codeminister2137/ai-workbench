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
    stores.close_inbox_task(inbox_id, resolution="Withdrawn.")
    outcomes = drain.drain()
    assert outcomes[0]["action"] == "parked"
    assert outcomes[0]["reason"] == "approval is closed"
    assert calls == []


def test_closed_after_approve_executes(drain, stores, calls) -> None:
    """Close is archival: a recorded Approve survives close-before-drain."""
    run_id, inbox_id = _queue_chat_run(stores, answer="Approve")
    stores.close_inbox_task(inbox_id, resolution="Approved then archived.")
    assert stores.inbox.get(inbox_id)["answer"] == "Approve"
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "completed"}]
    assert [call["id"] for call in calls] == [run_id]


@pytest.mark.parametrize("mode", [None, "owner-filed", "e2e-followup", "agent-queue"])
@pytest.mark.parametrize("link", ["inbox_id", "bridged_from"])
@pytest.mark.parametrize("status", ["open", "answered", "closed"])
@pytest.mark.parametrize("answer", [None, "", "Approve", "Schedule it", "Reject", "Use option B"])
def test_approval_mode_status_answer_matrix(drain, stores, calls, mode, link, status, answer):
    """Completed tasks park; recorded decisions remain available for close-out."""
    run_id, inbox_id = _queue_chat_run(stores)
    item = stores.inbox.get(inbox_id)
    item.update(status=status, answer=answer)
    stores.inbox.put(inbox_id, item)
    run = stores.runs.get(run_id)
    run["approval_mode"] = mode
    run["inbox_id"] = None
    run[link] = inbox_id
    stores.runs.put(run_id, run)
    path = stores.data_dir / "runs" / f"{run_id}.json"
    before = path.read_bytes()

    allowed = (
        not (status == "closed" and not answer)
        if mode is not None
        else status in {"answered", "closed"} and answer in {"Approve", "Schedule it"}
    )
    outcomes = drain.drain()
    if allowed:
        assert outcomes == [{"run_id": run_id, "status": "completed"}]
        assert [call["id"] for call in calls] == [run_id]
    else:
        assert outcomes[0]["action"] == "parked"
        assert calls == []
        assert path.read_bytes() == before
        assert stores.runs.get(run_id)["status"] == "queued"
    assert _claim_files(stores) == []


@pytest.mark.parametrize("mode", ["owner-filed", "e2e-followup", "agent-queue"])
def test_bridged_close_between_scan_and_pickup_parks(drain, stores, calls, monkeypatch, mode):
    run_id, inbox_id = _queue_chat_run(stores)
    run = stores.runs.get(run_id)
    run.update(inbox_id=None, bridged_from=inbox_id, approval_mode=mode)
    path = stores.runs.put(run_id, run)
    before = path.read_bytes()
    pickup = drain._run_claimed

    def close_then_pickup(path):
        item = stores.inbox.get(inbox_id)
        item.update(status="closed", answer=None)
        stores.inbox.put(inbox_id, item)
        return pickup(path)

    monkeypatch.setattr(drain, "_run_claimed", close_then_pickup)
    outcomes = drain.drain()
    assert outcomes == [
        {"run_id": run_id, "status": "queued", "action": "parked", "reason": "approval is closed"}
    ]
    assert calls == []
    assert path.read_bytes() == before
    assert _claim_files(stores) == []


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
        return {"status": "completed", "summary": "resumed and done"}

    drain = RunDrain(runs_dir=stores.data_dir / "runs", get_inbox=stores.inbox.get, executor=flaky)
    assert drain.drain() == [{"run_id": "run1", "status": "paused"}]
    assert stores.runs.get("run1")["attempts"] == 1
    assert drain.drain() == [{"run_id": "run1", "status": "completed"}]
    stored = stores.runs.get("run1")
    assert stored["attempts"] == 2
    assert stored["receipts"] == [
        {"status": "paused", "note": "transport wobbled"},
        {"status": "completed", "summary": "resumed and done"},
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


def test_reconcile_epoch_skips_live_worker(stores) -> None:
    epoch = "2026-11-14T11:00:00+00:00"
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed"},
        worker_epoch=epoch,
    )
    stores.runs.put(
        "live", {"id": "live", "title": "t", "status": "running", "worker_epoch": epoch}
    )
    stores.runs.put(
        "dead", {"id": "dead", "title": "t", "status": "running", "worker_epoch": "old"}
    )
    stores.runs.put("legacy", {"id": "legacy", "title": "t", "status": "running"})
    outcomes = drain.reconcile(epoch)
    assert outcomes == [
        {"run_id": "dead", "action": "requeued"},
        {"run_id": "legacy", "action": "requeued"},
        {"run_id": "live", "action": "skipped", "reason": "live worker epoch"},
    ]
    assert stores.runs.get("live")["status"] == "running"
    assert stores.runs.get("dead")["status"] == "queued"
    event = stores.runs.get("dead")["events"][-1]
    assert event["kind"] == "run_requeued"
    assert event["payload"]["worker_epoch"] == "old"
    assert event["payload"]["reconciled_by_epoch"] == epoch


def test_drain_stamps_worker_epoch(stores) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    seen: dict = {}
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: seen.update(run) or {"status": "completed", "summary": "stamped"},
        worker_epoch="epoch-1",
    )
    assert drain.drain() == [{"run_id": run_id, "status": "completed"}]
    assert seen["worker_epoch"] == "epoch-1"


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


def test_cancelled_run_reaches_terminal_despite_rejection(drain, stores, calls) -> None:
    """Cancellation wins over approval gating; rejected+cancelled never parks."""
    run_id, _inbox_id = _queue_chat_run(stores, answer="Reject")
    record = stores.runs.get(run_id)
    request_run_cancel(record)
    stores.runs.put(run_id, record)
    assert drain.drain() == [{"run_id": run_id, "status": "cancelled"}]
    assert calls == []
    assert stores.runs.get(run_id)["status"] == "cancelled"


def test_drain_runs_oldest_first_not_filename_order(drain, stores, calls) -> None:
    _queue_chat_run(stores, run_id="z-newer", answer="Approve")
    _queue_chat_run(stores, run_id="a-older", answer="Approve")
    newer = stores.runs.get("z-newer")
    older = stores.runs.get("a-older")
    assert newer is not None and older is not None
    newer["created_at_utc"] = "2026-11-06T00:00:00+00:00"
    older["created_at_utc"] = "2026-11-05T00:00:00+00:00"
    stores.runs.put("z-newer", newer)
    stores.runs.put("a-older", older)
    outcomes = drain.drain(max_runs=1)
    assert [outcome["run_id"] for outcome in outcomes] == ["a-older"]
    assert [call["id"] for call in calls] == ["a-older"]


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
        executor=lambda run: {"status": "completed", "summary": "done"},
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
        executor=lambda run: {"status": "completed", "summary": "done"},
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


def test_receipt_staged_copies_to_run_record(stores) -> None:
    _queue_chat_run(stores, answer="Approve")
    staged = [{"relpath": "a.py", "content": "x", "digest": "d", "base_digest": None}]
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed", "staged": staged},
    )
    assert drain.drain() == [{"run_id": "run1", "status": "completed"}]
    assert stores.runs.get("run1")["staged"] == staged


def test_non_list_staged_ignored(stores) -> None:
    _queue_chat_run(stores, answer="Approve")
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed", "summary": "done", "staged": "bogus"},
    )
    assert drain.drain() == [{"run_id": "run1", "status": "completed"}]
    assert "staged" not in stores.runs.get("run1")


def test_owner_filed_run_executes_without_approval(drain, stores, calls) -> None:
    """Bridge pre-approval: filing is approval, no linked decision needed."""
    stores.runs.put(
        "own1",
        {
            "id": "own1",
            "title": "owner task",
            "status": "queued",
            "body": "do it",
            "origin": "inbox",
            "inbox_id": None,
            "approval_mode": "owner-filed",
            "created_at_utc": "2026-11-05T00:00:00+00:00",
            "updated_at_utc": "2026-11-05T00:00:00+00:00",
        },
    )
    assert drain.drain() == [{"run_id": "own1", "status": "completed"}]
    assert [call["id"] for call in calls] == ["own1"]
    assert stores.runs.get("own1")["status"] == "completed"


def _note_hook(stores, posted):
    def hook(inbox_id, note):
        posted.append((inbox_id, note))
        item = stores.inbox.get(inbox_id)
        item["notes"] = (item.get("notes") or "") + note
        stores.inbox.put(inbox_id, item)

    return hook


def test_hollow_completed_run_escalates(stores) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda _run: {"status": "completed"},
    )
    assert drain.drain() == [{"run_id": run_id, "status": "needs-attention"}]
    stored = stores.runs.get(run_id)
    assert stored["status"] == "needs-attention"
    assert "hollow" in (stored.get("error") or "").lower()


def test_completed_run_posts_findings_to_linked_inbox(stores) -> None:
    posted: list = []
    run_id, inbox_id = _queue_chat_run(stores, answer="Approve")
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda _run: {"status": "completed", "summary": "found three names"},
        inbox_note=_note_hook(stores, posted),
    )
    assert drain.drain() == [{"run_id": run_id, "status": "completed"}]
    assert len(posted) == 1
    assert posted[0][0] == inbox_id
    assert "test" in posted[0][1]  # human-readable run title, not a bare id
    assert "found three names" in posted[0][1]
    assert "found three names" in (stores.inbox.get(inbox_id).get("notes") or "")


def test_writeback_failure_escalates(stores) -> None:
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")

    def boom(_inbox_id, _note):
        raise RuntimeError("store down")

    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda _run: {"status": "completed", "summary": "done"},
        inbox_note=boom,
    )
    assert drain.drain() == [{"run_id": run_id, "status": "needs-attention"}]
    assert "write-back" in (stores.runs.get(run_id).get("error") or "").lower()


def test_unlinked_substance_run_completes_without_hook(stores) -> None:
    posted: list = []
    stores.runs.put(
        "own2",
        {
            "id": "own2",
            "title": "owner task",
            "status": "queued",
            "body": "do it",
            "origin": "inbox",
            "inbox_id": None,
            "approval_mode": "owner-filed",
            "created_at_utc": "2026-11-05T00:00:00+00:00",
            "updated_at_utc": "2026-11-05T00:00:00+00:00",
        },
    )
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda _run: {"status": "completed", "summary": "done"},
        inbox_note=_note_hook(stores, posted),
    )
    assert drain.drain() == [{"run_id": "own2", "status": "completed"}]
    assert posted == []


def _interrupted(stores, run_id="stuck1", **overrides):
    record = {"id": run_id, "title": "t", "status": "running", "attempts": 1}
    record.update(overrides)
    stores.runs.put(run_id, record)


def _capped_drain(stores, terminal, evidence):
    return RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed"},
        on_terminal=lambda summary: terminal.append(summary),
        output_evidence=evidence,
    )


def test_reconcile_cancels_twice_interrupted_without_output(stores) -> None:
    terminal: list = []
    drain = _capped_drain(stores, terminal, lambda _run_id: False)
    _interrupted(stores)
    assert drain.reconcile() == [{"run_id": "stuck1", "action": "requeued"}]
    stored = stores.runs.get("stuck1")
    stored["status"] = "running"
    stores.runs.put("stuck1", stored)
    assert drain.reconcile() == [
        {"run_id": "stuck1", "action": "cancelled", "reason": "no output evidence"}
    ]
    cancelled = stores.runs.get("stuck1")
    assert cancelled["status"] == "cancelled"
    assert "cancelled by supervisor" in cancelled["error"]
    assert cancelled["events"][-1]["kind"] == "run_cancelled"
    assert terminal == [
        {"run_id": "stuck1", "status": "cancelled", "title": "t", "error": cancelled["error"]}
    ]


def test_reconcile_requeues_when_output_evidence_exists(stores) -> None:
    drain = _capped_drain(stores, [], lambda _run_id: True)
    _interrupted(stores, interruptions=1)
    assert drain.reconcile() == [{"run_id": "stuck1", "action": "requeued"}]
    assert stores.runs.get("stuck1")["status"] == "queued"


def test_reconcile_receipt_output_counts_as_evidence(stores) -> None:
    drain = _capped_drain(stores, [], lambda _run_id: False)
    _interrupted(
        stores,
        interruptions=1,
        receipts=[{"status": "failed", "stdout_tail": "partial work"}],
    )
    assert drain.reconcile() == [{"run_id": "stuck1", "action": "requeued"}]


def test_reconcile_without_callback_requeues_forever(stores) -> None:
    drain = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=lambda run: {"status": "completed"},
    )
    _interrupted(stores)
    assert drain.reconcile() == [{"run_id": "stuck1", "action": "requeued"}]
    stored = stores.runs.get("stuck1")
    stored["status"] = "running"
    stores.runs.put("stuck1", stored)
    assert drain.reconcile() == [{"run_id": "stuck1", "action": "requeued"}]


def test_reconcile_hard_cap_breaks_crash_loops(stores) -> None:
    drain = _capped_drain(stores, [], lambda _run_id: True)
    _interrupted(stores, interruptions=4)
    assert drain.reconcile() == [
        {"run_id": "stuck1", "action": "cancelled", "reason": "interrupted repeatedly"}
    ]


def _shipping_drain(stores, shipper):
    def executor(run):
        return {"status": "completed", "summary": "done"}

    return RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=executor,
        ship_completed=shipper,
    )


def test_shipper_records_shipment_on_completed(stores) -> None:
    seen = []
    drain = _shipping_drain(stores, lambda run: seen.append(run["id"]) or {"committed": True})
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "completed"}]
    assert seen == [run_id]
    assert stores.runs.get(run_id)["shipment"] == {"committed": True}


def test_shipper_failure_escalates_to_attention(stores) -> None:
    def boom(run):
        raise RuntimeError("git gone")

    drain = _shipping_drain(stores, boom)
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "needs-attention"}]
    stored = stores.runs.get(run_id)
    assert "completion ship failed" in stored["error"]


def test_shipper_uncommitted_report_escalates(stores) -> None:
    drain = _shipping_drain(stores, lambda run: {"committed": False, "error": "dirty"})
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    outcomes = drain.drain()
    assert outcomes == [{"run_id": run_id, "status": "needs-attention"}]


@pytest.mark.parametrize("holder", ["agent", "dashboard"])
def test_wake_idle_lock_compatibility(stores, holder):
    """Independent implementations exclude each other on the same lock byte."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from ai_agent.wake_idle_lock import interlock as agent_lock
    from wake_idle import interlock as dashboard_lock

    first, second = (agent_lock, dashboard_lock)
    if holder == "dashboard":
        first, second = second, first
    attempted, acquired = Event(), Event()

    def contend():
        attempted.set()
        with second(stores.data_dir):
            acquired.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with first(stores.data_dir):
            future = pool.submit(contend)
            assert attempted.wait(2)
            assert not acquired.wait(0.15)
        future.result(timeout=3)
    assert acquired.is_set()
    assert (stores.data_dir / "wake-idle.lock").read_bytes()[:1] == b"0"


@pytest.mark.parametrize("operation", ["claim", "release", "restore", "requeue", "publish"])
def test_drain_mutations_serialize_with_sleep_commit(stores, operation):
    """Once the final-check lock is held, no drain mutation can cross it."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from threading import Event

    from wake_idle import interlock

    path = stores.data_dir / "runs" / "race.json"
    claim = path.with_suffix(".json.claim")
    record = {"id": "race", "status": "queued", "approval_mode": "owner-filed"}
    stores.runs.put("race", record)
    attempted, executed = Event(), Event()

    def execute(_run):
        # Lock must be available throughout execution, including to other modules.
        with interlock(stores.data_dir):
            executed.set()
        return {"status": "completed", "summary": "done"}

    worker = RunDrain(runs_dir=path.parent, get_inbox=lambda _: None, executor=execute)
    if operation in {"release", "restore", "publish"}:
        path.rename(claim)
    if operation == "requeue":
        stores.runs.put("race", {**record, "status": "running"})
    cancel = stores.data_dir / "wake-idle.cancel"
    cancel.unlink(missing_ok=True)
    before = (path.read_bytes() if path.exists() else None, claim.exists())

    def mutate():
        attempted.set()
        if operation == "claim":
            return worker._run_claimed(path)
        if operation == "release":
            return worker._release(path, claim)
        if operation == "publish":
            return worker._publish(path, claim, record)
        return worker.reconcile()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with interlock(stores.data_dir):
            future = pool.submit(mutate)
            assert attempted.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.15)
            assert not cancel.exists()
            assert (path.read_bytes() if path.exists() else None, claim.exists()) == before
        future.result(timeout=5)
    assert cancel.exists()
    if operation == "claim":
        assert executed.is_set()


def test_claim_before_final_check_cancels_sleep_even_after_fast_completion(stores):
    """A claim in the handoff window invalidates sleep even if its blocker disappears."""
    from concurrent.futures import ThreadPoolExecutor

    from wake_idle import final_check, interlock

    stores.data_dir.mkdir(parents=True, exist_ok=True)
    config = stores.data_dir / "config.json"
    config.write_text('{"supervision":"unattended"}', encoding="utf-8")
    path = stores.data_dir / "runs" / "race.json"
    # A paused run is not itself an idle blocker; claiming it must invalidate sleep.
    stores.runs.put("race", {"id": "race", "status": "paused"})
    (stores.data_dir / "wake-idle.cancel").unlink(missing_ok=True)
    worker = RunDrain(
        runs_dir=path.parent,
        get_inbox=lambda _: None,
        executor=lambda _: {"status": "paused"},
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(worker._run_claimed, path).result(timeout=5)
    assert not path.with_suffix(".json.claim").exists()
    assert stores.runs.get("race")["status"] == "paused"
    with interlock(stores.data_dir):
        assert final_check(stores.data_dir, config) != 0


def _exhausting_drain(stores, calls):
    def executor(run):
        calls.append(run)
        return {
            "status": "failed",
            "error": "Mai session exited with code 1",
            "failure_class": "provider",
            "exhausted_tree": True,
        }

    return RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=executor,
    )


def test_exhausted_tree_parks_with_backoff(stores, calls) -> None:
    """Scheduler-A park-on-exhaustion: handoff failure requeues, never fails."""
    from datetime import UTC, datetime

    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    worker = _exhausting_drain(stores, calls)
    (outcome,) = worker.drain()
    assert outcome["status"] == "queued"
    assert outcome["action"] == "parked"
    assert "ripe after" in outcome["reason"]
    stored = stores.runs.get(run_id)
    assert stored["status"] == "queued"
    assert stored["park_count"] == 1
    ripe_at = datetime.fromisoformat(stored["not_before_utc"])
    assert ripe_at > datetime.now(UTC)
    assert "finished_at_utc" not in stored
    assert [entry["kind"] for entry in stored["events"]][-1] == "run_parked"
    assert _claim_files(stores) == []


def test_unripe_parked_run_skips_without_executing(stores, calls) -> None:
    from datetime import UTC, datetime, timedelta

    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    worker = _exhausting_drain(stores, calls)
    worker.drain()
    assert len(calls) == 1
    (outcome,) = worker.drain()
    assert outcome["action"] == "parked"
    assert "parked until" in outcome["reason"]
    assert len(calls) == 1
    # A ripe run executes again.
    stored = stores.runs.get(run_id)
    stored["not_before_utc"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    stores.runs.put(run_id, stored)
    worker.drain()
    assert len(calls) == 2
    assert stores.runs.get(run_id)["park_count"] == 2


def test_repeated_parks_fail_terminal(stores, calls) -> None:
    """Nothing is immortal: past PARK_MAX the run fails with cause."""
    from ai_agent.supervisor_drain import PARK_MAX

    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    worker = _exhausting_drain(stores, calls)
    for _ in range(PARK_MAX + 1):
        stored = stores.runs.get(run_id)
        stored.pop("not_before_utc", None)
        stores.runs.put(run_id, stored)
        worker.drain()
    stored = stores.runs.get(run_id)
    assert stored["status"] == "failed"
    assert "parked repeatedly" in stored["error"]
    assert stored["park_count"] == PARK_MAX


def test_plain_failure_never_parks(stores, calls) -> None:
    def executor(run):
        calls.append(run)
        return {"status": "failed", "error": "genuine task failure"}

    worker = RunDrain(
        runs_dir=stores.data_dir / "runs",
        get_inbox=stores.inbox.get,
        executor=executor,
    )
    run_id, _inbox_id = _queue_chat_run(stores, answer="Approve")
    (outcome,) = worker.drain()
    assert outcome == {"run_id": run_id, "status": "failed"}
    stored = stores.runs.get(run_id)
    assert "park_count" not in stored
    assert "not_before_utc" not in stored
