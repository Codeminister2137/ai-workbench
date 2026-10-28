"""Actual native requests disclose their reply ceiling without changing the task."""

from argparse import Namespace

import pytest
from ai_agent import repo_coding_assistant as cli
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendConfig,
    BackendInfo,
    BackendLocation,
    MessageRole,
    ProviderKind,
)
from ai_provider.closeout import FINAL_RESPONSE_INSTRUCTION


@pytest.mark.parametrize("rounds,custom", [(1, None), (3, None), (7, "Owner system instructions")])
def test_native_request_discloses_configured_reply_ceiling(rounds, custom, tmp_path, monkeypatch):
    requests = []

    class Client:
        backend = BackendInfo("fake", "budget-check", BackendLocation.LOCAL)

        def complete(self, request):
            requests.append(request)
            return AIResponse(
                AIMessage(MessageRole.ASSISTANT, "No tool actions requested."), self.backend
            )

    monkeypatch.setattr(cli, "create_chat_client", lambda config: Client())
    args = Namespace(
        start_ollama=False, system=custom, max_action_rounds=rounds, approval_policy="read_only"
    )
    result = cli._run_native_agent(
        "Inspect only",
        BackendConfig(ProviderKind.OLLAMA, "test"),
        cli.coding_task_profile(privacy_class=OrchestratorPrivacyClass.LOCAL_ONLY),
        args,
        tmp_path,
    )
    assert result.iterations == 1 and len(requests) == 1
    request = requests[0]
    system = next(m.content for m in request.messages if m.role is MessageRole.SYSTEM)
    expected = (
        f"Host action budget: at most {rounds} model replies for this invocation "
        "(including the final report)."
    )
    assert system.count(expected) == 1
    assert FINAL_RESPONSE_INSTRUCTION in system
    assert "Reserve replies for validation, correction and the final report." in system
    assert "Other guards may stop earlier; this ceiling grants no new actions or time." in system
    if custom:
        assert custom in system
    assert request.messages[-1].content == "Inspect only"
    assert result.tool_results == ()
