"""Normalized subscription-allowance windows (brief 73276c85, answer B).

Native readers report the same idea — how much allowance is left and when
it refreshes — in four different shapes. This module normalizes them into
one :class:`AllowanceWindow` so pre-refresh health checks (deferred by the
brief) can consume every provider through a single model. No new I/O: all
observations flow through the existing native readers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ai_orchestrator import AccessMethod, BillingSource, ExecutionTarget

from ai_provider import account_usage

PROVIDERS = ("codex", "copilot", "kiro", "opencode-go")
_MAX_RESET_UNIX = 253402300799


@dataclass(frozen=True)
class AllowanceWindow:
    """One normalized allowance window for pre-refresh checks."""

    provider: str
    bucket_id: str
    window: str
    used_percent: float | None
    remaining_percent: float | None
    resets_at_utc: str | None
    source: str
    details: dict[str, Any] = field(default_factory=dict)


def _percent(value: Any, name: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"Invalid {name}")
    if not 0 <= value <= 100:
        raise ValueError(f"Invalid {name}")
    return float(value)


def _complement(used: float | None, remaining: float | None) -> tuple[float | None, float | None]:
    """Fill the missing side of a 0-100 percent pair; never invent both."""
    if used is None and remaining is not None:
        return round(100 - remaining, 6), remaining
    if remaining is None and used is not None:
        return used, round(100 - used, 6)
    return used, remaining


def _iso_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def _reset_from_unix(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= _MAX_RESET_UNIX:
        raise ValueError("Invalid quota reset")
    return _iso_utc(datetime.fromtimestamp(value, tz=UTC))


def _reset_from_text(value: Any, *, date_only: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("Invalid quota reset")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid quota reset") from None
    if date_only and len(value) == 10:
        moment = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return _iso_utc(moment)


def normalize_windows(
    provider: str, windows: list[dict[str, Any]], source: str
) -> list[AllowanceWindow]:
    """Normalize one provider's native windows; raises ValueError on bad data."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported allowance provider: {provider!r}")
    normalized = []
    for entry in windows:
        if not isinstance(entry, dict):
            raise ValueError("Invalid allowance window")
        bucket_id = entry.get("bucket_id")
        window = entry.get("window")
        if not isinstance(bucket_id, str) or not bucket_id:
            raise ValueError("Invalid allowance bucket")
        if not isinstance(window, str) or not window:
            raise ValueError("Invalid allowance window")
        if provider == "codex":
            used = _percent(entry.get("used_percent"), "quota percentage")
            remaining: float | None = None
            resets_at = _reset_from_unix(entry.get("resets_at_unix_seconds"))
            details = {
                k: v
                for k, v in entry.items()
                if k not in {"bucket_id", "window", "used_percent", "resets_at_unix_seconds"}
            }
        elif provider == "copilot":
            used = None
            remaining = _percent(entry.get("remaining_percent"), "quota measurement")
            resets_at = _reset_from_text(entry.get("reset_date"))
            details = {
                k: v
                for k, v in entry.items()
                if k not in {"bucket_id", "window", "remaining_percent", "reset_date"}
            }
        elif provider == "kiro":
            # "Credits (X of Y covered in plan), Z%": the plan-covered share
            # still available, i.e. remaining. Owner case-by-case review (brief
            # note) confirms per-provider semantics.
            used = None
            remaining = _percent(entry.get("reported_percent"), "credit measurement")
            resets_at = _reset_from_text(entry.get("reset_date"), date_only=True)
            details = {
                k: v
                for k, v in entry.items()
                if k not in {"bucket_id", "window", "reported_percent", "reset_date"}
            }
        else:
            used = _percent(entry.get("used_percent"), "usage percent")
            remaining = _percent(entry.get("remaining_percent"), "usage percent")
            raw_reset = entry.get("resets_at")
            try:
                resets_at = _reset_from_text(raw_reset)
            except ValueError:
                # Observed (undocumented) endpoint: drift must not break checks.
                resets_at = None
                details = dict(entry)
                details["resets_at_unparsed"] = raw_reset
            else:
                details = {
                    k: v
                    for k, v in entry.items()
                    if k
                    not in {"bucket_id", "window", "used_percent", "remaining_percent", "resets_at"}
                }
        used, remaining = _complement(used, remaining)
        normalized.append(
            AllowanceWindow(
                provider=provider,
                bucket_id=bucket_id,
                window=window,
                used_percent=used,
                remaining_percent=remaining,
                resets_at_utc=resets_at,
                source=source,
                details=details,
            )
        )
    return normalized


def provider_for_target(target: ExecutionTarget) -> str | None:
    """Map an execution target to a normalized provider tag, if supported."""
    if (
        target.access_method is AccessMethod.CODEX_CLI
        and target.billing_source is BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE
    ):
        return "codex"
    if (
        target.access_method is AccessMethod.COPILOT_CLI
        and target.billing_source is BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE
    ):
        return "copilot"
    if (
        target.access_method is AccessMethod.KIRO_CLI
        and target.billing_source is BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE
    ):
        return "kiro"
    if (
        target.access_method is AccessMethod.PROVIDER_API
        and target.billing_source is BillingSource.OPENCODE_GO_SUBSCRIPTION_ALLOWANCE
    ):
        return "opencode-go"
    return None


def read_allowance_windows(target: ExecutionTarget) -> list[AllowanceWindow] | None:
    """Observe and normalize one target's allowance; None when unsupported."""
    provider = provider_for_target(target)
    if provider is None:
        return None
    report = account_usage.read_execution_allowance(target)
    if report is None:
        return None
    windows = report.get("windows")
    if not isinstance(windows, list):
        raise ValueError("Invalid allowance report")
    return normalize_windows(provider, windows, str(report.get("source") or provider))
