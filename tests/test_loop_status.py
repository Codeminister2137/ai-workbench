"""Remaining-work derivation from plan ledger + inbox."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop_status.py"


def _load():
    sys.path.insert(0, str(SCRIPT.parents[1] / "apps" / "workbench_dashboard"))
    spec = importlib.util.spec_from_file_location("loop_status", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["loop_status"] = module
    spec.loader.exec_module(module)
    return module


loop_status = _load()

PLAN = """# Plan

| Order | Concrete action | Source | Authority | Rough | Validation | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Do mail | Owner | Local | 30 min | Tested | COMPLETE 10:00 UTC (done) |
| 2 | Do research | Owner | Web | 60 min | Filed | IN_PROGRESS from 10:30 |
| 3 | Do extra | Owner | Local | 20 min | Tests | READY |
| 4 | Hmm | Owner | ? | ? | ? | BLOCKED (needs owner call) |
| Final | Closeout | AGENTS.md | Default | 35 min | Verified | Required for every ending |
"""


def test_counts_and_remaining(tmp_path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN, encoding="utf-8")
    rows, error = loop_status.parse_ledger(plan)
    assert error is None
    assert len(rows) == 5
    assert [row["status"] for row in rows] == [
        "COMPLETE",
        "IN_PROGRESS",
        "READY",
        "BLOCKED",
        "UNMARKED",
    ]


def test_reverted_counts_as_terminal(tmp_path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(
        "| Order | C | S | A | R | V | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 1 | X | O | L | 1 | T | REVERTED (broke tests) |\n",
        encoding="utf-8",
    )
    text = loop_status.render(plan, tmp_path / "absent-data")
    assert "1 complete, 0 blocked, 0 remaining, 1 rows" in text
    assert "remaining: none (ledger fully complete)" in text


def test_missing_plan_reports_error(tmp_path) -> None:
    rows, error = loop_status.parse_ledger(tmp_path / "absent.md")
    assert rows == []
    assert error is not None and "not readable" in error


def test_missing_data_dir_reports_unknown(tmp_path) -> None:
    items, error = loop_status.open_inbox_items(tmp_path / "absent-data")
    assert items is None
    assert error is not None and "missing" in error


def test_render_lists_remaining_and_open_inbox(tmp_path) -> None:
    from dashboard_stores import DashboardStores

    plan = tmp_path / "plan.md"
    plan.write_text(PLAN, encoding="utf-8")
    data_dir = tmp_path / "data"
    stores = DashboardStores(data_dir)
    stores.create_inbox_task(title="Pick me", body="b", task_type="decision")
    text = loop_status.render(plan, data_dir)
    assert "1 complete, 1 blocked, 3 remaining, 5 rows" in text
    assert "- [2] Do research (IN_PROGRESS)" in text
    assert "- [4] Do extra" not in text  # READY row 3, not row 4
    assert "- [3] Do extra (READY)" in text
    assert "blocked-pending:" in text and "needs owner call" in text
    assert "open inbox: 1" in text
    assert "Pick me [decision]" in text
