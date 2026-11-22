"""Focused tests for the allowance health check (evaluate + file logic)."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "scripts" / "allowance_healthcheck.py"


def _load():
    spec = importlib.util.spec_from_file_location("allowance_healthcheck", HERE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _load()
NOW = datetime.now(UTC)


def _window(**over):
    base = {
        "provider": "codex",
        "bucket_id": "codex",
        "window": "primary",
        "used_percent": 10.0,
        "remaining_percent": 90.0,
        "resets_at_utc": (NOW + timedelta(days=3)).isoformat(),
        "source": "codex_app_server",
        "details": {},
    }
    base.update(over)
    return base


def test_healthy_windows_no_problems() -> None:
    result = CHECK.evaluate(
        {"codex": {"status": "available", "windows": [_window()]}},
        [],
        NOW,
    )
    assert result["problems"] == []
    assert result["stale_models"] == []


def test_exhausted_and_failed_readers_flagged() -> None:
    result = CHECK.evaluate(
        {
            "codex": {"status": "unknown", "reason": "client_unavailable", "windows": []},
            "copilot": {
                "status": "available",
                "windows": [_window(provider="copilot", used_percent=99.0)],
            },
        },
        [],
        NOW,
    )
    kinds = {p["kind"] for p in result["problems"]}
    assert kinds == {"reader_failed", "window_exhausted"}


def test_optional_reader_errors_stay_informational() -> None:
    result = CHECK.evaluate(
        {"kiro": {"status": "unknown", "reason": "client_unavailable", "windows": []}},
        [],
        NOW,
    )
    assert result["problems"] == []
    assert result["unavailable"] == ["kiro"]


def test_stale_models_listed_not_filed() -> None:
    old = (NOW - timedelta(days=45)).timestamp()
    new = (NOW - timedelta(days=2)).timestamp()
    result = CHECK.evaluate({}, [("model-old", old), ("model-new", new)], NOW)
    assert result["stale_models"] == ["model-old"]
    assert result["problems"] == []


def test_regressed_reader_flags_problem() -> None:
    result = CHECK.evaluate(
        {"kiro": {"status": "unknown", "reason": "timeout", "windows": []}},
        [],
        NOW,
        previously_available={"kiro"},
    )
    assert [p["kind"] for p in result["problems"]] == ["reader_regressed"]


def test_filing_dedupes_by_problem_hash(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, "apps/workbench_dashboard")
    from dashboard_stores import DashboardStores

    stores = DashboardStores(tmp_path / "data")
    problems = [{"kind": "reader_failed", "provider": "codex", "detail": "x"}]
    first = CHECK.file_problems(stores, problems, [])
    assert first is not None
    assert first["assignee"] == first["waiting_on"] == "agent"
    assert first["options"] == []
    assert "Agent action:" in first["body"]
    assert "receipt-*.json" in first["body"]
    assert "resolution" in first["body"]
    assert CHECK.file_problems(stores, problems, []) is None
    stores.answer_inbox_task(first["id"], answer="Investigate")
    assert CHECK.file_problems(stores, problems, []) is None
    other = CHECK.file_problems(
        stores, problems + [{"kind": "window_exhausted", "provider": "codex", "detail": "y"}], []
    )
    assert other is not None
