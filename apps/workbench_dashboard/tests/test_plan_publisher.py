from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores, StoreError
from plan_publisher import sync_decision, sync_plan, sync_run


def test_sync_plan_round_trip(tmp_path) -> None:
    source = tmp_path / "loop.md"
    source.write_text("# Loop\n- stream A: done\n", encoding="utf-8")
    stores = DashboardStores(tmp_path / "data")
    record = sync_plan(
        stores,
        plan_id="loop-1",
        title="Evening loop",
        source_file=source,
        status="complete",
    )
    assert record["body"].startswith("# Loop")
    stored = stores.plans.get("loop-1")
    assert stored is not None and stored["status"] == "complete"
    assert stored["title"] == "Evening loop"


def test_sync_plan_missing_file(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    with pytest.raises(StoreError):
        sync_plan(
            stores,
            plan_id="loop-1",
            title="x",
            source_file=tmp_path / "nope.md",
            status="open",
        )


def test_sync_plan_rejects_bad_id(tmp_path) -> None:
    source = tmp_path / "loop.md"
    source.write_text("x", encoding="utf-8")
    stores = DashboardStores(tmp_path / "data")
    with pytest.raises(StoreError):
        sync_plan(
            stores,
            plan_id="../evil",
            title="x",
            source_file=source,
            status="open",
        )


def test_sync_run_upsert(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    sync_run(stores, run_id="w4", title="W4 fix", status="committed", branch="fix/x")
    updated = sync_run(stores, run_id="w4", title="W4 fix", status="merged", commit="abc1234")
    assert updated["status"] == "merged"
    got = stores.runs.get("w4")
    assert got is not None and got["status"] == "merged"


def test_sync_decision_dedupes_open_title(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    first = sync_decision(
        stores,
        title="Ship it?",
        body="details",
        options=["Yes", "No"],
    )
    assert first.get("deduped") is None
    second = sync_decision(
        stores,
        title="Ship it?",
        body="changed",
        options=["Yes", "No"],
    )
    assert second["deduped"] is True
    assert second["id"] == first["id"]
    items, total = stores.inbox.list(limit=10)
    assert total == 1


def test_sync_decision_rejects_bad_type(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    with pytest.raises(StoreError):
        sync_decision(
            stores,
            title="x",
            body="y",
            options=[],
            task_type="mandate",
        )


def test_sync_run_carries_report(tmp_path) -> None:
    stores = DashboardStores(tmp_path / "data")
    record = sync_run(stores, run_id="w4", title="W4 fix", status="merged", report="Done.")
    assert record["report"] == "Done."
    assert stores.runs.get("w4") is not None
    assert stores.runs.get("w4")["report"] == "Done."
