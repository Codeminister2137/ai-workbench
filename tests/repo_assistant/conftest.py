"""Account-readiness mocks scoped to CLI regression tests."""

import pytest


@pytest.fixture(autouse=True)
def mock_fallback_account_checks(monkeypatch):
    """Existing CLI regression tests never contact installed native client accounts."""
    from ai_provider.agent_readiness import AgentReadiness

    monkeypatch.setattr(
        "ai_provider.execution_fallback.check_agent_readiness",
        lambda method: AgentReadiness(method.value == "codex_cli", "mocked account check"),
    )
