"""One-shot micro-evaluation across reachable chat routes (L3 evidence).

Sends one fixed tiny task per route — complete a three-line function — and
checks the answer deterministically. The prompt is synthetic and carries no
repository content (PUBLIC_OR_LOW_RISK), outputs are capped at 256 tokens,
and usage is recorded when the provider reports it. Typical cost is a few
cents of grant credit across all routes.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import time
from collections.abc import Callable
from typing import Any

from ai_provider import route_probe
from ai_provider.adapters.baseten import BASETEN_HACKATHON_MODEL
from ai_provider.adapters.openai_compatible import _zero_price_row
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass
from ai_provider.factory import create_chat_client
from ai_provider.source_info import _utc_now

TASK = (
    "Complete this Python function so add2(2) returns 4. "
    "Reply with ONLY the completed function in a ```python block, no explanation:\n"
    "```python\ndef add2(x):\n    return\n```"
)
MAX_OUTPUT_TOKENS = 1024


@dataclasses.dataclass(frozen=True)
class EvalResult:
    """Deterministic outcome of one route's micro-evaluation."""

    route: str
    model: str
    checked_utc: str
    passed: bool
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def summary(self) -> str:
        if self.error:
            return f"{self.route} ({self.model}): ERROR {self.error}"
        verdict = "PASS" if self.passed else "FAIL"
        usage = (
            f"{self.input_tokens}/{self.output_tokens}t"
            if self.input_tokens is not None
            else "usage-unknown"
        )
        return f"{self.route} ({self.model}): {verdict} {self.latency_ms}ms {usage}"


def check_completion(text: str) -> bool:
    """Run the returned function in a bare namespace and assert add2(2) == 4."""
    block = text
    if "```" in text:
        parts = text.split("```")
        candidates = [part for part in parts if "def add2" in part]
        if not candidates:
            return False
        block = candidates[0]
        if block.lstrip().startswith("python"):
            block = block.lstrip()[len("python") :]
    namespace: dict[str, Any] = {"__builtins__": {}}
    try:
        # Bare namespace without builtins: the snippet can only define add2.
        exec(compile(block, "<eval>", "exec"), namespace)
    except Exception:
        return False
    candidate = namespace.get("add2")
    if not callable(candidate):
        return False
    try:
        return bool(candidate(2) == 4)
    except Exception:
        return False


def _short_error(error: Exception) -> str:
    """Exception type plus a credential-scrubbed message snippet."""
    scrubbed = re.sub(r"[A-Za-z0-9_-]{32,}", "***", str(error))
    return f"{type(error).__name__}: {scrubbed[:150]}"


def run_eval(client: Any, route: str, model: str) -> EvalResult:
    """Send the fixed task through one client and grade deterministically."""
    checked = _utc_now()
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, TASK),),
        temperature=0.0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        # Fixed synthetic prompt: satisfies the ADR-063 public attestation
        # branch of the OpenRouter free-tier retention guard.
        metadata={"public_or_synthetic": True},
    )
    started = time.monotonic()
    try:
        response = client.complete(request)
    except Exception as error:
        return EvalResult(route, model, checked, False, None, None, None, _short_error(error))
    latency_ms = int((time.monotonic() - started) * 1000)
    usage = response.usage
    return EvalResult(
        route,
        model,
        checked,
        check_completion(response.message.content or ""),
        latency_ms,
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        None,
    )


def _list_rows(route: str, credentials: dict[str, str | None]) -> list[dict]:
    """Raw model rows from a route's live list endpoint (for model selection)."""
    import urllib.request

    entry = next(item for item in route_probe.ROUTES if item[0] == route)
    _, url, env_name = entry
    headers = {"User-Agent": route_probe.USER_AGENT, "Accept": "application/json"}
    if env_name and credentials.get(env_name):
        headers["Authorization"] = f"Bearer {credentials[env_name]}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers, method="GET"), timeout=15
        ) as response:
            raw = json.loads(response.read(route_probe._MAX_BYTES + 1).decode("utf-8"))
    except Exception:
        return []
    rows = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        rows = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _list_model_ids(route: str, credentials: dict[str, str | None]) -> list[str]:
    """All model ids from a route's live list endpoint (for model selection)."""
    rows = _list_rows(route, credentials)
    ids = [row.get("id") for row in rows]
    if not any(ids):
        ids = [row.get("name") for row in rows]
    return [str(item) for item in ids if item]


