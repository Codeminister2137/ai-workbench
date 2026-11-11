"""search_web is registered everywhere coding tools are."""

from __future__ import annotations

from ai_agent import ToolContext, default_coding_tools
from ai_agent.contracts import ToolCall
from ai_agent.tool_profiles import CODING_PROFILE, shared_tool_registry


def test_present_in_default_coding_registry() -> None:
    tool = default_coding_tools().get("search_web")
    assert tool is not None
    assert tool.definition.name == "search_web"


def test_present_in_shared_coding_registry(tmp_path) -> None:
    assert "search_web" in CODING_PROFILE.tool_names
    registry = shared_tool_registry("coding")
    assert registry.get("search_web") is not None


def test_executes_through_stubbed_session(tmp_path, monkeypatch) -> None:
    from ai_agent.tools.research_search import SearchSession

    def fake_search(self, query, count=5):
        assert query == "python loops"
        return {"results": [{"title": "t", "url": "https://example.invalid"}]}

    monkeypatch.setattr(SearchSession, "search", fake_search)
    tool = default_coding_tools().get("search_web")
    assert tool is not None
    result = tool.run(ToolCall("search_web", {"query": "python loops"}), ToolContext(tmp_path))
    assert result.is_error is False
    assert "example.invalid" in result.output


def test_endpoint_configurable_via_env(monkeypatch) -> None:
    from ai_agent.tools.research_search import DEFAULT_SEARXNG_ENDPOINT, SearchSession

    session = SearchSession.from_environment(lambda _e, _r: None)
    assert session.endpoint == DEFAULT_SEARXNG_ENDPOINT
    monkeypatch.setenv("SEARXNG_ENDPOINT", "https://example.invalid/search")
    session = SearchSession.from_environment(lambda _e, _r: None)
    assert session.endpoint == "https://example.invalid/search"
