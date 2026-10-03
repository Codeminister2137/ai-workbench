"""Discovery routing, provider contracts, spending boundaries, and evidence tests."""

import io
import json
import socket
import time
from argparse import ArgumentParser, Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_agent.contracts import ToolCall
from ai_agent.tools import research_search
from ai_agent.tools.base import ToolContext
from ai_agent.tools.research_search import SearchFailure, SearchResponse, SearchSession
from ai_orchestrator.search_policy import search_routes
from ai_provider.research_execution import ResearchExecution, validate_research_arguments
from test_research_tools import execution as research_execution_fixture
from test_research_tools import receipt, valid_report

execution = research_execution_fixture


def test_tracking_flags_cannot_be_silently_ignored_for_coding(tmp_path, capsys):
    args = Namespace(tool_profile="coding", research_report=None, search_privacy="reduced_tracking")
    with pytest.raises(SystemExit):
        validate_research_arguments(args, tmp_path, ArgumentParser())
    assert "search options require --tool-profile research" in capsys.readouterr().err


def test_reduced_tracking_cli_rejects_api_override(tmp_path, capsys):
    args = Namespace(
        tool_profile="research",
        research_report=Path("report.md"),
        search_privacy="reduced_tracking",
        search_provider="brave",
    )
    with pytest.raises(SystemExit):
        validate_research_arguments(args, tmp_path, ArgumentParser())
    assert "conflicts with reduced tracking" in capsys.readouterr().err


def test_disabled_discovery_is_not_registered(execution):
    disabled = ResearchExecution(
        execution.root,
        Path("report.md"),
        execution.store,
        execution.run_id,
        search_options={"privacy": "disabled"},
    )
    assert "search_web" not in {tool.name for tool in disabled.registry.list_definitions()}


def response(data):
    return SearchResponse(data, "a" * 64)


def free_usage():
    return {
        "account": {
            "current_plan": "Researcher",
            "plan_usage": 0,
            "plan_limit": 1000,
            "paygo_usage": 0,
            "paygo_limit": 0,
        },
        "key": {"usage": 0, "limit": 1000},
    }


def source_data():
    return {
        "results": [
            {"title": "Python", "url": "https://docs.python.org/3/", "content": "Public source"}
        ]
    }


def test_route_policy():
    assert search_routes("auto", "standard") == ("tavily", "brave", "searxng")
    assert search_routes("brave", "standard") == ("brave", "tavily", "searxng")
    assert search_routes("auto", "reduced_tracking") == ("searxng",)
    assert search_routes("auto", "standard", fallback=False) == ("tavily",)
    assert not search_routes("auto", "disabled")
    assert not search_routes("none", "standard")
    with pytest.raises(ValueError, match="tracking"):
        search_routes("tavily", "reduced_tracking")


def test_missing_credentials_skipped_and_full_queries_saved():
    events, requests = [], []

    def transport(*args):
        requests.append(args)
        return response(source_data())

    session = SearchSession(lambda kind, value: events.append((kind, value)), transport=transport)
    output = session.search("python API docs")
    assert len(requests) == 1
    assert len(events) == 3
    assert all(e[0] == "search_receipts" and e[1]["query"] == "python API docs" for e in events)
    assert output["attempts"][0]["query_transmitted"] is False
    assert session.current == "searxng"
    assert output["results"][0]["url"] == "https://docs.python.org/3/"
    requests.clear()
    assert len(session.search("next query")["attempts"]) == 1
    assert len(requests) == 1


