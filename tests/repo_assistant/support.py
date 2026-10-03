"""Shared example-entrypoint adapter and fake clients for CLI tests."""

from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "ai_provider"
    / "examples"
    / "repo_coding_assistant.py"
)
sys.path.insert(0, str(_EXAMPLE_PATH.parent))
_SPEC = importlib.util.spec_from_file_location("repo_coding_assistant_example", _EXAMPLE_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_EXAMPLE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _EXAMPLE
_SPEC.loader.exec_module(_EXAMPLE)
build_repo_prompt = _EXAMPLE.build_repo_prompt
main = _EXAMPLE.main
build_delegation_context = _EXAMPLE.build_delegation_context
run_local_context_delegation = _EXAMPLE.run_local_context_delegation
_run_native_agent = _EXAMPLE._run_native_agent
_TeeOutput = _EXAMPLE._TeeOutput
execute_actions = _EXAMPLE.execute_actions
extract_actions = _EXAMPLE.extract_actions
load_prompt_context = _EXAMPLE.load_prompt_context
AssistantAction = _EXAMPLE.AssistantAction
parse_external_agent_jsonl = _EXAMPLE.parse_external_agent_jsonl
parse_response_scrutiny_report = _EXAMPLE.parse_response_scrutiny_report


class _AsciiTerminal(StringIO):
    encoding = "ascii"

    def write(self, text: str) -> int:
        text.encode(self.encoding)
        return super().write(text)


def _implementation_scrutiny_result():
    return SimpleNamespace(
        response=SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    "VERDICT: pass\nSCORE: 8\nSTRENGTHS: validated\nISSUES: none\n"
                    "RECOMMENDED_NEXT_ACTION: review\nREVISED_RESPONSE: work validated"
                )
            )
        )
    )


class _NativeFakeClient:
    def __init__(self) -> None:
        from ai_provider import BackendInfo, BackendLocation

        self.backend = BackendInfo(provider="ollama", model="test", location=BackendLocation.LOCAL)
        self.calls = 0

    def complete(self, request):
        from ai_provider import AIMessage, AIResponse, AIToolCall, FinishReason, MessageRole

        self.calls += 1
        if self.calls == 1:
            message = AIMessage(
                MessageRole.ASSISTANT,
                "",
                tool_calls=(
                    AIToolCall(
                        "call-1",
                        "create_file",
                        {"path": "native.txt", "content": "native"},
                    ),
                ),
            )
        else:
            message = AIMessage(MessageRole.ASSISTANT, "native complete")
        return AIResponse(
            message=message,
            backend=self.backend,
            finish_reason=FinishReason.STOP,
        )

    def stream(self, request):
        raise NotImplementedError
