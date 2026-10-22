"""Account metadata uses provider transport without inference or secret output."""

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest
from ai_provider import openrouter_usage as usage


class Response(BytesIO):
    status = 200

    def __init__(self, raw, headers=None):
        super().__init__(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.headers = headers or {}


def account(**counter):
    return {
        "data": {
            "label": "PRIVATE_LABEL",
            "is_free_tier": True,
            "free_model_daily_requests": counter,
        }
    }


def test_metadata_uses_environment_key_and_only_official_gets(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "SYNTHETIC_SECRET")
    calls = []

    def open_request(request, *, timeout):
        calls.append(request.full_url)
        assert request.get_method() == "GET" and request.data is None
        assert request.get_header("Authorization") == "Bearer SYNTHETIC_SECRET"
        assert request.get_header("Cache-control") == "no-cache" and timeout == 4
        if request.full_url.endswith("/key"):
            return Response(account(used=3, limit=50, remaining=47))
        return Response(
            {
                "data": [
                    {
                        "id": "public/free:free",
                        "pricing": {"prompt": "0", "completion": "0"},
                        "supported_parameters": ["tools"],
                    },
                    {"id": "public/paid", "pricing": {"prompt": "0", "completion": "0"}},
                    {
                        "id": "public/extra:free",
                        "pricing": {"prompt": "0", "completion": "0", "request": "0.01"},
                    },
                    {"id": "public/missing:free", "pricing": {"prompt": "0"}},
                ]
            }
        )

    monkeypatch.setattr(usage, "urlopen", open_request)
    result = usage.read_openrouter_allowance(timeout_seconds=4, include_models=True)
    assert calls == [usage.BASE_URL + "/key", usage.BASE_URL + "/models/user"]
    assert result["status"] == "observed" and result["completion_requests"] == 0
    assert result["checks"][0]["free_model_daily_requests"] == dict(used=3, limit=50, remaining=47)
    assert result["checks"][1]["free_models"] == [{"id": "public/free:free", "tools": True}]
    assert "SYNTHETIC_SECRET" not in json.dumps(result)
    assert "PRIVATE_LABEL" not in json.dumps(result)


@pytest.mark.parametrize(
    "counter",
    [{}, {"used": True, "limit": 50, "remaining": 49}, {"used": 3, "limit": 50, "remaining": 48}],
)
def test_unknown_or_invalid_counter_stays_unknown(monkeypatch, counter):
    monkeypatch.setattr(usage, "urlopen", lambda *a, **k: Response(account(**counter)))
    result = usage.read_openrouter_allowance(api_key="synthetic")
    assert result["checks"][0]["free_model_daily_requests"] is None


@pytest.mark.parametrize("headers", [{"Age": "5"}, {"Age": "unknown"}, {"CF-Cache-Status": "HIT"}])
def test_cached_quota_is_not_current_capacity(monkeypatch, headers):
    monkeypatch.setattr(
        usage, "urlopen", lambda *a, **k: Response(account(used=0, limit=50, remaining=50), headers)
    )
    result = usage.read_openrouter_allowance(api_key="synthetic")
    assert result["checks"][0]["free_model_daily_requests"] is None
    assert result["checks"][0]["cached"]


@pytest.mark.parametrize("failure", ["http", "transport", "oversize", "bad_json", "bad_shape"])
def test_failed_metadata_stops_without_raw_error_or_later_request(monkeypatch, failure):
    calls = []

    def open_request(request, **kwargs):
        calls.append(request)
        if failure == "http":
            raise HTTPError(request.full_url, 401, "SYNTHETIC_SECRET", Message(), None)
        if failure == "transport":
            raise URLError("SYNTHETIC_SECRET")
        return Response(
            b"x" * 65537
            if failure == "oversize"
            else b"SYNTHETIC_SECRET"
            if failure == "bad_json"
            else []
        )

    monkeypatch.setattr(usage, "urlopen", open_request)
    result = usage.read_openrouter_allowance(api_key="synthetic", include_models=True)
    assert len(calls) == 1 and result["status"] == "unavailable"
    assert "SYNTHETIC_SECRET" not in json.dumps(result)
    assert result["checks"][0]["failure_kind"]


def test_missing_credentials_never_read_files_or_request_metadata(monkeypatch):
    from pathlib import Path

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(usage, "urlopen", lambda *a, **k: pytest.fail("Network attempted"))
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("Credential file discovered"))
    result = usage.read_openrouter_allowance()
    assert result["reason"] == "credential_not_configured" and result["checks"] == []


@pytest.mark.parametrize("timeout", [True, 0, -1, float("inf"), float("nan")])
def test_invalid_timeouts_refuse_before_io(monkeypatch, timeout):
    monkeypatch.setattr(usage, "urlopen", lambda *a, **k: pytest.fail("Network attempted"))
    with pytest.raises(ValueError, match="finite and positive"):
        usage.read_openrouter_allowance(api_key="synthetic", timeout_seconds=timeout)
