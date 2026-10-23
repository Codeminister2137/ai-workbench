"""Deterministic route/catalog checks for the OpenCode Go `opencode-go/go-kimi-k2.7-code` route.

These tests do not perform live inference; they verify that the catalog entry,
orchestrator resolution and fallback readiness treat the route as a valid
provider-api coding route.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_agent import repo_coding_assistant as cli
from ai_agent.ide_bridge import IDE_TOOL_NAMES
from ai_agent.tool_profiles import shared_tool_registry
from ai_orchestrator import (
    AccessMethod,
    BackendLocation,
    BillingSource,
    CostPolicyTier,
    PrivacyClass,
    QualityThreshold,
    TaskProfile,
    load_model_catalog,
    recommend_model,
)
from ai_provider import ProviderKind

CATALOG_PATH = Path("packages/ai_orchestrator/examples/model_catalog.toml")


def _offline_args(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--fallback-readiness",
        "--repo-root",
        str(tmp_path),
        "--privacy",
        "public_or_low_risk",
        "--cost-policy",
        "allowances_allowed",
        "--route-id",
        "opencode-go/go-kimi-k2.7-code",
        *extra,
    ]


def test_catalog_contains_opencode_go_kimi_route() -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    routes = {entry.backend.route.route_id: entry for entry in catalog}
    assert "opencode-go/go-kimi-k2.7-code" in routes
    entry = routes["opencode-go/go-kimi-k2.7-code"]
    assert entry.backend.route.provider == ProviderKind.OPENCODE_GO.value
    assert entry.backend.route.access_method is AccessMethod.PROVIDER_API
    assert entry.backend.route.location is BackendLocation.EXTERNAL
    assert entry.backend.route.billing_source is BillingSource.OPENCODE_GO_SUBSCRIPTION_ALLOWANCE
    assert entry.backend.route.cost_policy_tier is CostPolicyTier.ALLOWANCES_ALLOWED


def test_recommender_selects_kimi_route_for_coding_task() -> None:
    catalog = load_model_catalog(CATALOG_PATH)
    profile = TaskProfile(
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        quality_threshold=QualityThreshold.HIGH,
        user_route_id_override="opencode-go/go-kimi-k2.7-code",
    )
    recommendation = recommend_model(profile, catalog)
    assert recommendation is not None
    route = recommendation.selected.backend.route
    assert route.route_id == "opencode-go/go-kimi-k2.7-code"
    assert route.provider == ProviderKind.OPENCODE_GO.value


def test_coding_tool_registry_does_not_require_ide_host(tmp_path: Path) -> None:
    """The shared coding registry used by provider-api routes works without PyCharm."""

    registry = shared_tool_registry("coding", workspace=tmp_path)
    names = {definition.name for definition in registry.list_definitions()}
    required = {
        "read_file",
        "list_dir",
        "find_files",
        "grep_search",
        "git_status",
        "git_diff",
        "create_file",
        "edit_file",
        "run_command",
        "fetch_url",
        "python_runtime",
        "python_navigate",
        "rename_preview",
        "rename_apply",
        "delegate_task",
    }
    assert required <= names
    assert not (set(IDE_TOOL_NAMES) & names)


def test_fallback_readiness_reports_kimi_as_primary_route(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "get_local_provider_capability_snapshot", lambda *args, **kwargs: None)
    assert cli.main(_offline_args(tmp_path)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "offline"
    assert report["primary_route"] == "opencode-go/go-kimi-k2.7-code"
    assert report["cost_policy_tier"] == "allowances_allowed"
    assert report["authentication"] == "not_checked"
    assert report["allowance"] == "unknown"


def test_fallback_readiness_includes_provider_api_candidates(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "get_local_provider_capability_snapshot", lambda *args, **kwargs: None)
    assert cli.main(_offline_args(tmp_path, "--approval-policy", "trusted_local")) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "offline"
    kimi = next(
        (
            row
            for row in report["fallback_candidates"]
            if row["route_id"] == "opencode-go/go-kimi-k2.7-code"
        ),
        None,
    )
    # The primary route itself is not a fallback candidate.
    assert kimi is None
    # Provider-api routes with allowances_allowed are statically compatible.
    assert any(row["executor_compatible"] for row in report["fallback_candidates"])
