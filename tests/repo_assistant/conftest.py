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


@pytest.fixture(autouse=True)
def mock_native_runtime_admission(monkeypatch):
    """Legacy loop fixtures use synthetic models; admission has separate contract tests."""
    monkeypatch.setattr(
        "ai_provider.repo_coding_assistant.prepare_native_coding_client",
        lambda client, config, args, diagnostic: client,
    )


@pytest.fixture(autouse=True)
def mock_fallback_runtime_probes(monkeypatch):
    """CLI regressions use fake clients; runtime evidence has dedicated boundary tests."""
    from ai_provider import ProviderError

    def unavailable_identity(config):
        raise ProviderError("Mocked native runtime is unavailable")

    monkeypatch.setattr(
        "ai_provider.repo_coding_assistant.installed_native_identity", unavailable_identity
    )
    monkeypatch.setattr(
        "ai_provider.repo_coding_assistant.is_ollama_server_available", lambda *a: False
    )
