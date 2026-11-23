"""Native allowance shapes normalize into one refresh-aware window model."""

import pytest
from ai_orchestrator import (
    AccessMethod,
    AuthMethod,
    BillingSource,
    CostPolicyTier,
    ExecutionTarget,
)
from ai_provider import account_usage
from ai_provider import allowance_windows as windows


def _target(access_method, billing_source):
    return ExecutionTarget(
        route_id="allowance-probe",
        provider="probe",
        product="probe",
        model="probe",
        access_method=access_method,
        auth_method=AuthMethod.API_KEY,
        billing_source=billing_source,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        timeout_seconds=5,
    )


def test_codex_unix_reset_and_complement():
    (window,) = windows.normalize_windows(
        "codex",
        [
            {
                "bucket_id": "codex",
                "window": "primary",
                "used_percent": 25,
                "resets_at_unix_seconds": 1791626400,
            }
        ],
        "codex_app_server",
    )
    assert window.provider == "codex"
    assert window.used_percent == 25.0
    assert window.remaining_percent == 75.0
    assert window.resets_at_utc == "2026-10-10T10:00:00+00:00"
    assert window.source == "codex_app_server"


def test_copilot_iso_reset_and_counts_in_details():
    (window,) = windows.normalize_windows(
        "copilot",
        [
            {
                "bucket_id": "premium",
                "window": "entitlement",
                "entitlement_requests": 100,
                "used_requests": 30,
                "remaining_percent": 70,
                "reset_date": "2026-12-01",
            }
        ],
        "copilot_account_quota",
    )
    assert window.used_percent == 30.0
    assert window.remaining_percent == 70.0
    assert window.resets_at_utc == "2026-12-01T00:00:00+00:00"
    assert window.details == {"entitlement_requests": 100, "used_requests": 30}


def test_kiro_date_reset_and_reported_share():
    (window,) = windows.normalize_windows(
        "kiro",
        [
            {
                "bucket_id": "plan_credits",
                "window": "subscription",
                "measurement_kind": "native_estimate",
                "covered_credits": 87.5,
                "plan_credits": 100.0,
                "reported_percent": 87.5,
                "reset_date": "2026-11-20",
            }
        ],
        "kiro_cli",
    )
    assert window.used_percent == 87.5
    assert window.remaining_percent == 12.5
    assert window.resets_at_utc == "2026-11-20T00:00:00+00:00"
    assert window.details["covered_credits"] == 87.5


def test_opencode_go_zulu_reset_and_drift_tolerance():
    (window,) = windows.normalize_windows(
        "opencode-go",
        [
            {
                "bucket_id": "go_weekly",
                "window": "weekly",
                "used_percent": 90,
                "remaining_percent": 10,
                "resets_at": "2026-10-26T00:00:00.000Z",
                "status": "ok",
            }
        ],
        "opencode_go",
    )
    assert window.used_percent == 90.0
    assert window.remaining_percent == 10.0
    assert window.resets_at_utc == "2026-10-26T00:00:00+00:00"
    (drifted,) = windows.normalize_windows(
        "opencode-go",
        [
            {
                "bucket_id": "go_weekly",
                "window": "weekly",
                "used_percent": 90,
                "remaining_percent": 10,
                "resets_at": "next friday, probably",
            }
        ],
        "opencode_go",
    )
    assert drifted.resets_at_utc is None
    assert drifted.details["resets_at_unparsed"] == "next friday, probably"


def test_invalid_provider_and_measurements_raise():
    with pytest.raises(ValueError, match="Unsupported allowance provider"):
        windows.normalize_windows("openrouter", [], "x")
    with pytest.raises(ValueError, match="quota percentage"):
        windows.normalize_windows(
            "codex",
            [
                {
                    "bucket_id": "codex",
                    "window": "primary",
                    "used_percent": 101,
                    "resets_at_unix_seconds": None,
                }
            ],
            "x",
        )
    with pytest.raises(ValueError, match="allowance bucket"):
        windows.normalize_windows("codex", [{"window": "primary"}], "x")
    with pytest.raises(ValueError, match="quota reset"):
        windows.normalize_windows(
            "copilot",
            [
                {
                    "bucket_id": "b",
                    "window": "entitlement",
                    "remaining_percent": 50,
                    "reset_date": "yesterday",
                }
            ],
            "x",
        )


def test_provider_mapping_and_unsupported_target():
    assert (
        windows.provider_for_target(
            _target(AccessMethod.CODEX_CLI, BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE)
        )
        == "codex"
    )
    assert (
        windows.provider_for_target(
            _target(AccessMethod.COPILOT_CLI, BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE)
        )
        == "copilot"
    )
    assert (
        windows.provider_for_target(
            _target(AccessMethod.KIRO_CLI, BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE)
        )
        == "kiro"
    )
    assert (
        windows.provider_for_target(
            _target(AccessMethod.PROVIDER_API, BillingSource.OPENCODE_GO_SUBSCRIPTION_ALLOWANCE)
        )
        == "opencode-go"
    )
    assert (
        windows.provider_for_target(
            _target(AccessMethod.PROVIDER_API, BillingSource.OPENAI_API_BILLING)
        )
        is None
    )


def test_read_allowance_windows_uses_existing_reader(monkeypatch):
    seen = {}

    def fake_reader(target):
        seen["target"] = target
        return {
            "status": "observed",
            "source": "codex_app_server",
            "windows": [
                {
                    "bucket_id": "codex",
                    "window": "primary",
                    "used_percent": 10,
                    "resets_at_unix_seconds": None,
                }
            ],
        }

    monkeypatch.setattr(account_usage, "read_execution_allowance", fake_reader)
    target = _target(AccessMethod.CODEX_CLI, BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE)
    found = windows.read_allowance_windows(target)
    assert found is not None
    (window,) = found
    assert seen["target"] is target
    assert window.used_percent == 10.0
    assert window.remaining_percent == 90.0
    assert window.resets_at_utc is None
    assert (
        windows.read_allowance_windows(
            _target(AccessMethod.PROVIDER_API, BillingSource.OPENAI_API_BILLING)
        )
        is None
    )
