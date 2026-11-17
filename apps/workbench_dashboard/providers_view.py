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
    "codex": {
        "display": "Codex",
        "env": None,
        "site_url": "https://openai.com",
        "account_required": True,
        "blurb": "Codex CLI via native login; quota windows only, no model turns.",
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
    allowance_windows: tuple[Mapping[str, Any], ...] = ()

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
            "allowance_windows": [dict(window) for window in self.allowance_windows],
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


def route_ids() -> list[str]:
    """Provider route ids in display order, codex last (no HTTP probe)."""
    return [route for route, _url, _env in ROUTES] + ["codex"]


def _cache_path(data_dir: Path) -> Path:
    return data_dir / CACHE_FILENAME


def load_dotenv_values(repo_root: Path | None) -> dict[str, str]:
    """Read repo .env via the canonical secret-store parser (values in-process)."""
    from ai_provider.secrets import STORE_FILENAME, parse_dotenv_lines

    if repo_root is None:
        return {}
    try:
        text = (Path(repo_root) / STORE_FILENAME).read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_dotenv_lines(text)


def key_presence(repo_root: Path | None = None) -> dict[str, bool]:
    """Which provider keys exist in process env or repo .env (booleans only)."""
    dotenv = load_dotenv_values(repo_root)
    found: dict[str, bool] = {}
    for _route, _url, env_name in ROUTES:
        if env_name:
            found[env_name] = bool(os.environ.get(env_name) or dotenv.get(env_name))
    return found


def _credentials(repo_root: Path | None = None) -> dict[str, str | None]:
    dotenv = load_dotenv_values(repo_root)
    return {
        env_name: os.environ.get(env_name) or dotenv.get(env_name) or None
        for _route, _url, env_name in ROUTES
        if env_name
    }


def _serialize(probes: list[RouteProbe], repo_root: Path | None = None) -> dict[str, Any]:
    presence = key_presence(repo_root)
    rows = []
    for probe in probes:
        env_name = next((env for route, _url, env in ROUTES if route == probe.route), None)
        rows.append(
            ProviderView.from_probe(
                probe, key_configured=bool(env_name and presence.get(env_name))
            ).to_json()
        )
    return {"providers": rows}


def codex_view(report: Mapping[str, Any]) -> ProviderView:
    """Map one native Codex allowance report onto a provider row.

    Codex is a CLI subscription, not an HTTP route, so it never goes
    through probe_all; availability means the CLI ran and native login
    answered with quota windows.
    """
    from datetime import UTC, datetime

    meta = PROVIDER_META.get("codex", {})
    available = report.get("status") == "available"
    windows = report.get("windows") or []
    checked_at = report.get("observed_at_utc") or datetime.now(UTC).isoformat()
    return ProviderView(
        route="codex",
        display=str(meta.get("display", "codex")),
        account_required=bool(meta.get("account_required", True)),
        key_configured=available,
        site_url=str(meta.get("site_url", "")),
        blurb=str(meta.get("blurb", "")),
        reachable=True if available else False,
        auth_ok=True if available else None,
        model_count=None,
        sample_ids=(),
        latency_ms=None,
        checked_at=checked_at,
        error=None if available else str(report.get("reason") or "unknown"),
        allowance_windows=tuple(windows),
    )


def read_codex_report() -> Mapping[str, Any]:
    """Read one live Codex allowance report; never raises (degrades)."""
    from ai_provider.codex_usage import read_codex_allowance

    try:
        return read_codex_allowance()
    except Exception as error:  # noqa: BLE001 - one route must not kill the sweep
        return {"status": "unknown", "reason": type(error).__name__, "windows": []}


OPENCODE_USAGE_ENV = "OPENCODE_USAGE_KEY"


def read_opencode_report(repo_root: Path | None = None) -> Mapping[str, Any]:
    """Read Go usage via the scoped key; never raises (degrades).

    The inference key cannot read usage (403); this needs the separate
    least-privilege Usage-Read key. Absent key degrades with a reason.
    """
    import os

    from ai_provider.go_source_info import read_opencode_go_allowance

    key = os.environ.get(OPENCODE_USAGE_ENV) or load_dotenv_values(repo_root).get(
        OPENCODE_USAGE_ENV
    )
    if not key:
        return {"status": "unknown", "reason": "usage_key_not_configured", "windows": []}
    try:
        report = read_opencode_go_allowance(api_key=key)
    except Exception as error:  # noqa: BLE001 - one route must not kill the sweep
        return {"status": "unknown", "reason": type(error).__name__, "windows": []}
    if not isinstance(report, dict) or report.get("status") != "observed":
        return {"status": "unknown", "reason": "usage_unavailable", "windows": []}
    return report


def load_cached(data_dir: Path) -> dict[str, Any] | None:
    """Return the cached snapshot, or None when missing/unreadable."""
    try:
        raw = json.loads(_cache_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        return None
    return raw


def provider_status(data_dir: Path, repo_root: Path | None = None) -> dict[str, Any]:
    """Serve the cached snapshot; never probes (safe for every page load)."""
    cached = load_cached(data_dir)
    if cached is not None:
        return {"ok": True, **cached, "cached": True}
    presence = key_presence(repo_root)
    rows = []
    for route, _url, env_name in ROUTES:
        rows.append(
            ProviderView.unchecked(
                route, key_configured=bool(env_name and presence.get(env_name))
            ).to_json()
        )
    rows.append(ProviderView.unchecked("codex", key_configured=False).to_json())
    return {"ok": True, "providers": rows, "cached": False}


def _attach_opencode_windows(rows: list[dict[str, Any]], report: Mapping[str, Any]) -> None:
    """Attach Go usage windows to the opencode row (usage failure never hides probe)."""
    for row in rows:
        if row.get("route") != "opencode_go":
            continue
        windows = report.get("windows") or []
        row["allowance_windows"] = [dict(window) for window in windows if isinstance(window, dict)]
        if not row["allowance_windows"] and not row.get("error"):
            row["error"] = f"usage: {report.get('reason') or 'unknown'}"


def refresh_provider_status(
    data_dir: Path,
    repo_root: Path | None = None,
    *,
    probe: Callable[[Mapping[str, str | None]], list[RouteProbe]] | None = None,
    codex_probe: Callable[[], Mapping[str, Any]] | None = None,
    opencode_probe: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one live probe sweep, cache it atomically, and return the view."""
    from ai_provider.route_probe import probe_all

    sweep = probe or probe_all
    snapshot = _serialize(list(sweep(_credentials(repo_root))), repo_root)
    codex_sweep = codex_probe or read_codex_report
    snapshot["providers"].append(codex_view(codex_sweep()).to_json())
    opencode_sweep = opencode_probe or (lambda: read_opencode_report(repo_root))
    _attach_opencode_windows(snapshot["providers"], opencode_sweep())
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
