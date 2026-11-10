"""Groundedness gate: claims need tool evidence."""

from __future__ import annotations

import pytest
from ai_agent import (
    AgentLoop,
    PermissionManager,
    PermissionPolicy,
    ToolContext,
    default_coding_tools,
)
from ai_agent.contracts import ToolResult
from ai_agent.groundedness import check_groundedness, find_verification_claims
from ai_provider import (
    AIMessage,
    AIResponse,
    BackendInfo,
    BackendLocation,
    FinishReason,
    MessageRole,
    PrivacyClass,
    ProviderError,
    UsageMetadata,
)


def _result(name: str, *, error: bool = False) -> ToolResult:
    return ToolResult(name=name, output="ok", is_error=error)


def test_claim_classes_detected() -> None:
    claims = find_verification_claims("I verified the code and confirmed the fix.")
    assert {claim.claim_class for claim in claims} == {"inspection"}
    claims = find_verification_claims("Created the file and fixed the bug.")
    assert {claim.claim_class for claim in claims} == {"modification"}
    claims = find_verification_claims("All tests passed; pytest reports 5 passed.")
    assert {claim.claim_class for claim in claims} == {"test_execution"}


def test_requests_negations_and_future_work_are_not_claims() -> None:
    report = (
        "Please verify this later. I could not verify the network path. "
        "This summary is unverified. Testing requires a device lab. "
        "To verify, run the suite. We must confirm with the owner."
    )
    assert find_verification_claims(report) == ()


def test_zero_tool_claims_are_unsupported() -> None:
    verdict = check_groundedness("I verified the changes; all tests passed.", ())
    assert not verdict.ok
    assert {claim.claim_class for claim in verdict.unsupported} == {
        "inspection",
        "test_execution",
    }


def test_matching_evidence_supports_each_class() -> None:
    verdict = check_groundedness(
        "I verified the code.",
        (_result("read_file"),),
    )
    assert verdict.ok
    verdict = check_groundedness(
        "Created the helper.",
        (_result("create_file"),),
    )
    assert verdict.ok
    verdict = check_groundedness(
        "All tests passed.",
        (_result("run_command"),),
    )
    assert verdict.ok


def test_wrong_class_or_failed_tool_does_not_support() -> None:
    verdict = check_groundedness(
        "All tests passed.",
        (_result("read_file"),),
    )
    assert not verdict.ok
    verdict = check_groundedness(
        "All tests passed.",
        (_result("run_command", error=True),),
    )
    assert not verdict.ok
    verdict = check_groundedness(
        "Created the helper.",
        (_result("read_file"),),
    )
    assert not verdict.ok


def test_unknown_tool_backs_inspection_only() -> None:
    verdict = check_groundedness("I checked the system.", (_result("custom_probe"),))
    assert verdict.ok
    verdict = check_groundedness("All tests passed.", (_result("custom_probe"),))
    assert not verdict.ok


class ClaimClient:
    backend = BackendInfo(provider="fake", model="test", location=BackendLocation.LOCAL)

    def __init__(self, *answers: str) -> None:
        self.answers = answers
        self.requests = []
        self.calls = 0

    def complete(self, request):
        self.requests.append(request)
        text = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return AIResponse(
            message=AIMessage(MessageRole.ASSISTANT, text),
            backend=self.backend,
            finish_reason=FinishReason.STOP,
            usage=UsageMetadata(),
        )

    def stream(self, request):
        raise NotImplementedError


def test_loop_feedback_drives_downgrade_to_unverified_summary(tmp_path) -> None:
    client = ClaimClient(
        "I verified the implementation.",
        "Unverified summary: no checks were run.",
    )
    result = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
        max_iterations=3,
        require_grounded_reports=True,
    ).run("Check it", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert result.response.message.content == "Unverified summary: no checks were run."
    assert result.iterations == 2
    assert "groundedness" in client.requests[1].messages[-1].content


def test_persistent_claims_stop_without_new_allowance(tmp_path) -> None:
    client = ClaimClient("I verified the implementation.")
    with pytest.raises(ProviderError, match="without observed tool evidence"):
        AgentLoop(
            client,
            default_coding_tools(),
            ToolContext(tmp_path),
            permissions=PermissionManager(policy=PermissionPolicy.permissive()),
            max_iterations=5,
            require_grounded_reports=True,
        ).run("Check it", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert client.calls == 2


def test_grounded_reports_not_required_by_default(tmp_path) -> None:
    client = ClaimClient("I verified the implementation.")
    loop = AgentLoop(
        client,
        default_coding_tools(),
        ToolContext(tmp_path),
        permissions=PermissionManager(policy=PermissionPolicy.permissive()),
    )
    assert loop.require_grounded_reports is False
    result = loop.run("Check it", privacy_class=PrivacyClass.LOCAL_ONLY)
    assert result.response.message.content == "I verified the implementation."
