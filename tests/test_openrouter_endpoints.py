"""OpenRouter endpoint availability observations; no network and no inference."""

import json
from email.message import Message
from io import BytesIO

import pytest
from ai_provider.openrouter_endpoints import (
    read_openrouter_endpoint_availability,
)
from ai_provider.source_info import EndpointAvailability, EndpointInventory

MODEL = "qwen/qwen3.8-27b:free"


class Response(BytesIO):
    status = 200

    def __init__(self, raw, headers=None):
        super().__init__(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.headers = headers or {}


def endpoint(**changes):
    row = {
        "provider_name": "Chutes",
        "tag": "chutes/fp8",
        "status": 0,
        "uptime_last_1d": 100.0,
        "uptime_last_30m": 100.0,
        "uptime_last_5m": 100.0,
        "latency_last_30m": None,
        "throughput_last_30m": None,
        "quantization": "fp8",
        "service_tier": None,
        "context_length": 262144,
        "max_completion_tokens": 65536,
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": ["tools", "max_tokens"],
    }
    row.update(changes)
    return row


def transport(monkeypatch, *, rows=None, status=200):
    calls = []

    def send(http_request, **kwargs):
        calls.append(http_request)
        if status != 200:
            from urllib.error import HTTPError

            raise HTTPError(http_request.full_url, status, "error", Message(), None)
        return Response({"data": {"id": MODEL, "endpoints": endpoint_rows()}})

    def endpoint_rows():
        return [endpoint()] if rows is None else rows

    monkeypatch.setattr("ai_provider.openrouter_endpoints.urlopen", send)
    return calls


def test_endpoints_are_read_without_inference(monkeypatch):
    calls = transport(monkeypatch)
    result = read_openrouter_endpoint_availability(MODEL)
    assert isinstance(result, EndpointInventory)
    assert result.status == "observed"
    assert result.model == MODEL
    assert result.reason is None
    assert [call.get_method() for call in calls] == ["GET"]
    assert calls[0].full_url == (
        "https://openrouter.ai/api/v1/models/qwen/qwen3.8-27b:free/endpoints"
    )
    endpoint_record = result.endpoints[0]
    assert isinstance(endpoint_record, EndpointAvailability)
    assert endpoint_record.provider == "Chutes"
    assert endpoint_record.endpoint == "chutes/fp8"
    assert endpoint_record.quantization == "fp8"
    assert endpoint_record.uptime_1d_percent == 100.0
    assert endpoint_record.context_length == 262144
    assert endpoint_record.supported_parameters == ("tools", "max_tokens")


def test_unreported_values_stay_unknown(monkeypatch):
    transport(
        monkeypatch,
        rows=[
            endpoint(
                latency_last_30m=None,
                throughput_last_30m=None,
                service_tier=None,
                quantization=None,
            )
        ],
    )
    record = read_openrouter_endpoint_availability(MODEL).endpoints[0]
    assert record.latency_seconds is None
    assert record.throughput_tokens_per_second is None
    assert record.service_tier is None
    assert record.quantization is None


def test_non_numeric_availability_values_are_ignored(monkeypatch):
    transport(monkeypatch, rows=[endpoint(uptime_last_1d="unknown", context_length="many")])
    record = read_openrouter_endpoint_availability(MODEL).endpoints[0]
    assert record.uptime_1d_percent is None
    assert record.context_length is None


def test_model_without_advertised_endpoints_is_observed_and_empty(monkeypatch):
    transport(monkeypatch, rows=[])
    result = read_openrouter_endpoint_availability(MODEL)
    assert result.status == "observed"
    assert result.endpoints == ()
    assert result.reason == "no_endpoints_advertised"
    assert result.summary()["provider_count"] == 0


def test_summary_reports_the_weakest_and_strongest_endpoints(monkeypatch):
    transport(
        monkeypatch,
        rows=[
            endpoint(provider_name="Chutes", uptime_last_1d=100.0, quantization="fp8"),
            endpoint(provider_name="Wafer", uptime_last_1d=72.5, quantization="fp4"),
            endpoint(provider_name="Cloudflare", uptime_last_1d=None, quantization=None),
        ],
    )
    summary = read_openrouter_endpoint_availability(MODEL).summary()
    assert summary["provider_count"] == 3
    assert summary["endpoint_count"] == 3
    assert summary["best_uptime_1d_percent"] == 100.0
    assert summary["worst_uptime_1d_percent"] == 72.5
    assert summary["max_context_length"] == 262144
    assert summary["quantizations"] == ["fp4", "fp8"]


def test_endpoint_rows_without_a_provider_are_skipped(monkeypatch):
    transport(monkeypatch, rows=[endpoint(), {"tag": "orphan"}])
    result = read_openrouter_endpoint_availability(MODEL)
    assert len(result.endpoints) == 1


@pytest.mark.parametrize("rows", [[{"tag": "orphan"}], [None, {}, "invalid"]])
def test_unusable_rows_do_not_claim_no_endpoints_are_advertised(monkeypatch, rows):
    transport(monkeypatch, rows=rows)
    result = read_openrouter_endpoint_availability(MODEL)
    assert result.status == "unavailable"
    assert result.reason == "metadata_request_failed"
    assert result.endpoints == ()


@pytest.mark.parametrize("value", [-1, 101, float("inf"), float("nan"), 10**400, True])
def test_invalid_uptime_does_not_distort_availability_summary(monkeypatch, value):
    transport(monkeypatch, rows=[endpoint(uptime_last_1d=value, uptime_last_30m=value)])
    result = read_openrouter_endpoint_availability(MODEL)
    assert result.status == "observed"
    assert result.endpoints[0].uptime_1d_percent is None
    assert result.endpoints[0].uptime_30m_percent is None
    assert result.summary()["best_uptime_1d_percent"] is None


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), 10**400, True])
def test_invalid_performance_observations_stay_unknown(monkeypatch, value):
    transport(monkeypatch, rows=[endpoint(latency_last_30m=value, throughput_last_30m=value)])
    record = read_openrouter_endpoint_availability(MODEL).endpoints[0]
    assert record.latency_seconds is None
    assert record.throughput_tokens_per_second is None


