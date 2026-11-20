"""Grade records: verdict folding, file writing, catalog overlay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ai_orchestrator.catalog import load_model_catalog, measured_overlay
from ai_provider.grade_records import (
    fold_verdicts,
    load_grade_records,
    record_grades,
)

CATALOG = """\
[[models]]
route_id = "r1"
provider = "ollama"
model = "m1"
location = "local"

[models.capabilities]
chat = true
streaming = false
tools = false
"""


def _verdict(route="r1", capability="tools", status="pass", checked="2026-11-20T10:00:00+00:00"):
    return {
        "route_id": route,
        "capability": capability,
        "status": status,
        "checked_utc": checked,
        "elapsed_seconds": 1.0,
        "detail": "test",
    }


def test_fold_maps_pass_fail_and_drops_inconclusive():
    records = fold_verdicts(
        [
            _verdict(status="pass"),
            _verdict(capability="streaming", status="fail"),
            _verdict(capability="structured_output", status="error"),
            _verdict(capability="chat", status="unknown"),
        ],
        evidence="eval.json",
    )
    assert len(records) == 1
    assert records[0].capabilities == {"streaming": False, "tools": True}


def test_fold_later_verdict_wins_and_routes_sorted():
    records = fold_verdicts(
        [
            _verdict(route="b", status="pass"),
            _verdict(route="a", status="fail"),
            _verdict(route="a", status="pass", checked="2026-11-20T11:00:00+00:00"),
        ],
        evidence="eval.json",
    )
    assert [record.route_id for record in records] == ["a", "b"]
    assert records[0].capabilities == {"tools": True}
    assert records[0].checked_utc == "2026-11-20T11:00:00+00:00"


def test_fold_rejects_bad_input():
    with pytest.raises(ValueError, match="evidence"):
        fold_verdicts([_verdict()], evidence="  ")
    with pytest.raises(ValueError, match="Unknown capability"):
        fold_verdicts([_verdict(capability="telepathy")], evidence="e")
    with pytest.raises(ValueError, match="route_id"):
        fold_verdicts([_verdict(route="")], evidence="e")


def test_record_grades_writes_dated_files_and_never_overwrites(tmp_path: Path):
    out = tmp_path / "eval.jsonl"
    out.write_text(json.dumps(_verdict()) + "\n", encoding="utf-8")
    written = record_grades(out, tmp_path / "grades", evidence="run-1")
    assert len(written) == 1
    assert written[0].name == "r1-2026-11-20.json"
    saved = json.loads(written[0].read_text(encoding="utf-8"))
    assert saved["capabilities"] == {"tools": True}
    assert saved["evidence"] == "run-1"
    with pytest.raises(FileExistsError):
        record_grades(out, tmp_path / "grades", evidence="run-1")


def test_record_grades_rejects_invalid_jsonl(tmp_path: Path):
    out = tmp_path / "eval.jsonl"
    out.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        record_grades(out, tmp_path / "grades", evidence="run-1")


def test_load_grade_records_newest_wins_and_missing_dir_empty(tmp_path: Path):
    assert load_grade_records(tmp_path / "absent") == {}
    grades = tmp_path / "grades"
    grades.mkdir()
    old = {
        "route_id": "r1",
        "checked_utc": "2026-11-19T10:00:00+00:00",
        "capabilities": {"tools": False},
        "evidence": "old",
    }
    new = {
        "route_id": "r1",
        "checked_utc": "2026-11-20T10:00:00+00:00",
        "capabilities": {"tools": True},
        "evidence": "new",
    }
    (grades / "r1-2026-11-19.json").write_text(json.dumps(old), encoding="utf-8")
    (grades / "r1-2026-11-20.json").write_text(json.dumps(new), encoding="utf-8")
    loaded = load_grade_records(grades)
    assert loaded["r1"].capabilities == {"tools": True}
    assert loaded["r1"].evidence == "new"


def test_catalog_overlay_measured_wins_with_provenance(tmp_path: Path):
    catalog = tmp_path / "cat.toml"
    catalog.write_text(CATALOG, encoding="utf-8")
    plain = load_model_catalog(catalog)
    assert plain[0].backend.capabilities.tools is False
    overlay = measured_overlay(
        {
            "r1": {
                "capabilities": {"tools": True},
                "checked_utc": "2026-11-20T10:00:00+00:00",
                "evidence": "run-1",
            },
            "retired": {
                "capabilities": {"tools": True},
                "checked_utc": "2026-11-20T10:00:00+00:00",
                "evidence": "run-1",
            },
        }
    )
    entries = load_model_catalog(catalog, measured=overlay)
    assert entries[0].backend.capabilities.tools is True
    assert entries[0].backend.capabilities.streaming is False  # unmeasured stays
    assert entries[0].metadata["measured_at"] == "2026-11-20T10:00:00+00:00"
    assert entries[0].metadata["measured_evidence"] == "run-1"
    assert entries[0].metadata["measured_capabilities"] == "tools"


def test_measured_overlay_rejects_invalid_record():
    with pytest.raises(ValueError, match="Invalid grade record"):
        measured_overlay({"r1": {"capabilities": {}}})
