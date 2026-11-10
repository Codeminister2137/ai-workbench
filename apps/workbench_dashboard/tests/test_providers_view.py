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
    ]
    assert all(p["checked_at"] is None for p in view["providers"])
    assert all(p["key_configured"] is False for p in view["providers"])


def test_refresh_caches_and_serves_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-value")
    view = refresh_provider_status(tmp_path, probe=_stub)
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
    view = refresh_provider_status(tmp_path, probe=_stub)
    dumped = json.dumps(view)
    assert "sk-secret-abc123" not in dumped
    dumped_cache = (tmp_path / "providers.json").read_text(encoding="utf-8")
    assert "sk-secret-abc123" not in dumped_cache


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


def test_handler_routes_registered() -> None:
    import dashboard_web_app as web

    source = Path(web.__file__).read_text(encoding="utf-8")
    assert '"/api/providers"' in source
    assert '"/api/providers/refresh"' in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_dotenv_keys_count_as_configured(tmp_path: Path, monkeypatch) -> None:
    from providers_view import key_presence, load_dotenv_values

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
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
