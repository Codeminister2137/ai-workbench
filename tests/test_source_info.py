"""Source-information contract tests."""

from ai_provider.contracts import ModelCapabilities, UsageMetadata, UsageSource
from ai_provider.source_info import (
    AccountAllowance,
    ModelInventory,
    ModelInventoryItem,
    ResponseUsage,
)


def test_model_inventory_to_dict_omits_nothing_secret():
    item = ModelInventoryItem(
        id="kimi-k2.7-code",
        source="opencode_go",
        endpoint="https://opencode.ai/inference/go/openai/v1/chat/completions",
        capabilities=ModelCapabilities(chat=True, streaming=True, tools=True),
        context_window_tokens=128_000,
        prices={"input": "0.95", "output": "4.00"},
        observed_at_utc="2026-10-22T12:00:00+00:00",
    )
    inventory = ModelInventory(
        status="observed",
        source="opencode_go",
        models=(item,),
        observed_at_utc="2026-10-22T12:00:00+00:00",
    )
    data = inventory.to_dict()
    assert data["status"] == "observed"
    assert data["models"][0]["id"] == "kimi-k2.7-code"
    assert data["models"][0]["capabilities"]["tools"] is True
    assert "api_key" not in str(data)


def test_account_allowance_to_dict_preserves_unknown_state():
    allowance = AccountAllowance(
        status="unavailable",
        source="opencode_go",
        reason="no_official_account_allowance_endpoint_for_go_key",
        observed_at_utc="2026-10-22T12:00:00+00:00",
    )
    data = allowance.to_dict()
    assert data["status"] == "unavailable"
    assert data["reason"] == "no_official_account_allowance_endpoint_for_go_key"
    assert data["windows"] == []


def test_response_usage_serializes_provider_reported_values():
    usage = UsageMetadata(
        source=UsageSource.PROVIDER_REPORTED,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        reported_cost_usd=0.0012,
    )
    response = ResponseUsage(usage=usage, source="opencode_go")
    data = response.to_dict()
    assert data["source"] == "opencode_go"
    assert data["usage_source"] == "provider_reported"
    assert data["input_tokens"] == 10
    assert data["reported_cost_usd"] == 0.0012
