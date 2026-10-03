"""Local user preferences, separate from shared catalogs and backend credentials."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ai_orchestrator import CostPolicyTier


@dataclass(frozen=True)
class UserConfig:
    """Typed preferences; new preference groups can be added as needs arise."""

    cost_policy: CostPolicyTier = CostPolicyTier.PREPAID_CREDITS_ALLOWED
    fallback_enabled: bool = True


def load_user_config(path: Path, *, required: bool = False) -> UserConfig:
    """Load TOML preferences, rejecting invalid values and misspelled settings."""

    if not path.exists() and not required:
        return UserConfig()
    with path.open("rb") as source:
        data = tomllib.load(source)
    if set(data) - {"defaults", "fallback"}:
        raise ValueError("Unknown user config section; supported sections: defaults, fallback")
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict) or set(defaults) - {"cost_policy"}:
        raise ValueError("User config defaults supports only cost_policy")
    fallback = data.get("fallback", {})
    if not isinstance(fallback, dict) or set(fallback) - {"enabled"}:
        raise ValueError("User config fallback supports only enabled")
    enabled = fallback.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("fallback.enabled must be a boolean")
    return UserConfig(
        cost_policy=CostPolicyTier(
            defaults.get("cost_policy", CostPolicyTier.PREPAID_CREDITS_ALLOWED.value)
        ),
        fallback_enabled=enabled,
    )
