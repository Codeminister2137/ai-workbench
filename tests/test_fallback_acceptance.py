"""Live fixture validation must never execute candidate Python."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "fallback_acceptance", Path(__file__).resolve().parents[1] / "scripts/fallback-acceptance.py"
)
assert spec is not None and spec.loader is not None
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


@pytest.mark.parametrize(
    "source",
    [
        "import os\nvalue = 2\n",
        "value = int('2')",
        "value = 1 + 1",
        "value = True",
        "value = 2.0",
        "other = 2",
        "value = other = 2",
        "value =",
        "",
    ],
)
def test_fixed_assignment_validator_refuses_executable_or_invalid_source(source):
    assert not harness.valid_source(source)


def test_fixed_assignment_validator_accepts_preserved_comment():
    assert harness.valid_source("# Partial work before simulated quota exhaustion\nvalue = 2\n")


@pytest.mark.parametrize("client", ["copilot", "kiro"])
def test_shared_live_harness_with_synthetic_client(tmp_path, monkeypatch, client):
    import sys

    from ai_agent.contracts import ToolCall
    from ai_agent.permissions import PermissionManager, PermissionPolicy
    from ai_agent.shared_approvals import scoped_registry
    from ai_agent.tool_profiles import shared_tool_registry
    from ai_agent.tools import ToolContext
    from ai_provider.agent_readiness import AgentReadiness
    from ai_provider.coding_sessions import ACTIVE_SESSION
    from ai_provider.external_agents import ExternalAgentResult

    monkeypatch.setattr(harness, "__file__", str(tmp_path / "scripts/fallback-acceptance.py"))
    monkeypatch.setattr(sys, "argv", ["acceptance", "--shared-coding", "--fallback-client", client])
    monkeypatch.setenv("GITHUB_COPILOT_COMMAND", "fixture-copilot")
    monkeypatch.setenv("KIRO_COMMAND", "fixture-kiro")
    monkeypatch.setattr(
        harness.execution_fallback,
        "check_agent_readiness",
        lambda method: AgentReadiness(True, "synthetic"),
    )

    def execute(prompt, config, **kwargs):
        session = ACTIVE_SESSION.get()
        assert session is not None
        registry = scoped_registry(
            shared_tool_registry("coding"),
            PermissionManager(PermissionPolicy.workspace_write()),
            config.cwd,
            session.session_id,
            config.shared_run_id,
        )
        registry = session.observe_registry(
            registry, operation_prefix=f"shared:{session.session_id}:{config.shared_run_id}:"
        )
        result = registry.execute(
            ToolCall(
                "edit_file", {"path": "source.py", "old_text": "value = 1", "new_text": "value = 2"}
            ),
            ToolContext(config.cwd),
        )
        assert not result.is_error
        return ExternalAgentResult((), 0, "done", "")

    monkeypatch.setattr(harness.cli, "_run_external_agent", execute)
    assert harness.main() == 0