def test_tavily_preflight_and_basic_only_translation():
    calls, events = [], []

    def transport(*args):
        calls.append(args)
        return response(free_usage() if args[0].endswith("usage") else source_data())

    session = SearchSession(
        lambda kind, value: events.append(value), tavily_key="secret", transport=transport
    )
    session.search("python")
    assert calls[0][1:3] == ("GET", {"Authorization": "Bearer secret"})
    assert calls[1][3] == {
        "query": "python",
        "max_results": 5,
        "search_depth": "basic",
        "auto_parameters": False,
        "include_answer": False,
        "include_raw_content": False,
        "include_usage": True,
    }
    assert "secret" not in json.dumps(events) and "secret" not in repr(session)
    session.search("second")
    assert sum(c[0].endswith("usage") for c in calls) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_plan", "Bootstrap"),
        ("paygo_limit", 100),
        ("paygo_usage", 1),
        ("plan_limit", 1001),
        ("plan_usage", 1000),
        ("plan_usage", -1),
        ("plan_usage", float("nan")),
        ("plan_usage", True),
        ("plan_limit", None),
    ],
)
def test_unsafe_or_exhausted_tavily_account_never_receives_query(field, value):
    calls, events = [], []
    usage = free_usage()
    usage["account"][field] = value

    def transport(*args):
        calls.append(args)
        return response(usage if args[0].endswith("usage") else source_data())

    session = SearchSession(
        lambda kind, value: events.append(value), tavily_key="secret", transport=transport
    )
    output = session.search("public topic")
    assert not any(c[0] == "https://api.tavily.com/search" for c in calls)
    assert output["attempts"][0]["query_transmitted"] is False
    assert output["attempts"][-1]["provider"] == "searxng"
    assert "tavily" in session.disabled


@pytest.mark.parametrize("free,storage", [(False, False), (True, False), (False, True)])
def test_brave_gated_by_cost_and_storage_rights(free, storage):
    calls = []
    session = SearchSession(
        lambda *a: None,
        primary="brave",
        brave_key="key",
        brave_free_only=free,
        brave_storage_allowed=storage,
        transport=lambda *a: calls.append(a) or response(source_data()),
    )
    output = session.search("public")
    assert output["attempts"][0]["status"] == "skipped"
    assert all("brave.com" not in c[0] for c in calls)


def test_brave_adapter_and_quota_fallback():
    calls = []

    def transport(*args):
        calls.append(args)
        if "brave.com" in args[0]:
            raise SearchFailure("quota", status=402)
        return response(source_data())

    session = SearchSession(
        lambda *a: None,
        primary="brave",
        brave_key="key",
        brave_free_only=True,
        brave_storage_allowed=True,
        transport=transport,
    )
    output = session.search("public & query")
    assert calls[0][2] == {"X-Subscription-Token": "key"}
    assert "q=public+%26+query" in calls[0][0]
    assert output["attempts"][0]["reason"] == "quota"
    assert session.current == "searxng"
    assert "brave" in session.disabled
    session = SearchSession(
        lambda *a: None,
        primary="brave",
        brave_key="key",
        brave_free_only=True,
        brave_storage_allowed=True,
        transport=lambda *a: response(
            {"web": {"results": [{"url": "https://example.com", "description": "snippet"}]}}
        ),
    )
    assert session.search("public")["results"][0]["snippet"] == "snippet"


def test_reduced_tracking_never_leaks_to_other_provider_on_failure():
    calls = []

    def transport(*args):
        calls.append(args)
        raise SearchFailure("rate_limit", status=429)

    session = SearchSession(
        lambda *a: None,
        privacy="reduced_tracking",
        tavily_key="key",
        brave_key="key",
        transport=transport,
    )
    assert "error" in session.search("public")
    assert len(calls) == 1 and "mectov" in calls[0][0]


def test_genuine_empty_results_do_not_trigger_fallback():
    session = SearchSession(
        lambda *a: None,
        tavily_key="key",
        transport=lambda *a: response(free_usage() if a[0].endswith("usage") else {"results": []}),
    )
    output = session.search("public")
    assert "error" not in output and output["results"] == []
    assert len(output["attempts"]) == 1


def test_searxng_captcha_is_failure():
    session = SearchSession(
        lambda *a: None,
        primary="searxng",
        fallback=False,
        transport=lambda *a: response(
            {"results": [], "unresponsive_engines": [["google", "CAPTCHA"]]}
        ),
    )
    assert session.search("public")["attempts"][0]["reason"] == "upstream_unavailable"


def test_budget_expiry_sends_nothing():
    session = SearchSession(
        lambda *a: None,
        deadline=time.monotonic() - 1,
        transport=lambda *a: pytest.fail("No HTTP after budget"),
    )
    assert "error" in session.search("public")