def test_zero_performance_and_percentage_boundaries_are_valid(monkeypatch):
    transport(
        monkeypatch,
        rows=[
            endpoint(
                uptime_last_1d=0, uptime_last_30m=100, latency_last_30m=0, throughput_last_30m=0
            )
        ],
    )
    record = read_openrouter_endpoint_availability(MODEL).endpoints[0]
    assert record.uptime_1d_percent == 0
    assert record.uptime_30m_percent == 100
    assert record.latency_seconds == 0
    assert record.throughput_tokens_per_second == 0


def test_nonfinite_numeric_prices_do_not_escape_json_safe_observation(monkeypatch):
    transport(
        monkeypatch,
        rows=[endpoint(pricing={"prompt": "0", "completion": float("nan"), "other": float("inf")})],
    )
    result = read_openrouter_endpoint_availability(MODEL)
    assert result.endpoints[0].prices == {"prompt": "0"}
    json.dumps(result.to_dict(), allow_nan=False)


@pytest.mark.parametrize(
    "status,reason", [(404, "model_not_found"), (401, "authentication_failed")]
)
def test_http_failures_are_sanitized(monkeypatch, status, reason):
    transport(monkeypatch, status=status)
    result = read_openrouter_endpoint_availability(MODEL)
    assert result.status == "unavailable"
    assert result.reason == reason
    assert result.endpoints == ()


def test_malformed_payloads_refuse_without_raising(monkeypatch):
    def send(http_request, **kwargs):
        return Response({"data": {"endpoints": "not-a-list"}})

    monkeypatch.setattr("ai_provider.openrouter_endpoints.urlopen", send)
    result = read_openrouter_endpoint_availability(MODEL)
    assert result.status == "unavailable"
    assert result.reason == "metadata_request_failed"


@pytest.mark.parametrize("model_id", ["", "   ", "no-slash", "a/b/c", "author/"])
def test_invalid_model_ids_are_rejected(model_id):
    with pytest.raises(ValueError, match="[Mm]odel id"):
        read_openrouter_endpoint_availability(model_id)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeouts_refuse_before_io(monkeypatch, timeout):
    monkeypatch.setattr(
        "ai_provider.openrouter_endpoints.urlopen",
        lambda *a, **k: pytest.fail("Network attempted"),
    )
    with pytest.raises(ValueError, match="finite and positive"):
        read_openrouter_endpoint_availability(MODEL, timeout_seconds=timeout)


def test_credential_is_optional_and_never_returned(monkeypatch):
    calls = transport(monkeypatch)
    result = read_openrouter_endpoint_availability(MODEL, api_key="synthetic")
    assert "synthetic" not in json.dumps(result.to_dict())
    assert calls[0].get_header("Authorization") == "Bearer synthetic"


def test_no_credential_is_sent_when_none_is_configured(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    calls = transport(monkeypatch)
    read_openrouter_endpoint_availability(MODEL)
    assert calls[0].get_header("Authorization") is None
