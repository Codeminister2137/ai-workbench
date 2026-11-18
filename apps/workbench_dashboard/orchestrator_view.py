"""Read-only orchestrator route queries (dynamic queries slice).

Answers "which routes can do X right now?" from the catalog through the
real recommender — orchestrator knowledge visualized, no probing, no
side effects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def query_routes(
    catalog_path: Path | str,
    *,
    capabilities: list[str] | None = None,
    cost_tier: str = "prepaid_credits_allowed",
    privacy: str = "external_allowed",
) -> dict[str, Any]:
    """Recommend catalog routes for a capability set; raises ValueError on bad input."""
    from ai_orchestrator import CostPolicyTier, load_model_catalog
    from ai_orchestrator.models import (
        PrivacyClass,
        TaskCapability,
        TaskProfile,
        TaskType,
    )
    from ai_orchestrator.recommender import recommend_model

    try:
        required = frozenset(TaskCapability(name) for name in (capabilities or ["chat"]))
    except ValueError:
        valid = sorted(member.value for member in TaskCapability)
        raise ValueError(f"unknown capability; valid: {valid}") from None
    try:
        tier = CostPolicyTier(cost_tier)
    except ValueError:
        valid = sorted(member.value for member in CostPolicyTier)
        raise ValueError(f"unknown cost_tier; valid: {valid}") from None
    try:
        privacy_class = PrivacyClass(privacy)
    except ValueError:
        valid = sorted(member.value for member in PrivacyClass)
        raise ValueError(f"unknown privacy; valid: {valid}") from None
    catalog = load_model_catalog(catalog_path)
    profile = TaskProfile(
        task_type=TaskType.GENERAL,
        privacy_class=privacy_class,
        required_capabilities=required,
        cost_policy_tier=tier,
    )
    try:
        result = recommend_model(profile, catalog)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "routes": [], "rejected": []}
    return {
        "ok": True,
        "routes": [
            {
                "route_id": entry.backend.route_id,
                "provider": entry.backend.route.provider,
                "model": entry.backend.route.model,
                "selected": entry == result.selected,
            }
            for entry in (result.selected, *result.alternatives)
        ],
        "rejected": [
            {"route_id": item.candidate.backend.route_id, "reason": item.reason}
            for item in result.rejected
        ],
        "reasons": list(result.reasons),
    }
