"""Local user preferences, separate from shared catalogs and backend credentials."""

from __future__ import annotations

import argparse
import math
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from ai_agent.permissions import ApprovalPolicyPreset
from ai_orchestrator import BillingSource, CostPolicyTier, PrivacyClass, QualityThreshold
from ai_orchestrator.fallback import FallbackQualityPolicy

from ai_provider.repo_context import (
    DEFAULT_CONTEXT_BUDGET_CHARS,
    DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
    DEFAULT_INSTRUCTION_BUDGET_CHARS,
)

EXECUTION_DEFAULT_KEYS = frozenset(
    {
        "quality",
        "privacy",
        "approval_policy",
        "context_budget_chars",
        "context_file_budget_chars",
        "instruction_budget_chars",
        "timeout_seconds",
        "validation_timeout_seconds",
        "max_repair_cycles",
    }
)


@dataclass(frozen=True)
class SpendingExemption:
    """One owner-admitted billing source despite the task cost tier.

    Covers finite free grants (expiry enforced automatically). Balances are
    informational only until settlement wiring lands; the owner updates or
    removes the rule when the grant depletes.
    """

    billing_source: str
    balance_cents: int | None = None
    expires_at: float | None = None
    note: str = ""


@dataclass(frozen=True)
class UserConfig:
    """Typed preferences; new preference groups can be added as needs arise."""

    cost_policy: CostPolicyTier = CostPolicyTier.PREPAID_CREDITS_ALLOWED
    spending_exemptions: tuple[SpendingExemption, ...] = ()
    fallback_enabled: bool = True
    fallback_quality_policy: FallbackQualityPolicy = FallbackQualityPolicy.EMERGENCY_PRESERVE
    fallback_priority: tuple[str, ...] = ()
    fallback_exclude: tuple[str, ...] = ()
    fallback_allow_cost_escalation: bool = False
    quality: QualityThreshold = QualityThreshold.STANDARD
    privacy: PrivacyClass = PrivacyClass.EXTERNAL_ALLOWED
    approval_policy: ApprovalPolicyPreset = ApprovalPolicyPreset.INTERACTIVE
    context_budget_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS
    context_file_budget_chars: int = DEFAULT_CONTEXT_FILE_BUDGET_CHARS
    instruction_budget_chars: int = DEFAULT_INSTRUCTION_BUDGET_CHARS
    timeout_seconds: float = 180.0
    validation_timeout_seconds: float = 300.0
    max_repair_cycles: int = 3
    configured_defaults: frozenset[str] = frozenset()


def active_cost_exemptions(config: UserConfig, *, now: float | None = None) -> frozenset[str]:
    """Billing sources admitted right now; expired exemptions fail closed."""
    moment = time.time() if now is None else now
    return frozenset(
        item.billing_source
        for item in config.spending_exemptions
        if item.expires_at is None or moment < item.expires_at
    )


def _spending_exemptions(spending: dict[str, object]) -> tuple[SpendingExemption, ...]:
    if set(spending) - {"exemptions"}:
        raise ValueError("Unknown spending keys; supported: exemptions")
    raw_rules = spending.get("exemptions", [])
    if not isinstance(raw_rules, list):
        raise ValueError("spending.exemptions must be a list")
    rules: list[SpendingExemption] = []
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ValueError(f"spending rule #{index} must be a table")
        unknown = sorted(set(raw) - {"billing_source", "balance_cents", "expires_at", "note"})
        if unknown:
            raise ValueError(f"spending rule #{index} unknown keys: {unknown}")
        source = raw.get("billing_source")
        if not isinstance(source, str):
            raise ValueError(f"spending rule #{index} needs a billing_source")
        try:
            BillingSource(source)
        except ValueError:
            valid = ", ".join(item.value for item in BillingSource)
            raise ValueError(
                f"spending rule #{index} unknown billing_source; valid: {valid}"
            ) from None
        balance = raw.get("balance_cents")
        if balance is not None and (not isinstance(balance, int) or balance < 0):
            raise ValueError(f"spending rule #{index} balance_cents must be >= 0")
        expires = raw.get("expires_at")
        expires_at: float | None = None
        if expires is not None:
            if isinstance(expires, (int, float)):
                expires_at = float(expires)
            elif isinstance(expires, str):
                try:
                    parsed = datetime.fromisoformat(expires)
                except ValueError:
                    raise ValueError(
                        f"spending rule #{index} expires_at must be ISO or epoch"
                    ) from None
                if parsed.tzinfo is None:
                    raise ValueError(f"spending rule #{index} expires_at needs a timezone offset")
                expires_at = parsed.timestamp()
            else:
                raise ValueError(f"spending rule #{index} expires_at must be ISO or epoch")
        note = raw.get("note", "")
        if not isinstance(note, str):
            raise ValueError(f"spending rule #{index} note must be a string")
        rules.append(
            SpendingExemption(
                billing_source=source,
                balance_cents=balance,
                expires_at=expires_at,
                note=note,
            )
        )
    return tuple(rules)


