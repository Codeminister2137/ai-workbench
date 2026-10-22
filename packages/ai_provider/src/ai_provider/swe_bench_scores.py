"""Published SWE-bench capability results as a dated selection prior.

Reads the public SWE-bench leaderboard data published by the benchmark project
(``data/leaderboards.json`` in the licensed ``swe-bench.github.io`` repository)
and normalizes the rows into the shared :class:`CapabilityScore` record.

Two properties of the source shape the record and must not be lost:

- A row is a **(model, agent scaffold)** pair, not a model alone. The same
  model appears under several scaffolds with different scores, so the scaffold
  is part of every record and a score must never be read as a model-only claim.
- The published model names are not normalized: the same model appears as
  "GLM 4.5" and "GLM-4.5". The record keeps the published spelling and adds a
  comparable key derived from it.

This is a public, read-only fetch. No prompt, credential, repository content or
model call is involved. The returned record is JSON-safe and safe to persist;
the caller owns any cache. Published results are a selection prior, not
acceptance evidence for this repository.
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

from ai_provider.http_transport import urlopen
from ai_provider.source_info import CapabilityPrior, CapabilityScore, _utc_now

SOURCE = "swe_bench"
BENCHMARK = "SWE-bench"
LEADERBOARD_URL = (
    "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json"
)
_MAX_BYTES = 8_388_608
DEFAULT_SPLIT = "Verified"


def _normalized_model(display: str) -> str:
    """Return a comparable key for a published model display name.

    Only case, separators and spacing are normalized. The result is a display
    key, not a resolved model identity: mapping a route to an upstream model
    is a separate, dated decision.
    """

    collapsed = display.strip().lower()
    for separator in ("-", "_"):
        collapsed = collapsed.replace(separator, " ")
    return " ".join(collapsed.split())


def _text(row: dict[str, Any], name: str) -> str | None:
    value = row.get(name)
    return value if isinstance(value, str) and value.strip() else None


def _number(row: dict[str, Any], name: str) -> float | None:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    candidate = float(value)
    return candidate if math.isfinite(candidate) else None


def _parse_row(
    row: object, *, split: str, source_url: str, observed_at_utc: str
) -> CapabilityScore | None:
    if not isinstance(row, dict):
        return None
    display = _text(row, "model_display")
    if display is None:
        return None
    checked = row.get("checked")
    return CapabilityScore(
        source=SOURCE,
        benchmark=BENCHMARK,
        split=split,
        model=_normalized_model(display),
        model_display=display,
        agent=_text(row, "agent"),
        agent_org=_text(row, "agent_org"),
        score=_number(row, "resolved"),
        scale="percent_resolved",
        measured_at=_text(row, "date"),
        verified=checked if type(checked) is bool else None,
        cost_usd=_number(row, "cost"),
        warning=_text(row, "warning"),
        source_url=source_url,
        observed_at_utc=observed_at_utc,
    )


def read_swe_bench_scores(
    split: str = DEFAULT_SPLIT, *, timeout_seconds: float = 30, source_url: str = LEADERBOARD_URL
) -> CapabilityPrior:
    """Read the published results for one SWE-bench leaderboard split.

    The leaderboard data is public and needs no credential. Socket timeouts
    bound the single request; callers own the total process deadline. An
    unknown split is reported as unavailable rather than guessed.
    """

    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (float, int))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("Metadata timeout must be finite and positive")
    if not isinstance(split, str) or not split.strip():
        raise ValueError("Split must be a non-empty string")
    requested = split.strip()

    observed_at = _utc_now()
    request = Request(source_url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read(_MAX_BYTES + 1)
        if len(body) > _MAX_BYTES:
            raise ValueError("Leaderboard response exceeded byte bound")
        raw = json.loads(body.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Invalid leaderboard envelope")
        leaderboards = raw.get("leaderboards")
        if not isinstance(leaderboards, list):
            raise ValueError("Invalid leaderboard list")
        rows: list[object] | None = None
        available: list[str] = []
        for leaderboard in leaderboards:
            if not isinstance(leaderboard, dict):
                continue
            name = leaderboard.get("name")
            if not isinstance(name, str):
                continue
            available.append(name)
            if name == requested:
                results = leaderboard.get("results")
                rows = results if isinstance(results, list) else []
        if rows is None:
            return CapabilityPrior(
                status="unavailable",
                source=SOURCE,
                benchmark=BENCHMARK,
                split=requested,
                observed_at_utc=observed_at,
                reason="unknown_split",
                source_url=source_url,
            )
        scores = tuple(
            score
            for score in (
                _parse_row(row, split=requested, source_url=source_url, observed_at_utc=observed_at)
                for row in rows
            )
            if score is not None
        )
    except (OSError, ValueError, TypeError) as error:
        reason = "metadata_request_failed"
        if isinstance(error, HTTPError):
            if error.code == 404:
                reason = "source_not_found"
            elif error.code == 401:
                reason = "authentication_failed"
            elif error.code == 403:
                reason = "permission_denied"
        return CapabilityPrior(
            status="unavailable",
            source=SOURCE,
            benchmark=BENCHMARK,
            split=requested,
            observed_at_utc=observed_at,
            reason=reason,
            source_url=source_url,
        )
    return CapabilityPrior(
        status="observed",
        source=SOURCE,
        benchmark=BENCHMARK,
        split=requested,
        scores=scores,
        observed_at_utc=observed_at,
        reason=None,
        source_url=source_url,
    )


def main() -> int:
    """Print closed capability fields only; no raw response output."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--timeout-seconds", type=float, default=30)
    args = parser.parse_args()
    result = read_swe_bench_scores(args.split, timeout_seconds=args.timeout_seconds)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.status == "observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
