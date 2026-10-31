"""Live route reachability sweep over declared provider list endpoints.

Free metadata only: GET each provider's model-list endpoint (or the local
Ollama tag list) and record reachable/auth/models-seen/latency. Sends no
prompt, runs no inference, spends nothing. Credentials are passed in by the
caller (the live CLI reads them from the environment), never read here,
never logged, never persisted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from ai_provider.adapters.meta import META_BASE_URL
from ai_provider.adapters.openrouter import BASE_URL as OPENROUTER_BASE_URL
from ai_provider.go_source_info import GO_INFERENCE_BASE_URL
from ai_provider.http_transport import urlopen
from ai_provider.source_info import _utc_now

OLLAMA_BASE_URL = "http://localhost:11434"
REQUESTY_BASE_URL = "https://router.requesty.ai/v1"
USER_AGENT = "ai-workbench-route-probe/1.0"
_MAX_BYTES = 2_097_152


@dataclasses.dataclass(frozen=True)
class RouteProbe:
    """One observed list-endpoint check for a declared route."""

    route: str
    url: str
    checked_utc: str
    reachable: bool
    auth_ok: bool | None
    models_seen: int | None
    sample_ids: tuple[str, ...]
    latency_ms: int | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["sample_ids"] = list(self.sample_ids)
        return payload

    def summary(self) -> str:
        if not self.reachable:
            return f"{self.route}: unreachable ({self.error})"
        auth = (
            "auth-ok" if self.auth_ok else ("auth-refused" if self.auth_ok is False else "no-key")
        )
        seen = self.models_seen if self.models_seen is not None else "?"
        return f"{self.route}: {auth}, {seen} models, {self.latency_ms}ms"


def _extract_ids(raw: Any) -> tuple[int, tuple[str, ...]] | None:
    """Model count and sample ids from an OpenAI- or Ollama-shaped envelope."""
    rows = raw.get("data") if isinstance(raw, dict) else None
    key = "id"
    if not isinstance(rows, list):
        rows = raw.get("models") if isinstance(raw, dict) else None
        key = "name"
    if not isinstance(rows, list):
        return None
    ids = tuple(str(row[key]) for row in rows if isinstance(row, dict) and row.get(key))
    return (len(rows), ids[:5])


def probe_route(
    route: str,
    url: str,
    *,
    api_key: str | None = None,
    timeout_seconds: float = 15,
) -> RouteProbe:
    """GET one list endpoint and record the observed reachability signal."""
    checked = _utc_now()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    started = time.monotonic()
    try:
        request = Request(url, headers=headers, method="GET")
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(_MAX_BYTES + 1)
        latency_ms = int((time.monotonic() - started) * 1000)
    except HTTPError as error:
        latency_ms = int((time.monotonic() - started) * 1000)
        if error.code in (401, 403):
            return RouteProbe(
                route, url, checked, True, False, None, (), latency_ms, f"http-{error.code}"
            )
        return RouteProbe(
            route, url, checked, True, None, None, (), latency_ms, f"http-{error.code}"
        )
    except (URLError, OSError, ValueError) as error:
        return RouteProbe(
            route, url, checked, False, None, None, (), None, f"{type(error).__name__}"
        )
    if len(body) > _MAX_BYTES:
        return RouteProbe(route, url, checked, True, None, None, (), latency_ms, "oversized")
    try:
        raw = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return RouteProbe(route, url, checked, True, None, None, (), latency_ms, "invalid-json")
    extracted = _extract_ids(raw)
    if extracted is None:
        return RouteProbe(
            route, url, checked, True, None, None, (), latency_ms, "unrecognized-shape"
        )
    count, sample = extracted
    return RouteProbe(
        route, url, checked, True, True if api_key else None, count, sample, latency_ms, None
    )


ROUTES: tuple[tuple[str, str, str | None], ...] = (
    ("openrouter", f"{OPENROUTER_BASE_URL}/models", "OPENROUTER_API_KEY"),
    ("requesty", f"{REQUESTY_BASE_URL}/models", "REQUESTY_API_KEY"),
    ("meta", f"{META_BASE_URL}/models", "META_API_KEY"),
    ("opencode_go", f"{GO_INFERENCE_BASE_URL}/v1/models", "OPENCODE_API_KEY"),
    ("ollama", f"{OLLAMA_BASE_URL}/api/tags", None),
)


def probe_all(credentials: dict[str, str | None]) -> list[RouteProbe]:
    """Probe every declared route; one entry per route, never raises."""
    found = []
    for route, url, env_name in ROUTES:
        key = credentials.get(env_name) if env_name else None
        try:
            found.append(probe_route(route, url, api_key=key or None))
        except Exception as error:  # noqa: BLE001 - one route must not kill the sweep
            found.append(
                RouteProbe(
                    route, url, _utc_now(), False, None, None, (), None, type(error).__name__
                )
            )
    return found


def main(argv: list[str] | None = None) -> int:
    """Live CLI: read keys from the environment, sweep, write a snapshot."""
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=Path("artifacts/route-probes"))
    args = parser.parse_args(argv)
    credentials = {name: os.getenv(name) or None for _, _, name in ROUTES if name is not None}
    results = probe_all(credentials)
    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snapshot = args.snapshot_dir / f"route-probe-{stamp}.json"
    snapshot.write_text(
        json.dumps([item.to_dict() for item in results], indent=2), encoding="utf-8"
    )
    for item in results:
        print(item.summary())
    print(f"snapshot: {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
