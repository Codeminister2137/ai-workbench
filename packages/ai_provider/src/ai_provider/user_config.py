"""Local user preferences, separate from shared catalogs and backend credentials."""

from __future__ import annotations

import argparse
import math
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ai_agent.permissions import ApprovalPolicyPreset
from ai_orchestrator import CostPolicyTier, PrivacyClass, QualityThreshold
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
class UserConfig:
    """Typed preferences; new preference groups can be added as needs arise."""

    cost_policy: CostPolicyTier = CostPolicyTier.PREPAID_CREDITS_ALLOWED
    fallback_enabled: bool = True
    fallback_quality_policy: FallbackQualityPolicy = FallbackQualityPolicy.PRESERVE_QUALITY
    quality: QualityThreshold = QualityThreshold.STANDARD
    privacy: PrivacyClass = PrivacyClass.LOCAL_ONLY
    approval_policy: ApprovalPolicyPreset = ApprovalPolicyPreset.INTERACTIVE
    context_budget_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS
    context_file_budget_chars: int = DEFAULT_CONTEXT_FILE_BUDGET_CHARS
    instruction_budget_chars: int = DEFAULT_INSTRUCTION_BUDGET_CHARS
    timeout_seconds: float = 180.0
    validation_timeout_seconds: float = 300.0
    max_repair_cycles: int = 3
    configured_defaults: frozenset[str] = frozenset()


def apply_user_defaults(args: argparse.Namespace, config: UserConfig) -> None:
    """Apply preferences while retaining every explicitly supplied CLI value."""
    provided = getattr(args, "_provided_user_defaults", frozenset())
    for key in EXECUTION_DEFAULT_KEYS - provided:
        value = getattr(config, key)
        setattr(args, key, value.value if isinstance(value, StrEnum) else value)
    args._configured_user_defaults = config.configured_defaults


def load_user_config(path: Path, *, required: bool = False) -> UserConfig:
    """Load TOML preferences, rejecting invalid values and misspelled settings."""

    if not path.exists() and not required:
        return UserConfig()
    with path.open("rb") as source:
        data = tomllib.load(source)
    if set(data) - {"defaults", "fallback"}:
        raise ValueError("Unknown user config section; supported sections: defaults, fallback")
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
    if not isinstance(fallback, dict) or set(fallback) - {"enabled", "quality_policy"}:
        raise ValueError("User config fallback supports only enabled and quality_policy")
    enabled = fallback.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("fallback.enabled must be a boolean")
    return UserConfig(
        quality=QualityThreshold(defaults.get("quality", base.quality.value)),
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
            fallback.get("quality_policy", FallbackQualityPolicy.PRESERVE_QUALITY.value)
        ),
    )
