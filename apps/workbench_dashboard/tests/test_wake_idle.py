"""Idle policy and admission races; never suspend the test machine."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from dashboard_stores import DashboardStores
from wake_idle import GRACE, WakeIdle, blockers, final_check

NOW = datetime(2026, 11, 22, tzinfo=UTC)


@pytest.fixture
def idle(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"supervision":"unattended"}', encoding="utf-8")
    controller = WakeIdle(tmp_path / "data", config, tmp_path, clock=lambda: 0)
    controller.tick(now=NOW, dry_run=True)
    return controller


@pytest.mark.parametrize(
    "kind", ["task", "queued", "running", "claimed", "claim", "recent", "attended"]
)
def test_each_blocker_cancels_pending(idle, kind):
    stores = DashboardStores(idle.data_dir)
    if kind == "task":
        stores.inbox.put("task", {"status": "open", "assignee": "agent"})
    elif kind in {"queued", "running", "claimed"}:
        stores.runs.put("run", {"status": kind})
    elif kind == "claim":
        stores.runs.put("run", {}, claim=True)
    elif kind == "recent":
        stores.runs.put("run", {"status": "completed", "finished_at_utc": NOW.isoformat()})
    else:
        idle.config_path.write_text('{"supervision":"attended"}', encoding="utf-8")
    out = idle.tick(now=NOW + GRACE, dry_run=True)
    assert out["status"] == "sleep_cancelled"
    assert (idle.data_dir / "wake-idle.cancel").exists()


def test_grace_and_dry_receipt(idle):
    assert idle.tick(now=NOW + GRACE - timedelta(seconds=1), dry_run=True)["blockers"] == ["grace"]
    assert idle.tick(now=NOW + GRACE, dry_run=True)["status"] == "sleep_dry_run"
    receipt = json.loads((idle.data_dir / "wake-idle.json").read_text())
    assert receipt["dry_run"] is True
    assert receipt["status"] == "sleep_dry_run"


@pytest.mark.parametrize("kind", ["task", "queued", "claim", "recent", "attended"])
def test_final_recheck_prevents_handoff(idle, kind):
    stores = DashboardStores(idle.data_dir)

    def arrive():
        if kind == "attended":
            idle.config_path.write_text('{"supervision":"attended"}', encoding="utf-8")
        elif kind == "task":
            stores.inbox.put("new", {"status": "open", "assignee": "agent"})
        else:
            stores.runs.put(
                "new",
                {
                    "status": "queued" if kind == "queued" else "completed",
                    "finished_at_utc": (NOW + GRACE).isoformat(),
                },
                claim=kind == "claim",
            )

    called = []
    out = idle.tick(
        now=NOW + GRACE,
        dry_run=True,
        before_commit=arrive,
        handoff=lambda *args: called.append(args),
    )
    assert out["status"] == "sleep_cancelled"
    assert called == []


def test_resume_restarts_grace(idle):
    idle.clock = lambda: 120
    assert "grace" in idle.tick(now=NOW + GRACE, dry_run=True)["blockers"]


def test_owner_tasks_audio_and_old_runs_do_not_block(idle):
    stores = DashboardStores(idle.data_dir)
    stores.inbox.put("owner", {"status": "open", "assignee": "owner"})
    stores.runs.put(
        "old",
        {
            "status": "completed",
            "finished_at_utc": (NOW - GRACE - timedelta(seconds=1)).isoformat(),
        },
    )
    assert blockers(idle.data_dir, idle.config_path, NOW) == []


def test_bad_state_fails_closed(idle):
    folder = idle.data_dir / "runs"
    folder.mkdir()
    (folder / "broken.json").write_text("bad", encoding="utf-8")
    assert idle.tick(now=NOW + GRACE, dry_run=True)["status"] == "sleep_cancelled"


def test_handoff_seam_is_called_only_after_recheck(idle):
    # Use real-time grace because non-dry handoff rechecks the current clock.
    idle.idle_since = datetime.now(UTC) - GRACE - timedelta(seconds=1)
    called = []
    out = idle.tick(handoff=lambda *args: called.append(args))
    assert out["status"] == "sleep_helper_returned"
    assert len(called) == 1


@pytest.mark.parametrize(
    "kind", ["task", "queued", "claimed", "running", "claim", "recent", "attended", "cancel"]
)
def test_actual_final_guard_blocks_late_arrivals(idle, kind):
    stores = DashboardStores(idle.data_dir)
    (idle.data_dir / "wake-idle.cancel").unlink(missing_ok=True)
    if kind == "attended":
        idle.config_path.write_text('{"supervision":"attended"}', encoding="utf-8")
    elif kind == "cancel":
        (idle.data_dir / "wake-idle.cancel").touch()
    elif kind == "task":
        stores.inbox.put("late", {"status": "open", "assignee": "agent"})
    else:
        stores.runs.put(
            "late",
            {"status": "completed", "finished_at_utc": datetime.now(UTC).isoformat()}
            if kind == "recent"
            else {"status": kind},
            claim=kind == "claim",
        )
    if kind != "cancel":
        # Verify the fresh state check independently from admission's marker.
        (idle.data_dir / "wake-idle.cancel").unlink(missing_ok=True)
    assert final_check(idle.data_dir, idle.config_path) == 2


def test_admission_during_helper_preparation_cancels(idle):
    idle.idle_since = datetime.now(UTC) - GRACE - timedelta(seconds=1)

    def prepare(_repo, data, config):
        # A separate thread must be able to admit work while preparation runs.
        import threading

        admitted = threading.Event()

        def arrive():
            DashboardStores(data).runs.put("late", {"status": "queued"})
            admitted.set()

        worker = threading.Thread(target=arrive, daemon=True)
        worker.start()
        assert admitted.wait(3), "preparation must not hold admission lock"
        worker.join()
        assert final_check(data, config) == 2

    idle.tick(handoff=prepare)


def test_actual_final_guard_allows_idle(idle):
    (idle.data_dir / "wake-idle.cancel").unlink(missing_ok=True)
    assert final_check(idle.data_dir, idle.config_path) == 0
