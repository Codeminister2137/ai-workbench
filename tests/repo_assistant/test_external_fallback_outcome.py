"""External fallback outcome separates a completed run from a failed one."""

from types import SimpleNamespace

import pytest
from ai_agent.repo_coding_assistant import _external_fallback_response
from ai_provider.errors import ProviderError
from ai_provider.external_agents import ExternalAgentEventSummary, ExternalAgentResult

TARGET = SimpleNamespace(provider="external", model="test-model", route_id="external-route")


def _result(*, failure_reason: str | None = None, mcp_warnings: tuple[str, ...] = ()):
    return ExternalAgentResult(
        command=("external",),
        returncode=0,
        stdout="",
        stderr="",
        events=ExternalAgentEventSummary(
            "Done.",
            (),
            (),
            (),
            (),
            None,
            failure_reason,
            (),
            mcp_warnings,
        ),
    )


def test_completed_run_with_unresolved_mcp_warning_is_not_a_failed_fallback():
    # ADR-064: a completed run keeps its answer; the unresolved MCP recovery
    # is reported as a warning instead of failing the fallback route.
    response = _external_fallback_response(_result(mcp_warnings=("unresolved failure",)), TARGET)
    assert response.message.content == "Done."


def test_failed_run_still_raises_in_the_external_fallback():
    with pytest.raises(ProviderError, match="sandbox denied"):
        _external_fallback_response(_result(failure_reason="sandbox denied"), TARGET)
