"""Tests for the dashboard provider-status view (cache + serialization)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ai_provider.route_probe import RouteProbe
from providers_view import (
    PROVIDER_META,
    provider_status,
    refresh_provider_status,
)


def _probe(route: str, **overrides) -> RouteProbe:
    base = {
        "route": route,
        "url": f"https://example.invalid/{route}",
        "checked_utc": "2026-11-08T13:00:00+00:00",
        "reachable": True,
        "auth_ok": True,
        "models_seen": 3,
        "sample_ids": ("a", "b"),
        "latency_ms": 42,
        "error": None,
    }
    base.update(overrides)
    return RouteProbe(**base)


def _stub(_credentials):
    return [
        _probe("openrouter"),
        _probe("requesty", reachable=False, auth_ok=None, latency_ms=None, error="URLError"),
        _probe("meta", auth_ok=False, error="http-401"),
        _probe("opencode_go"),
        _probe("ollama", auth_ok=None),
    ]


def _codex_available():
    return {
        "status": "available",
        "source": "codex_app_server",
        "reason": "available",
        "observed_at_utc": "2026-11-08T13:00:00+00:00",
        "windows": [
            {
                "bucket_id": "primary",
                "window": "primary",
                "used_percent": 12.5,
                "window_duration_minutes": 300,
                "resets_at_unix_seconds": 1794182400,
            }
        ],
        "cleanup_verified": True,
    }


def _codex_unavailable():
    return {
        "status": "unknown",
        "source": "codex_app_server",
        "reason": "client_unavailable",
        "observed_at_utc": None,
        "windows": [],
        "cleanup_verified": True,
    }


def _opencode_available():
    return {
        "status": "observed",
        "source": "opencode_go_usage",
        "windows": [
            {
                "bucket_id": "go_weekly",
                "window": "weekly",
                "used_percent": 17,
                "remaining_percent": 83,
                "resets_at": "2026-11-24T00:00:00+00:00",
            }
        ],
        "observed_at_utc": "2026-11-17T18:00:00+00:00",
    }


def _opencode_unavailable():
    return {"status": "unknown", "reason": "usage_key_not_configured", "windows": []}


def test_uncached_status_returns_unchecked_skeleton(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("REQUESTY_API_KEY", raising=False)
    monkeypatch.delenv("META_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    view = provider_status(tmp_path)
    assert view["ok"] is True
    assert view["cached"] is False
    assert [p["route"] for p in view["providers"]] == [
        "openrouter",
        "requesty",
        "meta",
        "opencode_go",
        "ollama",
        "codex",
    ]
    assert all(p["checked_at"] is None for p in view["providers"])
    assert all(p["key_configured"] is False for p in view["providers"])


def test_refresh_caches_and_serves_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-value")
    view = refresh_provider_status(
        tmp_path, probe=_stub, codex_probe=_codex_unavailable, opencode_probe=_opencode_unavailable
    )
    assert view["ok"] is True
    assert view["cached"] is False
    assert (tmp_path / "providers.json").exists()
    rows = {p["route"]: p for p in view["providers"]}
    assert rows["openrouter"]["key_configured"] is True
    assert rows["requesty"]["reachable"] is False
    assert rows["meta"]["auth_ok"] is False
    assert rows["ollama"]["account_required"] is False
    served = provider_status(tmp_path)
    assert served["cached"] is True
    assert served["providers"] == view["providers"]


def test_snapshot_never_carries_secret_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-abc123")
    view = refresh_provider_status(
        tmp_path, probe=_stub, codex_probe=_codex_unavailable, opencode_probe=_opencode_unavailable
    )
    dumped = json.dumps(view)
    assert "sk-secret-abc123" not in dumped
    dumped_cache = (tmp_path / "providers.json").read_text(encoding="utf-8")
    assert "sk-secret-abc123" not in dumped_cache


def test_refresh_appends_codex_row_with_quota_windows(tmp_path: Path) -> None:
    view = refresh_provider_status(
        tmp_path, probe=_stub, codex_probe=_codex_available, opencode_probe=_opencode_unavailable
    )
    rows = {p["route"]: p for p in view["providers"]}
    assert "codex" in rows
    codex = rows["codex"]
    assert codex["reachable"] is True
    assert codex["auth_ok"] is True
    assert codex["key_configured"] is True
    assert codex["checked_at"] == "2026-11-08T13:00:00+00:00"
    assert codex["allowance_windows"] == _codex_available()["windows"]
    served = provider_status(tmp_path)
    assert served["cached"] is True
    assert {p["route"]: p for p in served["providers"]}["codex"] == codex


def test_refresh_codex_unavailable_degrades_row(tmp_path: Path) -> None:
    view = refresh_provider_status(
        tmp_path, probe=_stub, codex_probe=_codex_unavailable, opencode_probe=_opencode_unavailable
    )
    rows = {p["route"]: p for p in view["providers"]}
    codex = rows["codex"]
    assert codex["reachable"] is False
    assert codex["auth_ok"] is None
    assert codex["key_configured"] is False
    assert codex["error"] == "client_unavailable"
    assert codex["allowance_windows"] == []


def test_refresh_attaches_opencode_windows(tmp_path: Path) -> None:
    view = refresh_provider_status(
        tmp_path, probe=_stub, codex_probe=_codex_unavailable, opencode_probe=_opencode_available
    )
    rows = {p["route"]: p for p in view["providers"]}
    assert rows["opencode_go"]["allowance_windows"] == _opencode_available()["windows"]
    assert rows["opencode_go"]["error"] is None


def test_refresh_opencode_usage_failure_surfaces_without_hiding_probe(tmp_path: Path) -> None:
    view = refresh_provider_status(
        tmp_path, probe=_stub, codex_probe=_codex_unavailable, opencode_probe=_opencode_unavailable
    )
    rows = {p["route"]: p for p in view["providers"]}
    assert rows["opencode_go"]["allowance_windows"] == []
    assert rows["opencode_go"]["reachable"] is True
    assert "usage" in (rows["opencode_go"]["error"] or "")


def test_uncached_status_includes_unchecked_codex(tmp_path: Path) -> None:
    view = provider_status(tmp_path)
    rows = {p["route"]: p for p in view["providers"]}
    assert "codex" in rows
    assert rows["codex"]["checked_at"] is None
    assert rows["codex"]["allowance_windows"] == []


def test_corrupt_cache_falls_back_to_skeleton(tmp_path: Path) -> None:
    (tmp_path / "providers.json").write_text("not json", encoding="utf-8")
    view = provider_status(tmp_path)
    assert view["cached"] is False
    assert all(p["checked_at"] is None for p in view["providers"])


def test_every_route_has_metadata() -> None:
    from ai_provider.route_probe import ROUTES

    for route, _url, _env in ROUTES:
        meta = PROVIDER_META[route]
        assert meta["display"] and meta["site_url"] and meta["blurb"]
        assert meta["site_url"].startswith("https://")
    codex_meta = PROVIDER_META["codex"]
    assert codex_meta["display"] and codex_meta["site_url"] and codex_meta["blurb"]
    assert codex_meta["site_url"].startswith("https://")


def test_handler_routes_registered() -> None:
    import dashboard_web_app as web

    source = Path(web.__file__).read_text(encoding="utf-8")
    assert '"/api/providers"' in source
    assert '"/api/providers/refresh"' in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_dotenv_keys_count_as_configured(tmp_path: Path, monkeypatch) -> None:
    from providers_view import key_presence, load_dotenv_values

    for name in (
        "OPENROUTER_API_KEY",
        "REQUESTY_API_KEY",
        "META_API_KEY",
        "OPENCODE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        '# comment\n\nOPENROUTER_API_KEY="sk-test"\nREQUESTY_API_KEY=\n',
        encoding="utf-8",
    )
    values = load_dotenv_values(tmp_path)
    assert values == {"OPENROUTER_API_KEY": "sk-test", "REQUESTY_API_KEY": ""}
    presence = key_presence(tmp_path)
    assert presence["OPENROUTER_API_KEY"] is True
    assert presence["REQUESTY_API_KEY"] is False
    assert key_presence(tmp_path / "absent-dir")["OPENROUTER_API_KEY"] is False


def test_env_wins_over_dotenv_for_probe_values(tmp_path: Path, monkeypatch) -> None:
    from providers_view import _credentials  # noqa: SLF001 - behavior lives here

    (tmp_path / ".env").write_text("META_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("META_API_KEY", "env-key")
    assert _credentials(tmp_path)["META_API_KEY"] == "env-key"
    monkeypatch.delenv("META_API_KEY")
    assert _credentials(tmp_path)["META_API_KEY"] == "file-key"


def test_status_uses_repo_dotenv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-test\n", encoding="utf-8")
    view = provider_status(tmp_path / "data", tmp_path)
    row = next(p for p in view["providers"] if p["route"] == "openrouter")
    assert row["key_configured"] is True