def apply_user_defaults(args: argparse.Namespace, config: UserConfig) -> None:
    """Apply preferences while retaining every explicitly supplied CLI value."""
    provided = getattr(args, "_provided_user_defaults", frozenset())
    for key in EXECUTION_DEFAULT_KEYS - provided:
        value = getattr(config, key)
        setattr(args, key, value.value if isinstance(value, StrEnum) else value)
    args._configured_user_defaults = config.configured_defaults


def _route_id_list(fallback: dict[str, object], key: str) -> tuple[str, ...]:
    """Validate one ordered route-id list without accepting duplicates."""
    value = fallback.get(key, ())
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"fallback.{key} must be a list of non-empty route id strings")
    if len(set(value)) != len(value):
        raise ValueError(f"fallback.{key} must not repeat a route id")
    return tuple(value)


def load_user_config(path: Path, *, required: bool = False) -> UserConfig:
    """Load TOML preferences, rejecting invalid values and misspelled settings."""

    if not path.exists() and not required:
        return UserConfig()
    with path.open("rb") as source:
        data = tomllib.load(source)
    if set(data) - {"defaults", "fallback", "spending"}:
        raise ValueError(
            "Unknown user config section; supported sections: defaults, fallback, spending"
        )
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict) or set(defaults) - (EXECUTION_DEFAULT_KEYS | {"cost_policy"}):
        raise ValueError("Unknown user config defaults setting")
    base = UserConfig()
    for key, minimum in (
        ("context_budget_chars", 0),
        ("context_file_budget_chars", 1),
        ("instruction_budget_chars", 1),
        ("max_repair_cycles", -1),
    ):
        value = defaults.get(key, getattr(base, key))
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"defaults.{key} must be an integer >= {minimum}")
    for key in ("timeout_seconds", "validation_timeout_seconds"):
        value = defaults.get(key, getattr(base, key))
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"defaults.{key} must be a finite positive number")
    fallback = data.get("fallback", {})
    if not isinstance(fallback, dict) or set(fallback) - {
        "enabled",
        "quality_policy",
        "priority",
        "exclude",
        "allow_cost_escalation",
    }:
        raise ValueError(
            "User config fallback supports only enabled, quality_policy, "
            "priority, exclude and allow_cost_escalation"
        )
    enabled = fallback.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("fallback.enabled must be a boolean")
    allow_cost_escalation = fallback.get("allow_cost_escalation", False)
    if not isinstance(allow_cost_escalation, bool):
        raise ValueError("fallback.allow_cost_escalation must be a boolean")
    priority = _route_id_list(fallback, "priority")
    exclude = _route_id_list(fallback, "exclude")
    spending = data.get("spending", {})
    if not isinstance(spending, dict):
        raise ValueError("spending must be a table")
    return UserConfig(
        quality=QualityThreshold(defaults.get("quality", base.quality.value)),
        spending_exemptions=_spending_exemptions(spending),
        privacy=PrivacyClass(defaults.get("privacy", base.privacy.value)),
        approval_policy=ApprovalPolicyPreset(
            defaults.get("approval_policy", base.approval_policy.value)
        ),
        context_budget_chars=defaults.get("context_budget_chars", base.context_budget_chars),
        context_file_budget_chars=defaults.get(
            "context_file_budget_chars", base.context_file_budget_chars
        ),
        instruction_budget_chars=defaults.get(
            "instruction_budget_chars", base.instruction_budget_chars
        ),
        timeout_seconds=float(defaults.get("timeout_seconds", base.timeout_seconds)),
        validation_timeout_seconds=float(
            defaults.get("validation_timeout_seconds", base.validation_timeout_seconds)
        ),
        max_repair_cycles=defaults.get("max_repair_cycles", base.max_repair_cycles),
        configured_defaults=frozenset(defaults),
        cost_policy=CostPolicyTier(
            defaults.get("cost_policy", CostPolicyTier.PREPAID_CREDITS_ALLOWED.value)
        ),
        fallback_enabled=enabled,
        fallback_quality_policy=FallbackQualityPolicy(
            fallback.get("quality_policy", base.fallback_quality_policy.value)
        ),
        fallback_priority=priority,
        fallback_exclude=exclude,
        fallback_allow_cost_escalation=allow_cost_escalation,
    )