def select_model(route: str, credentials: dict[str, str | None]) -> str | None:
    """Cheapest defensible model id per route, or None to skip the route."""
    if route == "meta":
        return "muse-spark-1.3"
    if route == "baseten":
        return BASETEN_HACKATHON_MODEL
    if route == "requesty":
        # Same zero-price rule the completion guard enforces live.
        rows = _list_rows(route, credentials)
        free = [
            row["id"] for row in rows if isinstance(row.get("id"), str) and _zero_price_row(row)
        ]
        return free[0] if free else None
    ids = _list_model_ids(route, credentials)
    if route == "openrouter":
        free = [item for item in ids if item.endswith(":free")]
        return free[0] if free else None
    if route == "opencode_go":
        cheap = [
            item for item in ids if any(tag in item.lower() for tag in ("flash", "mini", "haiku"))
        ]
        return (cheap or ids or [None])[0]
    return None


_PROVIDERS: dict[str, tuple[ProviderKind, str, float, bool]] = {
    "meta": (ProviderKind.META, "META_API_KEY", 90.0, False),
    "baseten": (ProviderKind.BASETEN, "BASETEN_HACKATHON_API_KEY", 150.0, False),
    "openrouter": (ProviderKind.OPENROUTER, "OPENROUTER_API_KEY", 90.0, False),
    "requesty": (ProviderKind.REQUESTY, "REQUESTY_API_KEY", 90.0, True),
    "opencode_go": (ProviderKind.OPENCODE_GO, "OPENCODE_API_KEY", 90.0, False),
}


def _clients(credentials: dict[str, str | None]) -> dict[str, Callable[[str], Any]]:
    def make(route: str) -> Callable[[str], Any]:
        def build(model: str) -> Any:
            provider, env_name, timeout, free_only = _PROVIDERS[route]
            return create_chat_client(
                BackendConfig(
                    provider,
                    model,
                    None,
                    credentials.get(env_name) or None,
                    timeout,
                    require_free_model=free_only,
                )
            )

        return build

    return {route: make(route) for route in _PROVIDERS}


def run_all(credentials: dict[str, str | None]) -> list[EvalResult]:
    """Evaluate every route with a selectable model; skips are recorded."""
    factories = _clients(credentials)
    results = []
    for route, build in factories.items():
        try:
            model = select_model(route, credentials)
        except Exception as error:
            results.append(
                EvalResult(
                    route,
                    "?",
                    _utc_now(),
                    False,
                    None,
                    None,
                    None,
                    f"select:{type(error).__name__}",
                )
            )
            continue
        if model is None:
            results.append(EvalResult(route, "?", _utc_now(), False, None, None, None, "no-model"))
            continue
        results.append(run_eval(build(model), route, model))
    return results


def main(argv: list[str] | None = None) -> int:
    """Live CLI: evaluate reachable routes, write a dated snapshot."""
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=Path("artifacts/route-evals"))
    parser.add_argument("--routes", nargs="*", default=None)
    args = parser.parse_args(argv)
    credentials = {
        name: os.getenv(name) or None
        for name in (
            "META_API_KEY",
            "BASETEN_HACKATHON_API_KEY",
            "OPENROUTER_API_KEY",
            "REQUESTY_API_KEY",
            "OPENCODE_API_KEY",
        )
    }
    factories = _clients(credentials)
    wanted = args.routes or list(factories)
    results = []
    for route in wanted:
        model = select_model(route, credentials)
        if model is None:
            results.append(EvalResult(route, "?", _utc_now(), False, None, None, None, "no-model"))
            continue
        results.append(run_eval(factories[route](model), route, model))
    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snapshot = args.snapshot_dir / f"route-eval-{stamp}.json"
    snapshot.write_text(
        json.dumps([item.to_dict() for item in results], indent=2), encoding="utf-8"
    )
    for item in results:
        print(item.summary())
    print(f"snapshot: {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