@pytest.mark.parametrize(
    "query,count", [("", 5), ("x" * 1001, 5), ("q\nsecret", 5), ("q", 0), ("q", 11), ("q", True)]
)
def test_invalid_arguments_do_not_send_or_persist(query, count):
    session = SearchSession(
        lambda *a: pytest.fail("No invalid receipts"),
        transport=lambda *a: pytest.fail("No invalid HTTP"),
    )
    with pytest.raises(ValueError):
        session.search(query, count)


def test_discovery_receipts_do_not_satisfy_fetch_gate(execution):
    enabled = ResearchExecution(
        execution.root,
        Path("report.md"),
        execution.store,
        execution.run_id,
        search_options={"primary": "searxng"},
    )
    assert enabled.search is not None
    enabled.search.transport = lambda *a: response(source_data())
    result = enabled.registry.execute(
        ToolCall("search_web", {"query": "python"}), ToolContext(enabled.root)
    )
    assert not result.is_error
    enabled.registry.execute(
        ToolCall("write_research_report", {"content": valid_report()}), ToolContext(enabled.root)
    )
    assert any("no successful current-run receipt" in e for e in enabled.validate())
    assert "discovery only" in enabled.review_evidence()
    enabled.record("fetch_receipts", receipt())
    assert enabled.validate() == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://example.com/search",
        "https://u:p@example.com/search",
        "https://example.com/search?q=secret",
        "https://example.com/#fragment",
    ],
)
def test_invalid_endpoints_rejected(endpoint):
    with pytest.raises(ValueError, match="endpoint"):
        SearchSession(lambda *a: None, endpoint=endpoint)


def test_authenticated_transport_rejects_other_origin():
    with pytest.raises(SearchFailure, match="credential_origin"):
        research_search.search_json(
            "https://example.com/search", "GET", {"Authorization": "secret"}, None, 1
        )


def fake_connection(monkeypatch, status=200, body=b'{"results": []}', encoding="identity"):
    calls = []

    class Connection:
        sock = None

        def __init__(self, *args):
            calls.append(args)

        def request(self, *args, **kwargs):
            calls.append((args, kwargs))

        def getresponse(self):
            stream = io.BytesIO(body)
            return SimpleNamespace(
                status=status,
                read1=stream.read1,
                getheader=lambda name, default=None: encoding
                if name == "Content-Encoding"
                else default,
            )

        def close(self):
            calls.append("closed")

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("8.8.8.8", 443))])
    monkeypatch.setattr(research_search, "_PinnedHTTPS", Connection)
    return calls


@pytest.mark.parametrize(
    "status,category",
    [
        (302, "unavailable"),
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate_limit"),
        (432, "quota"),
        (503, "unavailable"),
    ],
)
def test_http_failures_are_sanitized_and_no_redirect(monkeypatch, status, category):
    calls = fake_connection(monkeypatch, status, b"response body secret")
    with pytest.raises(SearchFailure, match=category) as error:
        research_search.search_json(
            "https://api.tavily.com/search",
            "POST",
            {"Authorization": "secret"},
            {"query": "public"},
            1,
        )
    assert "secret" not in str(error.value)
    assert calls[-1] == "closed"
    assert len(calls) == 3


@pytest.mark.parametrize(
    "body,encoding",
    [
        (b"<html>CAPTCHA</html>", "identity"),
        (b"[]", "identity"),
        (b"x" * 512001, "identity"),
        (b"{}", "gzip"),
    ],
    ids=["html", "array", "oversize", "compressed"],
)
def test_malformed_compressed_or_oversized_json_rejected(monkeypatch, body, encoding):
    fake_connection(monkeypatch, body=body, encoding=encoding)
    with pytest.raises(SearchFailure):
        research_search.search_json("https://example.com/search", "GET", {}, None, 1)


def test_search_transport_pins_public_dns_and_has_no_ambient_credentials(monkeypatch):
    calls = fake_connection(monkeypatch)
    result = research_search.search_json("https://example.com/search?q=public", "GET", {}, None, 1)
    assert calls[0][0:3] == ("example.com", 443, "8.8.8.8")
    assert "Authorization" not in calls[1][1]["headers"]
    assert result.data == {"results": []} and len(result.sha256) == 64


def test_search_transport_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("127.0.0.1", 443))])
    with pytest.raises(SearchFailure):
        research_search.search_json("https://example.com/search", "GET", {}, None, 1)
