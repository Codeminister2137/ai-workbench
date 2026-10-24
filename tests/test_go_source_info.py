"""OpenCode Go metadata collection tests; no network or real credentials."""

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest
from ai_provider import go_source_info as go


class Response(BytesIO):
    status = 200

    def __init__(self, raw, headers=None):
        super().__init__(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.headers = headers or {}


def models_payload():
    return {
        "data": [
            {
                "id": "kimi-k2.7-code",
                "object": "model",
                "supported_parameters": ["tools", "stream", "max_tokens"],
                "context_window": 128000,
                "pricing": {"input": "0.95", "output": "4.00"},
            },
            {
                "id": "glm-5.2",
                "supported_parameters": ["tools"],
                "pricing": {"input": "1.40", "output": "4.40"},
            },
            {"id": "longcat-2.5-preview-free", "pricing": {"input": "0", "output": "0"}},
        ]
    }


def test_list_models_uses_key_and_parses_metadata(monkeypatch):
    calls = []

    def open_request(request, *, timeout):
        calls.append(request)
        assert request.get_method() == "GET"
        assert request.full_url == go.GO_INFERENCE_BASE_URL + "/v1/models"
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers.get("authorization") == "Bearer synthetic-go-key"
        assert "ai_projects" in headers.get("user-agent", "")
        assert request.data is None
        assert timeout == 4
        return Response(models_payload())

    monkeypatch.setattr(go, "urlopen", open_request)
    collector = go.OpenCodeGoSourceInfo(api_key="synthetic-go-key")
    inventory = collector.list_models(timeout_seconds=4)

    assert inventory.status == "observed"
    assert inventory.source == "opencode_go"
    assert len(inventory.models) == 3
    assert inventory.models[0].id == "kimi-k2.7-code"
    assert inventory.models[0].capabilities is not None
    assert inventory.models[0].capabilities.tools is True
    assert inventory.models[0].capabilities.streaming is True
    assert inventory.models[0].context_window_tokens == 128000
    assert inventory.models[0].prices == {"input": "0.95", "output": "4.00"}
    assert inventory.models[0].endpoint == go.GO_CHAT_BASE_URL + "/chat/completions"
    assert inventory.models[0].protocol == "chat"
    assert inventory.models[0].trains_on_request_data is False
    assert inventory.models[0].requires_global_regions is False

    data = inventory.to_dict()
    assert data["models"][1]["id"] == "glm-5.2"
    assert "synthetic-go-key" not in json.dumps(data)


def test_list_models_without_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(go, "urlopen", lambda *a, **k: pytest.fail("Network attempted"))
    collector = go.OpenCodeGoSourceInfo(api_key=None)
    inventory = collector.list_models(timeout_seconds=4)
    assert inventory.status == "unavailable"
    assert inventory.reason == "credential_not_configured"


@pytest.mark.parametrize(
    "failure",
    ["http_401", "http_403", "oversize", "bad_json", "bad_shape"],
)
def test_list_models_failures_are_sanitized(monkeypatch, failure):
    def open_request(request, *, timeout):
        if failure == "http_401":
            raise HTTPError(request.full_url, 401, "secret", Message(), None)
        if failure == "http_403":
            raise HTTPError(request.full_url, 403, "secret", Message(), None)
        if failure == "oversize":
            return Response(b"x" * (2_097_152 + 1))
        if failure == "bad_json":
            return Response(b"synthetic-secret-not-json")
        return Response([])

    monkeypatch.setattr(go, "urlopen", open_request)
    collector = go.OpenCodeGoSourceInfo(api_key="synthetic")
    inventory = collector.list_models(timeout_seconds=4)
    assert inventory.status == "unavailable"
    assert "secret" not in json.dumps(inventory.to_dict())


def usage_payload():
    return {
        "usage": {
            "rolling": {"status": "ok", "percent": 0, "resetsAt": "2026-10-24T19:44:54.756Z"},
            "weekly": {"status": "ok", "percent": 90, "resetsAt": "2026-10-26T00:00:00.000Z"},
            "monthly": {"status": "ok", "percent": 45, "resetsAt": "2026-11-22T09:49:38.000Z"},
        }
    }


def test_account_allowance_reads_the_documented_usage_endpoint(monkeypatch):
    calls = []

    def open_request(request, *, timeout):
        calls.append(request)
        assert request.get_method() == "GET"
        assert request.full_url == "https://opencode.ai/zen/go/v1/usage"
        headers = {key.lower(): value for key, value in request.headers.items()}
        assert headers.get("authorization") == "Bearer synthetic-go-key"
        assert "ai_projects" in headers.get("user-agent", "")
        assert request.data is None
        assert timeout == 4
        return Response(usage_payload())

    monkeypatch.setattr(go, "urlopen", open_request)
    allowance = go.OpenCodeGoSourceInfo(api_key="synthetic-go-key").account_allowance(
        timeout_seconds=4
    )

    assert len(calls) == 1
    assert allowance.status == "observed"
    assert allowance.source == "opencode_go"
    assert allowance.reason is None
    assert [window["window"] for window in allowance.windows] == ["rolling", "weekly", "monthly"]
    assert [window["used_percent"] for window in allowance.windows] == [0, 90, 45]
    assert [window["remaining_percent"] for window in allowance.windows] == [100, 10, 55]
    assert allowance.windows[1]["resets_at"] == "2026-10-26T00:00:00.000Z"
    assert "synthetic-go-key" not in json.dumps(allowance.to_dict())


def test_account_allowance_without_key_is_unavailable(monkeypatch):
    monkeypatch.setattr(go, "urlopen", lambda *a, **k: pytest.fail("Network attempted"))
    allowance = go.OpenCodeGoSourceInfo(api_key=None).account_allowance(timeout_seconds=4)
    assert allowance.status == "unavailable"
    assert allowance.reason == "credential_not_configured"


@pytest.mark.parametrize(
    "failure",
    ["http_401", "http_403", "http_429", "oversize", "bad_json", "bad_shape", "bad_percent"],
)
def test_account_allowance_failures_are_sanitized(monkeypatch, failure):
    def open_request(request, *, timeout):
        if failure.startswith("http_"):
            raise HTTPError(request.full_url, int(failure.split("_")[1]), "secret", Message(), None)
        if failure == "oversize":
            return Response(b"x" * (65_536 + 1))
        if failure == "bad_json":
            return Response(b"synthetic-secret-not-json")
        if failure == "bad_shape":
            return Response({"usage": {"rolling": {}}})
        payload = usage_payload()
        payload["usage"]["weekly"]["percent"] = 101
        return Response(payload)

    monkeypatch.setattr(go, "urlopen", open_request)
    allowance = go.OpenCodeGoSourceInfo(api_key="synthetic-go-key").account_allowance(
        timeout_seconds=4
    )

    assert allowance.status == "unavailable"
    assert allowance.windows == ()
    assert "secret" not in json.dumps(allowance.to_dict())
    expected = {
        "http_401": "authentication_failed",
        "http_403": "permission_denied",
        "http_429": "usage_endpoint_rate_limited",
    }.get(failure, "metadata_request_failed")
    assert allowance.reason == expected


def test_allowance_report_keeps_account_percentages_and_published_caps_separate(monkeypatch):
    monkeypatch.setattr(go, "urlopen", lambda request, *, timeout: Response(usage_payload()))
    report = go.read_opencode_go_allowance(api_key="synthetic-go-key", timeout_seconds=4)

    assert report["status"] == "observed"
    assert report["model_limits_usd"]["kimi-k2.7-code"] == 60.0
    assert report["model_limits_usd"]["kimi-k3"] == 15.0
    # The binding window is the account-wide one closest to its limit.
    assert report["binding_window"] == {
        "window": "weekly",
        "used_percent": 90,
        "remaining_percent": 10,
        "resets_at": "2026-10-26T00:00:00.000Z",
    }
    assert "account_wide" in report["usage_scope"]
    assert "not observed" in report["usage_scope"]
    assert "synthetic-go-key" not in json.dumps(report)


def test_allowance_report_without_observation_has_no_binding_window(monkeypatch):
    monkeypatch.setattr(go, "urlopen", lambda *a, **k: pytest.fail("Network attempted"))
    report = go.read_opencode_go_allowance(api_key=None, timeout_seconds=4)
    assert report["status"] == "unavailable"
    assert report["binding_window"] is None
    assert report["model_limits_usd"]["kimi-k2.7-code"] == 60.0


@pytest.mark.parametrize("timeout", [True, 0, -1, float("inf"), float("nan")])
def test_invalid_timeouts_refuse_before_io(monkeypatch, timeout):
    monkeypatch.setattr(go, "urlopen", lambda *a, **k: pytest.fail("Network attempted"))
    collector = go.OpenCodeGoSourceInfo(api_key="synthetic")
    with pytest.raises(ValueError, match="finite and positive"):
        collector.list_models(timeout_seconds=timeout)


def test_usage_from_response_normalizes_tokens_and_cost():
    raw = {
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 3,
            "total_tokens": 15,
            "cost": 0.0005,
        }
    }
    data = go.usage_from_response(raw)
    assert data["source"] == "opencode_go"
    assert data["usage_source"] == "provider_reported"
    assert data["input_tokens"] == 12
    assert data["output_tokens"] == 3
    assert data["total_tokens"] == 15
    assert data["reported_cost_usd"] == 0.0005


