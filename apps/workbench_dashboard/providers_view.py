"""Provider connection status for the dashboard.

Read-only, cost-free signals only: each probe is a single HTTP GET against a
provider's model-list endpoint (no inference, no spend). Live probes run only
when the owner clicks Refresh; the GET endpoint serves the cached snapshot so
page loads never touch the network.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_provider.route_probe import ROUTES, RouteProbe

CACHE_FILENAME = "providers.json"

PROVIDER_META: Mapping[str, Mapping[str, Any]] = {
    "openrouter": {
        "display": "OpenRouter",
        "env": "OPENROUTER_API_KEY",
        "site_url": "https://openrouter.ai",
        "account_required": True,
        "blurb": "Cloud gateway with many models behind one key.",
    },
    "requesty": {
        "display": "Requesty",
        "env": "REQUESTY_API_KEY",
        "site_url": "https://requesty.ai",
        "account_required": True,
        "blurb": "Cloud gateway with routing and fallbacks.",
    },
    "meta": {
        "display": "Meta",
        "env": "META_API_KEY",
        "site_url": "https://meta.ai",
        "account_required": True,
        "blurb": "Meta Models API; this checkout spends a finite free grant.",
    },
    "opencode_go": {
        "display": "OpenCode",
        "env": "OPENCODE_API_KEY",
        "site_url": "https://opencode.ai",
        "account_required": True,
        "blurb": "OpenCode inference service.",
    },
    "ollama": {
        "display": "Ollama (local)",
        "env": None,
        "site_url": "https://ollama.com",
        "account_required": False,
        "blurb": "Local models on this PC; no account or key needed.",
    },
}


@dataclass(frozen=True)
class ProviderView:
    """One serializable provider row; never carries secret values."""

    route: str
    display: str
    account_required: bool
    key_configured: bool
    site_url: str
    blurb: str
    reachable: bool | None
    auth_ok: bool | None
    model_count: int | None
    sample_ids: tuple[str, ...]
    latency_ms: int | None
    checked_at: str | None
    error: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "display": self.display,
            "account_required": self.account_required,
            "key_configured": self.key_configured,
            "site_url": self.site_url,
            "blurb": self.blurb,
            "reachable": self.reachable,
            "auth_ok": self.auth_ok,
            "model_count": self.model_count,
            "sample_ids": list(self.sample_ids),
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
            "error": self.error,
        }

    @classmethod
    def from_probe(cls, probe: RouteProbe, *, key_configured: bool) -> ProviderView:
        meta = PROVIDER_META.get(probe.route, {})
        return cls(
            route=probe.route,
            display=str(meta.get("display", probe.route)),
            account_required=bool(meta.get("account_required", True)),
            key_configured=key_configured,
            site_url=str(meta.get("site_url", "")),
            blurb=str(meta.get("blurb", "")),
            reachable=probe.reachable,
            auth_ok=probe.auth_ok,
            model_count=probe.models_seen,
            sample_ids=tuple(probe.sample_ids),
            latency_ms=probe.latency_ms,
            checked_at=probe.checked_utc,
            error=probe.error,
        )

    @classmethod
    def unchecked(cls, route: str, *, key_configured: bool) -> ProviderView:
        meta = PROVIDER_META.get(route, {})
        return cls(
            route=route,
            display=str(meta.get("display", route)),
            account_required=bool(meta.get("account_required", True)),
            key_configured=key_configured,
            site_url=str(meta.get("site_url", "")),
            blurb=str(meta.get("blurb", "")),
            reachable=None,
            auth_ok=None,
            model_count=None,
            sample_ids=(),
            latency_ms=None,
            checked_at=None,
            error=None,
        )


def _cache_path(data_dir: Path) -> Path:
    return data_dir / CACHE_FILENAME


def key_presence() -> dict[str, bool]:
    """Which provider env keys are set (booleans only; values never leave)."""
    found: dict[str, bool] = {}
    for _route, _url, env_name in ROUTES:
        if env_name:
            found[env_name] = bool(os.environ.get(env_name))
    return found


def _credentials() -> dict[str, str | None]:
    return {
        env_name: os.environ.get(env_name) or None for _route, _url, env_name in ROUTES if env_name
    }


def _serialize(probes: list[RouteProbe]) -> dict[str, Any]:
    presence = key_presence()
    rows = []
    for probe in probes:
        env_name = next((env for route, _url, env in ROUTES if route == probe.route), None)
        rows.append(
            ProviderView.from_probe(
                probe, key_configured=bool(env_name and presence.get(env_name))
            ).to_json()
        )
    return {"providers": rows}


def load_cached(data_dir: Path) -> dict[str, Any] | None:
    """Return the cached snapshot, or None when missing/unreadable."""
    try:
        raw = json.loads(_cache_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        return None
    return raw


def provider_status(data_dir: Path) -> dict[str, Any]:
    """Serve the cached snapshot; never probes (safe for every page load)."""
    cached = load_cached(data_dir)
    if cached is not None:
        return {"ok": True, **cached, "cached": True}
    presence = key_presence()
    rows = []
    for route, _url, env_name in ROUTES:
        rows.append(
            ProviderView.unchecked(
                route, key_configured=bool(env_name and presence.get(env_name))
            ).to_json()
        )
    return {"ok": True, "providers": rows, "cached": False}


def refresh_provider_status(
    data_dir: Path,
    *,
    probe: Callable[[Mapping[str, str | None]], list[RouteProbe]] | None = None,
) -> dict[str, Any]:
    """Run one live probe sweep, cache it atomically, and return the view."""
    from ai_provider.route_probe import probe_all

    sweep = probe or probe_all
    snapshot = _serialize(list(sweep(_credentials())))
    path = _cache_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return {"ok": True, **snapshot, "cached": False}
