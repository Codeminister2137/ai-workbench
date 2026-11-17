from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from dashboard_test_http import serve_dashboard


@pytest.fixture
def drain_server(tmp_path):
    calls: list = []
    with serve_dashboard(tmp_path, drain_calls=calls) as (base, _tmp):
        yield base, _tmp, calls


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_run(tmp_path: Path, run_id: str, inbox_id: str, **overrides) -> None:
    record = {
        "id": run_id,
        "title": "Seeded run",
        "status": "queued",
        "body": "Do the thing",
        "origin": "chat",
        "session_id": "dashboard-test",
        "fanout_policy": "restricted",
        "fanout_effective": "restricted",
        "inbox_id": inbox_id,
        "project_id": None,
        "plan_id": None,
    }
    record.update(overrides)
    _write(tmp_path / "data" / "runs" / f"{run_id}.json", record)


def _seed_inbox(tmp_path: Path, inbox_id: str, *, status: str, answer=None) -> None:
    _write(
        tmp_path / "data" / "inbox" / f"{inbox_id}.json",
        {"id": inbox_id, "status": status, "answer": answer},
    )


def _drain(base: str, payload: dict) -> dict:
    request = Request(
        f"{base}/api/runs/drain",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _drain_status(base: str, payload: dict) -> int:
    request = Request(
        f"{base}/api/runs/drain",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10):
            return 200
    except HTTPError as exc:
        return exc.code


def test_drain_parks_unapproved_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1")
    _seed_inbox(tmp_path, "inbox1", status="open")

    out = _drain(base, {})
    assert out["ok"] is True
    assert out["outcomes"][0]["action"] == "parked"
    assert calls == []
    run = json.loads((tmp_path / "data" / "runs" / "run1.json").read_text())
    assert run["status"] == "queued"


def test_drain_executes_approved_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1")
    _seed_inbox(tmp_path, "inbox1", status="answered", answer="Approve")

    out = _drain(base, {})
    assert out["ok"] is True
    assert out["outcomes"][0]["status"] == "completed"
    assert calls == ["run1"]
    run = json.loads((tmp_path / "data" / "runs" / "run1.json").read_text())
    assert run["status"] == "completed"


def test_drain_skips_cancelled_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1", cancel_requested=True)
    _seed_inbox(tmp_path, "inbox1", status="answered", answer="Approve")

    out = _drain(base, {})
    assert out["ok"] is True
    assert out["outcomes"][0]["status"] == "cancelled"
    assert calls == []


def test_drain_defaults_to_one_run(drain_server) -> None:
    base, tmp_path, calls = drain_server
    _seed_run(tmp_path, "run1", "inbox1")
    _seed_run(tmp_path, "run2", "inbox2")
    _seed_inbox(tmp_path, "inbox1", status="answered", answer="Approve")
    _seed_inbox(tmp_path, "inbox2", status="answered", answer="Approve")

    out = _drain(base, {})
    executed = [o for o in out["outcomes"] if "action" not in o]
    assert len(executed) == 1
    assert len(calls) == 1


def test_drain_rejects_bad_max_runs(drain_server) -> None:
    base, _tmp_path, _calls = drain_server
    assert _drain_status(base, {"max_runs": 0}) == 400
    assert _drain_status(base, {"max_runs": 101}) == 400
    assert _drain_status(base, {"max_runs": "many"}) == 400
    assert _drain_status(base, {"max_runs": True}) == 400


def _report_stores(tmp_path):
    from dashboard_stores import DashboardStores

    return DashboardStores(tmp_path / "data")


def _report_run(stores, run_id, inbox_id, **over):
    record = {
        "id": run_id,
        "title": "t",
        "status": "completed",
        "bridged_from": inbox_id,
    }
    record.update(over)
    stores.runs.put(run_id, record)
    return record


def _report_item(stores, inbox_id, **over):
    record = {"id": inbox_id, "status": "open", "title": "t", "body": "b"}
    record.update(over)
    stores.inbox.put(inbox_id, record)
    return record


def test_terminal_report_appends_outcome_note(tmp_path) -> None:
    from dashboard_web_app import report_run_terminal

    stores = _report_stores(tmp_path)
    _report_item(stores, "in1")
    _report_run(stores, "run1", "in1")
    outcome = report_run_terminal(
        stores, {"run_id": "run1", "status": "completed", "title": "t", "error": None}
    )
    assert outcome["action"] == "noted"
    item = stores.inbox.get("in1")
    assert item is not None
    assert "run1" in (item.get("note") or "")
    assert "completed" in (item.get("note") or "")
    assert item["status"] == "open"


def test_terminal_report_flags_failures_and_dedupes(tmp_path) -> None:
    from dashboard_web_app import report_run_terminal

    stores = _report_stores(tmp_path)
    _report_item(stores, "in1")
    _report_run(stores, "run1", "in1")
    summary = {"run_id": "run1", "status": "failed", "title": "t", "error": "boom"}
    assert report_run_terminal(stores, summary)["action"] == "noted"
    noted = stores.inbox.get("in1")
    assert noted is not None and "boom" in (noted.get("note") or "")
    assert report_run_terminal(stores, summary)["action"] == "skipped"


def test_terminal_report_skips_unlinked_and_closed(tmp_path) -> None:
    from dashboard_web_app import report_run_terminal

    stores = _report_stores(tmp_path)
    _report_run(stores, "run1", None)
    assert (
        report_run_terminal(
            stores, {"run_id": "run1", "status": "completed", "title": "t", "error": None}
        )["action"]
        == "skipped"
    )
    _report_item(stores, "in2", status="closed")
    _report_run(stores, "run2", "in2")
    assert (
        report_run_terminal(
            stores, {"run_id": "run2", "status": "completed", "title": "t", "error": None}
        )["action"]
        == "skipped"
    )