def test_usage_from_response_missing_usage_is_unknown():
    data = go.usage_from_response({})
    assert data["usage_source"] == "unavailable"
    assert data["input_tokens"] is None


def test_account_usage_dispatcher_routes_go_to_source_info(monkeypatch):
    from ai_orchestrator import (
        AccessMethod,
        AuthMethod,
        BillingSource,
        CostPolicyTier,
        ExecutionTarget,
    )
    from ai_provider import account_usage

    monkeypatch.setenv("OPENCODE_API_KEY", "synthetic-go-key")
    monkeypatch.setattr(go, "urlopen", lambda request, *, timeout: Response(usage_payload()))
    target = ExecutionTarget(
        route_id="opencode-go-kimi",
        provider="opencode_go",
        product="opencode_go",
        model="kimi-k2.7-code",
        access_method=AccessMethod.PROVIDER_API,
        auth_method=AuthMethod.API_KEY,
        billing_source=BillingSource.OPENCODE_GO_SUBSCRIPTION_ALLOWANCE,
        cost_policy_tier=CostPolicyTier.ALLOWANCES_ALLOWED,
        timeout_seconds=10,
    )
    result = account_usage.read_execution_allowance(target)
    assert result is not None
    assert result["status"] == "observed"
    assert result["source"] == "opencode_go"
    assert [window["used_percent"] for window in result["windows"]] == [0, 90, 45]
    assert result["binding_window"]["window"] == "weekly"


