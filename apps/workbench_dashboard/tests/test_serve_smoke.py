"""Serve smoke checks against a fixture dashboard (read-only probes)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "serve-smoke.py"


def _load():
    spec = importlib.util.spec_from_file_location("serve_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_passes_against_fixture_server(dashboard_server, tmp_path, monkeypatch) -> None:
    smoke = _load()
    data = tmp_path / "repo" / "apps" / "workbench_dashboard" / "data"
    data.mkdir(parents=True)
    (data / "serve-version.json").write_text(json.dumps({"commit": "abc123"}), encoding="utf-8")
    monkeypatch.setattr(smoke, "_origin_head", lambda repo: "abc123")
    results = smoke.run_all(dashboard_server, tmp_path / "repo")
    assert [name for name, _ok, _msg in results] == [
        "status",
        "agent-config",
        "e2e-open",
        "serve-drift",
    ]
    assert all(ok for _name, ok, _msg in results), results


def test_smoke_detects_serve_drift(tmp_path, monkeypatch) -> None:
    smoke = _load()
    data = tmp_path / "apps" / "workbench_dashboard" / "data"
    data.mkdir(parents=True)
    (data / "serve-version.json").write_text(json.dumps({"commit": "aaa"}), encoding="utf-8")
    monkeypatch.setattr(smoke, "_origin_head", lambda repo: "bbb")
    ok, message = smoke.check_serve_drift(tmp_path)
    assert ok is False
    assert "lags origin" in message


def test_smoke_reports_agent_mode_off_as_info(dashboard_server) -> None:
    smoke = _load()
    ok, message = smoke.check_agent_config(dashboard_server)
    assert ok is True
    assert "agent mode off" in message
