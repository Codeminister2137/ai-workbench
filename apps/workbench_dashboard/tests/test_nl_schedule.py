"""Sched A: NL proposal approval queues a drain-driven run.

Answering "Schedule it" on an NL proposal order creates a queued run
linked to the inbox record; the next drain tick executes it. "Decline"
queues nothing, re-answering maps to the same run id, and non-NL
answers never schedule.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dashboard_test_http import post_json, serve_dashboard


@pytest.fixture
def sched_server(tmp_path):
    calls: list = []
    with serve_dashboard(tmp_path, drain_calls=calls) as (base, _tmp):
        yield base, _tmp, calls


def _propose(base: str) -> dict:
    return post_json(base, "/api/tasks/propose", {"text": "Review the auth module, 30 min"})


def _answer(base: str, item_id: str, option_index: int) -> dict:
    return post_json(
        base, f"/api/inbox/{item_id}/answer", {"answer": "", "option_index": option_index}
    )


def _run_file(tmp_path: Path, run_id: str) -> Path:
    return tmp_path / "data" / "runs" / f"{run_id}.json"


def test_schedule_it_queues_run(sched_server) -> None:
    base, tmp_path, _ = sched_server
    created = _propose(base)
    out = _answer(base, created["id"], 0)
    assert out["ok"] is True
    run_id = out["scheduled_run"]
    assert run_id == f"nl-{created['proposal']['task_id']}-{created['id'][:8]}"
    run = json.loads(_run_file(tmp_path, run_id).read_text(encoding="utf-8"))
    assert run["status"] == "queued"
    assert run["inbox_id"] == created["id"]
    assert run["origin"] == "nl-schedule"
    assert run["model"] == "qwen2.5-coder:14b"
    assert run["budget_seconds"] == 1800.0
    assert run["body"] == created["proposal"]["prompt"]


def test_decline_queues_nothing(sched_server) -> None:
    base, tmp_path, _ = sched_server
    created = _propose(base)
    out = _answer(base, created["id"], 1)
    assert out["ok"] is True
    assert out["scheduled_run"] is None
    assert list((tmp_path / "data" / "runs").glob("*.json")) == []


def test_reanswer_maps_to_same_run(sched_server) -> None:
    base, tmp_path, _ = sched_server
    created = _propose(base)
    first = _answer(base, created["id"], 0)
    second = _answer(base, created["id"], 0)
    assert second["scheduled_run"] == first["scheduled_run"]
    assert len(list((tmp_path / "data" / "runs").glob("*.json"))) == 1


def test_drain_executes_scheduled_run(sched_server) -> None:
    base, tmp_path, calls = sched_server
    created = _propose(base)
    answered = _answer(base, created["id"], 0)
    out = post_json(base, "/api/runs/drain", {})
    assert out["ok"] is True
    assert out["outcomes"][0]["status"] == "completed"
    assert calls == [answered["scheduled_run"]]
    run = json.loads(_run_file(tmp_path, answered["scheduled_run"]).read_text(encoding="utf-8"))
    assert run["status"] == "completed"


def test_plain_answer_schedules_nothing(sched_server) -> None:
    base, tmp_path, _ = sched_server
    inbox_dir = tmp_path / "data" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    (inbox_dir / "plain1.json").write_text(
        json.dumps({"id": "plain1", "status": "open", "options": ["Approve"]}),
        encoding="utf-8",
    )
    out = _answer(base, "plain1", 0)
    assert out["ok"] is True
    assert out["scheduled_run"] is None
    assert list((tmp_path / "data" / "runs").glob("*.json")) == []