def test_account_usage_dispatcher_returns_none_for_non_go_sources():
    from ai_orchestrator import (
        AccessMethod,
        AuthMethod,
        BillingSource,
        CostPolicyTier,
        ExecutionTarget,
    )
    from ai_provider import account_usage

    target = ExecutionTarget(
        route_id="openai-gpt",
        provider="openai",
        product="openai",
        model="gpt-5-mini",
        access_method=AccessMethod.PROVIDER_API,
        auth_method=AuthMethod.API_KEY,
        billing_source=BillingSource.OPENAI_API_BILLING,
        cost_policy_tier=CostPolicyTier.BILLING_ALLOWED,
        timeout_seconds=10,
    )
    assert account_usage.read_execution_allowance(target) is None


def test_select_probe_models():
    from ai_provider.source_info import ModelInventory, ModelInventoryItem

    inventory = ModelInventory(
        status="observed",
        source="opencode_go",
        observed_at_utc="now",
        models=(
            ModelInventoryItem(id="kimi-k2.7-code", source="opencode_go", endpoint="x"),
            ModelInventoryItem(id="beam-free", source="opencode_go", endpoint="x"),
            ModelInventoryItem(id="minimax-m3.1-flash-free", source="opencode_go", endpoint="x"),
        ),
    )
    assert go._select_probe_models(inventory, "all") == [
        "kimi-k2.7-code",
        "beam-free",
        "minimax-m3.1-flash-free",
    ]
    assert go._select_probe_models(inventory, "free") == [
        "beam-free",
        "minimax-m3.1-flash-free",
    ]
    assert go._select_probe_models(inventory, "kimi-k2.7-code,beam-free") == [
        "kimi-k2.7-code",
        "beam-free",
    ]


