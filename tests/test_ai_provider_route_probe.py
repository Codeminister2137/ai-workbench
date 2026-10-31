"""Route reachability sweep; transport mocked, no network and no inference."""

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

from ai_provider import route_probe
from ai_provider.route_probe import RouteProbe, probe_all, probe_route


class Response(BytesIO):
    status = 200

    def __init__(self, raw):
        super().__init__(raw if isinstance(raw, bytes) else json.dumps(raw).encode())
        self.headers = {}


def transport(monkeypatch, *, payload=None, status=200, error=None):
    calls = []

    def send(http_request, **kwargs):
        calls.append(http_request)
        if error is not None:
            raise error
        if status != 200:
            raise HTTPError(http_request.full_url, status, "error", Message(), None)
        return Response(payload)

    monkeypatch.setattr(route_probe, "urlopen", send)
    return calls


def test_openai_shaped_list_counts_models_and_samples_ids(monkeypatch):
    calls = transport(monkeypatch, payload={"data": [{"id": f"m-{i}"} for i in range(8)]})
    result = probe_route("r", "https://x/models", api_key="k")
    assert result.reachable is True
    assert result.auth_ok is True
    assert result.models_seen == 8
    assert result.sample_ids == tuple(f"m-{i}" for i in range(5))
    assert calls[0].get_header("Authorization") == "Bearer k"
    assert result.error is None


def test_ollama_shaped_list_uses_names_without_key(monkeypatch):
    transport(monkeypatch, payload={"models": [{"name": "a"}, {"name": "b"}]})
    result = probe_route("ollama", "http://localhost:11434/api/tags")
    assert (result.reachable, result.auth_ok, result.models_seen) == (True, None, 2)
    assert result.sample_ids == ("a", "b")


def test_unauthorized_means_reachable_but_refused(monkeypatch):
    transport(monkeypatch, status=401)
    result = probe_route("r", "https://x/models", api_key="bad")
    assert (result.reachable, result.auth_ok) == (True, False)
    assert result.error == "http-401"


def test_network_error_means_unreachable(monkeypatch):
    transport(monkeypatch, error=URLError("down"))
    result = probe_route("r", "https://x/models")
    assert (result.reachable, result.models_seen) == (False, None)
    assert result.error == "URLError"


def test_unrecognized_shape_is_recorded_not_raised(monkeypatch):
    transport(monkeypatch, payload={"unexpected": []})
    result = probe_route("r", "https://x/models")
    assert (result.reachable, result.models_seen, result.error) == (
        True,
        None,
        "unrecognized-shape",
    )


def test_sweep_covers_every_route_and_survives_one_bad_probe(monkeypatch):
    seen = []

    def flaky(route, url, **kwargs):
        seen.append(route)
        if route == "meta":
            raise RuntimeError("boom")
        return RouteProbe(route, url, "t", True, None, 1, ("m",), 3, None)

    monkeypatch.setattr(route_probe, "probe_route", flaky)
    results = probe_all({})
    assert [item.route for item in results] == [name for name, _, _ in route_probe.ROUTES]
    assert seen == [item.route for item in results]
    meta = next(item for item in results if item.route == "meta")
    assert (meta.reachable, meta.error) == (False, "RuntimeError")


def test_summary_distinguishes_states():
    assert (
        "unreachable"
        in RouteProbe("r", "u", "t", False, None, None, (), None, "URLError").summary()
    )
    assert (
        "auth-refused" in RouteProbe("r", "u", "t", True, False, None, (), 1, "http-401").summary()
    )
    assert "3 models" in RouteProbe("r", "u", "t", True, True, 3, ("a",), 4, None).summary()
