"""Tests for the restrictions live feeder (subprocess counts)."""

from __future__ import annotations

import pytest
from dashboard_stores import DashboardStores
from restrictions_view import restrictions_status


def _stores(tmp_path) -> DashboardStores:
    return DashboardStores(tmp_path)


def test_empty_stores_report_zeros(tmp_path) -> None:
    view = restrictions_status(_stores(tmp_path))
    assert view["ok"] is True
    sub = view["subprocess"]
    assert sub["run_requests"] == 0
    assert sub["approvals"] == 0
    assert sub["approved"] == 0
    assert sub["rejected"] == 0
    assert sub["pending"] == 0


def test_counts_runs_and_approvals(tmp_path) -> None:
    stores = _stores(tmp_path)
    stores.runs.put("r1", {"id": "r1", "origin": "chat", "status": "queued"})
    stores.runs.put("r2", {"id": "r2", "origin": "chat", "status": "completed"})
    stores.runs.put("r3", {"id": "r3", "origin": "supervisor", "status": "queued"})
    stores.inbox.put(
        "a1",
        {
            "id": "a1",
            "title": "Approve agent run: x",
            "status": "answered",
            "answer": "Approve",
        },
    )
    stores.inbox.put(
        "a2",
        {
            "id": "a2",
            "title": "Approve agent run: y",
            "status": "answered",
            "answer": "Reject",
        },
    )
    stores.inbox.put("a3", {"id": "a3", "title": "Approve agent run: z", "status": "open"})
    stores.inbox.put("q1", {"id": "q1", "title": "P7 Q1", "status": "open"})
    view = restrictions_status(stores)
    sub = view["subprocess"]
    assert sub["run_requests"] == 2
    assert sub["by_status"] == {"queued": 1, "completed": 1}
    assert sub["approvals"] == 3
    assert sub["approved"] == 1
    assert sub["rejected"] == 1
    assert sub["pending"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
