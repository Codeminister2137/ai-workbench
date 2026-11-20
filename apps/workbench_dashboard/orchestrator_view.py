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
    search: str = "",
) -> dict[str, Any]:
    """Recommend catalog routes for a capability set; raises ValueError on bad input."""
    from ai_orchestrator import CostPolicyTier, load_model_catalog
    from ai_orchestrator.models import (
        PrivacyClass,
        TaskCapability,
        TaskProfile,
        TaskType,
        supports_capability,
    )
    from ai_orchestrator.recommender import NoCandidateError, recommend_model

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
    catalog_rows = [
        {
            "route_id": entry.backend.route_id,
            "provider": entry.backend.provider,
            "model": entry.backend.model,
            "quality": entry.quality.value,
            "notes": entry.notes or "No grade explanation recorded.",
            "cost_tier": entry.backend.cost_policy_tier.value,
            "capabilities": [
                member.value
                for member in TaskCapability
                if supports_capability(entry.backend.capabilities, member)
            ],
        }
        for entry in catalog
    ]
    terms = search.casefold().split()
    catalog_rows = [
        row for row in catalog_rows if all(term in str(row).casefold() for term in terms)
    ]
    options = {
        "capabilities": [member.value for member in TaskCapability],
        "cost_tiers": [member.value for member in CostPolicyTier],
        "privacy": [member.value for member in PrivacyClass],
    }
    try:
        result = recommend_model(profile, catalog)
    except NoCandidateError as exc:
        return {
            "ok": True,
            "admitted": False,
            "message": str(exc),
            "routes": [],
            "catalog": catalog_rows,
            "options": options,
            "rejected": [
                {"route_id": item.candidate.backend.route_id, "reason": item.reason}
                for item in exc.rejected
            ],
            "reasons": [],
        }
    return {
        "ok": True,
        "admitted": True,
        "catalog": catalog_rows,
        "options": options,
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
