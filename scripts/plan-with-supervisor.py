"""Chat with the Baseten supervisor to draft one queue objective.

Usage example:
    python scripts/plan-with-supervisor.py \
        --goal "Add focused regression tests for check_submission_eligibility.py" \
        --files scripts/check_submission_eligibility.py,tests/test_check_submission_eligibility.py

The script sends the goal and file context to the Baseten event model, asks it
to propose exactly one queue objective entry, and prints the JSON proposal.
Review and edit the output before adding it to a queue.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ai_provider lives in the workbench root package tree.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/ai_provider/src"))
sys.path.insert(0, str(ROOT / "packages/ai_orchestrator/src"))

from ai_provider.adapters.baseten import (  # noqa: E402
    BASETEN_BASE_URL,
    BASETEN_HACKATHON_MODEL,
    BasetenChatClient,
)
from ai_provider.config import BackendConfig, ProviderKind  # noqa: E402
from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass  # noqa: E402

DEFAULT_MAX_CALLS = 5


class LowReasoningClient(BasetenChatClient):
    def _chat_payload(self, request, *, stream):
        payload = super()._chat_payload(request, stream=stream)
        payload["reasoning_effort"] = "low"
        return payload


def _read_key() -> str:
    values = [
        line.partition("=")[2].strip().strip("\"'")
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines()
        if line.partition("=")[0].strip() == "BASETEN_HACKATHON_API_KEY"
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError("Exactly one BASETEN_HACKATHON_API_KEY entry is required in .env")
    return values[0]


def _load_file_context(paths: list[str]) -> str:
    parts: list[str] = []
    for rel in paths:
        p = Path(rel)
        if not p.is_absolute():
            p = Path.cwd() / p
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = f"[missing: {rel}]"
        except Exception as exc:  # noqa: BLE001
            text = f"[error reading {rel}: {exc}]"
        parts.append(f"--- {rel} ---\n{text}")
    return "\n\n".join(parts)


def _build_prompt(goal: str, file_context: str) -> str:
    return (
        "You are a Baseten supervisor helping to plan one bounded development "
        "objective for an unattended hackathon-credit loop.\n\n"
        f"User goal: {goal}\n\n"
        f"File context:\n{file_context}\n\n"
        "Propose exactly ONE queue objective entry as JSON. Use this shape:\n"
        "{\n"
        '  "id": "kebab-case-identifier",\n'
        '  "kind": "implement" | "workbench-implement" | "propose",\n'
        '  "worktree": "path/to/worktree",\n'
        '  "allowlist": ["relative/path.py"],\n'
        '  "files": ["relative/path.py"],\n'
        '  "max_calls": 5,\n'
        '  "objective": "clear, bounded instructions for the implementer",\n'
        '  "supervisor_model": "meta-models/muse-spark-open-1026",\n'
        '  "implementer_model": "meta-models/muse-spark-open-1026"\n'
        "}\n\n"
        "Rules:\n"
        "- Only one objective.\n"
        "- Keep it small enough to complete in a few model calls.\n"
        "- For Operator code use kind=implement with allowlist.\n"
        "- For Workbench tooling use kind=workbench-implement with files.\n"
        "- Do not propose anything that needs new dependencies, external services, "
        "judge credentials, or public release.\n"
        "Return ONLY valid JSON, no markdown fences, no commentary."
    )


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Model response contained no JSON object")
    return json.loads(text[start : end + 1])


def plan_objective(user_goal: str, files: list[str]) -> dict:
    """Ask the Baseten supervisor to propose one queue objective entry."""
    client = LowReasoningClient(
        BackendConfig(
            provider=ProviderKind.BASETEN,
            model=BASETEN_HACKATHON_MODEL,
            base_url=BASETEN_BASE_URL,
            api_key=_read_key(),
            timeout_seconds=120.0,
        )
    )
    prompt = _build_prompt(user_goal, _load_file_context(files))
    request = AIRequest(
        messages=(AIMessage(role=MessageRole.USER, content=prompt),),
        model=BASETEN_HACKATHON_MODEL,
        max_output_tokens=16384,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        metadata={"purpose": "plan-with-supervisor"},
    )
    response = client.complete(request)
    content = response.message.content or ""
    if response.finish_reason.value != "stop":
        raise RuntimeError(f"Model finished with {response.finish_reason.value}")
    proposal = _parse_json_object(content)
    if not isinstance(proposal, dict):
        raise ValueError("Model response is not a JSON object")
    return proposal


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True, help="Short user goal")
    parser.add_argument(
        "--files",
        default="",
        help="Comma-separated file paths relative to the worktree/cwd",
    )
    args = parser.parse_args(argv)

    files = [p.strip() for p in args.files.split(",") if p.strip()]
    proposal = plan_objective(args.goal, files)
    print(json.dumps(proposal, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