def test_model_protocol_and_privacy_metadata():
    cases = [
        ("kimi-k2.7-code", "chat", False, False),
        ("grok-4.6", "responses", False, False),
        ("deepseek-v4-pro", "responses", False, True),
        ("muse-spark-1.2-contributor", "responses", True, False),
        ("claude-haiku-5-5", "messages", False, False),
        ("minimax-m2.7", "messages", False, False),
    ]
    for model_id, protocol, trains, global_regions in cases:
        item = go._parse_model_row({"id": model_id}, source="opencode_go", observed_at_utc="now")
        assert item.protocol == protocol, model_id
        assert item.trains_on_request_data is trains, model_id
        assert item.requires_global_regions is global_regions, model_id


def test_model_endpoint_matches_protocol():
    chat = go._parse_model_row(
        {"id": "kimi-k2.7-code"}, source="opencode_go", observed_at_utc="now"
    )
    assert chat.endpoint == go.GO_CHAT_BASE_URL + "/chat/completions"
    resp = go._parse_model_row({"id": "grok-4.6"}, source="opencode_go", observed_at_utc="now")
    assert resp.endpoint == go.GO_INFERENCE_BASE_URL + "/v1/responses"
    msg = go._parse_model_row(
        {"id": "claude-haiku-5-5"}, source="opencode_go", observed_at_utc="now"
    )
    assert msg.endpoint == go.GO_INFERENCE_BASE_URL + "/v1/messages"


def test_probe_model_ok(monkeypatch):
    import ai_provider
    from ai_provider.contracts import FinishReason, UsageMetadata, UsageSource

    class FakeClient:
        def complete(self, request):
            class Resp:
                usage = UsageMetadata(
                    source=UsageSource.PROVIDER_REPORTED,
                    input_tokens=2,
                    output_tokens=3,
                    total_tokens=5,
                )
                finish_reason = FinishReason.STOP

            return Resp()

    monkeypatch.setattr(ai_provider, "create_chat_client", lambda config: FakeClient())
    result = go._probe_model(
        "kimi-k2.7-code",
        api_key="test",
        prompt="hi",
        max_output_tokens=8,
        timeout_seconds=5,
    )
    assert result["status"] == "ok"
    assert result["input_tokens"] == 2
    assert result["finish_reason"] == "stop"


def test_probe_model_error_is_sanitized(monkeypatch):
    import ai_provider
    from ai_provider.errors import ProviderError, ProviderErrorCategory

    def fail(config):
        raise ProviderError("secret model failure", category=ProviderErrorCategory.RATE_LIMIT)

    monkeypatch.setattr(ai_provider, "create_chat_client", fail)
    result = go._probe_model(
        "broken-model",
        api_key="test",
        prompt="hi",
        max_output_tokens=8,
        timeout_seconds=5,
    )
    assert result["status"] == "error"
    assert result["error_category"] == "rate_limit"
    assert "secret" not in str(result)
