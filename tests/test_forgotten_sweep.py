"""Focused tests for the forgotten-items sweep collectors."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts" / "forgotten_sweep.py"


def _load():
    spec = importlib.util.spec_from_file_location("forgotten_sweep", HERE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SWEEP = _load()
NOW = datetime.now(UTC)


def _ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def test_r1_flags_failed_without_followup_and_skips_superseded() -> None:
    runs = [
        {
            "id": "aaa",
            "title": "Old fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i1",
            "error": "boom",
        },
        {
            "id": "bbb",
            "title": "Old fail then retried",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i2",
        },
        {
            "id": "ccc",
            "title": "Retry ok",
            "status": "completed",
            "created_at_utc": _ts(90),
            "inbox_id": "i2",
        },
        {
            "id": "ddd",
            "title": "Fresh fail",
            "status": "failed",
            "created_at_utc": _ts(1),
            "inbox_id": None,
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["R1:aaa"]["fileable"] is True
    assert "R1:bbb" not in by_key  # superseded by newer sibling
    assert by_key["R1:ddd"]["fileable"] is False  # watching


def test_r1_skips_superseded_runs() -> None:
    runs = [
        {
            "id": "old",
            "title": "Old fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
            "superseded_by": "new",
        },
    ]
    assert SWEEP.collect_runs(runs, [], NOW)[0] == []


def test_r1_skips_failed_mentioned_in_open_inbox() -> None:
    runs = [
        {
            "id": "abc12345",
            "title": "Fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
        },
    ]
    inbox = [
        {
            "id": "i9",
            "title": "Requeue abc12345",
            "status": "open",
            "body": "",
            "resolution": "",
            "note": "",
        },
    ]
    assert SWEEP.collect_runs(runs, inbox, NOW)[0] == []


def test_idle_branch_ready_live_flagged() -> None:
    runs = [
        {"id": "q", "title": "Q", "status": "queued", "created_at_utc": _ts(100)},
        {"id": "b", "title": "B", "status": "branch-ready", "created_at_utc": _ts(100)},
        {"id": "l", "title": "L", "status": "live", "created_at_utc": _ts(20)},
        {"id": "m", "title": "M", "status": "merged", "created_at_utc": _ts(200)},
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["R2:q"]["fileable"] is True
    assert by_key["R3:b"]["fileable"] is True
    assert by_key["R4:l"]["fileable"] is True
    assert not [k for k in by_key if k.startswith("R1:m")]


def test_mtime_fallback_flags_timestamp_less_records(tmp_path: Path) -> None:
    store = tmp_path / "runs"
    store.mkdir()
    (store / "x.json").write_text(
        json.dumps({"id": "x", "title": "X", "status": "live"}), encoding="utf-8"
    )
    runs = SWEEP._load_store(tmp_path, "runs")
    assert runs[0]["_file_mtime"]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    assert findings[0]["key"] == "R4:x"
    assert findings[0]["fileable"] is False  # just written -> watching


def test_inbox_answered_open_buckets() -> None:
    inbox = [
        {
            "id": "a1",
            "title": "A",
            "status": "answered",
            "assignee": "owner",
            "created_at": _ts(30),
            "answer": "yes",
        },
        {"id": "a2", "title": "B", "status": "open", "assignee": "agent", "created_at": _ts(60)},
        {"id": "a3", "title": "C", "status": "open", "assignee": "owner", "created_at": _ts(60)},
        {"id": "a4", "title": "D", "status": "closed", "created_at": _ts(60)},
    ]
    by_key = {f["key"]: f for f in SWEEP.collect_inbox(inbox, NOW)}
    assert by_key["I1:a1"]["fileable"] is True
    assert by_key["I2:a2"]["fileable"] is True
    assert by_key["I3:a3"]["fileable"] is False  # 7d gate
    assert "I3:a4" not in by_key and "I1:a4" not in by_key


def test_e2e_linkage() -> None:
    tasks = [
        {"id": "t1", "title": "E2E promotion for abc1234", "status": "open", "created_at": _ts(60)},
        {
            "id": "t2",
            "title": "E2E promotion for def5678",
            "status": "submitted",
            "created_at": _ts(60),
        },
    ]
    reports = [
        {
            "id": "r1",
            "title": "E2E promotion for abc1234",
            "overall": "fail",
            "built_utc": _ts(30),
            "commit": "abc1234xy",
        },
        {
            "id": "r2",
            "title": "E2E promotion for 9999999",
            "overall": "fail",
            "built_utc": _ts(30),
            "commit": "9999999zz",
        },
        {
            "id": "r3",
            "title": "E2E promotion for 8888888",
            "overall": "fail",
            "built_utc": _ts(30),
            "commit": "8888888zz",
        },
        {
            "id": "r4",
            "title": "E2E promotion for 7777777",
            "overall": "pass",
            "built_utc": _ts(30),
            "commit": "7777777zz",
        },
    ]
    runs = [
        {"id": "f1", "title": "E2E follow-up: 9999999 (1 failed)", "status": "failed"},
    ]
    findings, _resolved = SWEEP.collect_e2e(tasks, reports, runs, [], NOW)
    by_key = {f["key"]: f for f in findings}
    assert by_key["E1:r1"]["fileable"] is True  # no follow-up anywhere
    assert by_key["E2:r2"]["fileable"] is True  # follow-up failed
    assert "E1:r3" in by_key and by_key["E1:r3"]["fileable"] is True
    assert "E3:t1" in by_key and by_key["E3:t1"]["assignee"] == "owner"
    assert not [k for k in by_key if ":t2" in k or ":r4" in k]


def test_closed_approval_resolves_r1_and_stales_r2() -> None:
    inbox = [
        {
            "id": "i1",
            "title": "Approve: A",
            "status": "closed",
            "created_at": _ts(100),
            "resolution": "underlying task resolved",
        },
        {
            "id": "i2",
            "title": "Approve: B",
            "status": "closed",
            "created_at": _ts(100),
            "resolution": "Superseded: done directly",
        },
    ]
    runs = [
        {
            "id": "f",
            "title": "Failed A",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i1",
        },
        {
            "id": "q",
            "title": "Queued B",
            "status": "queued",
            "created_at_utc": _ts(100),
            "inbox_id": "i2",
        },
    ]
    findings, resolved = SWEEP.collect_runs(runs, inbox, NOW)
    by_key = {f["key"]: f for f in findings}
    assert "R1:f" not in by_key
    assert "R2:q" not in by_key
    assert {r["key"] for r in resolved} == {"R1:f", "R2:q"}
    r5 = [f for f in findings if f["category"] == "R5"]
    assert len(r5) == 1 and r5[0]["members"][0]["id"] == "q"


def test_still_open_tracker_keeps_finding() -> None:
    inbox = [
        {
            "id": "i1",
            "title": "Approve: A",
            "status": "closed",
            "created_at": _ts(100),
            "resolution": "Partial: task abc12345 stays open for the second half",
        },
        {"id": "abc12345zz", "title": "Second half", "status": "open", "created_at": _ts(90)},
    ]
    runs = [
        {
            "id": "deadbeefdeadbeefdeadbeefdeadbeef",
            "title": "Failed A",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": "i1",
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, inbox, NOW)
    assert "R1:deadbeefdeadbeefdeadbeefdeadbeef" in {f["key"] for f in findings}


def test_old_run_verify_first_with_evidence() -> None:
    inbox = [
        {
            "id": "i9",
            "title": "Approve: mobile top bar",
            "status": "closed",
            "created_at": _ts(200),
            "resolution": "Merged fix/mobile-topbar",
        },
    ]
    runs = [
        {
            "id": "old",
            "title": "Top bar in mobile",
            "status": "failed",
            "created_at_utc": _ts(200),
            "inbox_id": None,
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, inbox, NOW, ("develop", "fix/mobile-topbar"))
    finding = next(f for f in findings if f["key"] == "R1:old")
    assert finding["action"].startswith("VERIFY FIRST")
    member_ids = [m["id"] for m in finding["members"]]
    assert "inbox:i9" in member_ids
    assert "branch:fix/mobile-topbar" in member_ids


def test_e3_skips_superseded_tasks() -> None:
    tasks = [
        {
            "id": "old",
            "title": "E2E promotion for abc",
            "status": "open",
            "created_at": _ts(100),
            "merge_commit": "abc123",
            "items": [{"id": "behavior:x", "behavior": "X"}],
        },
        {
            "id": "new",
            "title": "E2E promotion for abc",
            "status": "open",
            "created_at": _ts(10),
            "merge_commit": "abc123",
            "items": [{"id": "behavior:x", "behavior": "X"}],
        },
    ]
    findings, resolved = SWEEP.collect_e2e(tasks, [], [], [], NOW)
    keys = {f["key"] for f in findings}
    assert "E3:old" not in keys
    assert "E3:new" in keys
    assert {r["key"] for r in resolved} == {"E3:old"}


def test_findings_carry_dashboard_links() -> None:
    runs = [
        {
            "id": "r1",
            "title": "Fail",
            "status": "failed",
            "created_at_utc": _ts(100),
            "inbox_id": None,
        },
    ]
    findings, _resolved = SWEEP.collect_runs(runs, [], NOW)
    assert findings[0]["link"] == ""  # links attach in run(), not collectors
    body = SWEEP._filing_body(
        {
            "key": "E3:t",
            "gate_h": 48,
            "action": "act",
            "members": [],
            "link": "http://127.0.0.1:8766/#/e2e/t",
        },
        "receipt-x.json",
    )
    assert "Open: http://127.0.0.1:8766/#/e2e/t" in body


def test_run_writes_receipt_and_skips(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "runs").mkdir(parents=True)
    (data / "inbox").mkdir()
    (data / "e2e_tasks").mkdir()
    (data / "e2e_reports").mkdir()
    (data / "runs" / "f.json").write_text(
        json.dumps(
            {
                "id": "f",
                "title": "Fail",
                "status": "failed",
                "created_at_utc": _ts(100),
                "inbox_id": None,
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    receipt = SWEEP.run(data_dir=data, out_dir=out, repo=tmp_path, skip_keys=frozenset({"R1:f"}))
    assert receipt["counts"]["findings"] == 1
    assert receipt["counts"]["skipped_manual"] == 1
    assert receipt["counts"]["fileable_new"] == 0
    assert (out / receipt["receipt"]).exists()
