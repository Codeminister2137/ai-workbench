"""Small, one-attempt capability probes; never execute generated tools.

Run explicitly selected catalog routes with ``python -m ai_provider.capability_eval``.
Only synthetic inputs leave the process. Native schema probing currently covers
Ollama, OpenAI-compatible Chat Completions and the native Codex output-schema
protocol; other adapters report unknown rather than equating prompted JSON with
schema-constrained output. Native Codex
uses one bounded invocation with fresh allowance pre/postflight readings.
This is capability smoke evidence, not quality scoring.
"""

from __future__ import annotations

import argparse
import json
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.adapters.ollama import OllamaChatClient
from ai_provider.adapters.openai_compatible import OpenAICompatibleChatClient
from ai_provider.adapters.opencode_go import OpenCodeGoChatClient
from ai_provider.adapters.openrouter import OpenRouterFreeChatClient
from ai_provider.config import BackendConfig, ProviderKind
from ai_provider.contracts import (
    AIMessage,
    AIRequest,
    AIStreamDelta,
    AIStreamFinal,
    AIToolDefinition,
    AIToolParameter,
    ChatClient,
    MessageRole,
    PrivacyClass,
)
from ai_provider.errors import ProviderError
from ai_provider.factory import create_chat_client
from ai_provider.secrets import load_dotenv

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "integer", "enum": [7]}},
    "required": ["answer"],
    "additionalProperties": False,
}


class SchemaProbeOllamaClient(OllamaChatClient):
    """Eval-only wire extension; does not change the production request contract."""

    def _chat_payload(self, request: AIRequest, *, stream: bool) -> dict:
        payload = super()._chat_payload(request, stream=stream)
        if request.metadata.get("capability_schema_probe"):
            payload["format"] = SCHEMA
        return payload


class SchemaProbeOpenAIClient(OpenAICompatibleChatClient):
    """Eval-only strict JSON schema extension for Chat Completions."""

    def _chat_payload(self, request: AIRequest, *, stream: bool) -> dict:
        payload = super()._chat_payload(request, stream=stream)
        if request.metadata.get("capability_schema_probe"):
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "capability_probe", "strict": True, "schema": SCHEMA},
            }
        return payload


class SchemaProbeOpenCodeClient(SchemaProbeOpenAIClient, OpenCodeGoChatClient):
    """Keep OpenCode session and protocol behavior for schema probes."""


class SchemaProbeOpenRouterClient(SchemaProbeOpenAIClient, OpenRouterFreeChatClient):
    """Keep OpenRouter's free-only and privacy admission for schema probes."""


def create_probe_client(config: BackendConfig) -> ChatClient:
    """Select eval extensions only for supported factory-selected protocols."""
    client = create_chat_client(config)
    extensions = {
        OllamaChatClient: SchemaProbeOllamaClient,
        OpenAICompatibleChatClient: SchemaProbeOpenAIClient,
        OpenCodeGoChatClient: SchemaProbeOpenCodeClient,
        OpenRouterFreeChatClient: SchemaProbeOpenRouterClient,
    }
    extension = extensions.get(type(client))
    return extension(config) if extension is not None else client


@dataclass(frozen=True)
class Verdict:
    route_id: str
    capability: str
    status: str
    checked_utc: str
    elapsed_seconds: float
    detail: str


def probe(client: ChatClient, route_id: str, capability: str) -> Verdict:
    """Probe one capability without retry; transport errors never mean unsupported."""
    start = time.monotonic()
    checked = datetime.now(UTC).isoformat()
    status, detail = "unknown", "native schema request unavailable in this adapter"
    request = AIRequest(
        messages=(AIMessage(MessageRole.USER, 'Return exactly {"answer":7}.'),),
        max_output_tokens=1024,
        temperature=0,
        privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
        metadata={
            "ollama_context_length": 4096,
            "capability_schema_probe": capability == "structured_output",
            # All probe prompts are fixed synthetic constants carrying no
            # user data, so provider retention risk is nil. Adapters with
            # retention-gated free tiers (OpenRouter) honor this flag.
            "public_or_synthetic": True,
        },
    )
    try:
        if capability == "streaming":
            deltas, finals = [], []
            events = client.stream(request)
            try:
                for event in events:
                    if isinstance(event, AIStreamDelta) and event.content:
                        deltas.append(event.content)
                    elif isinstance(event, AIStreamFinal):
                        finals.append(event.response)
            finally:
                close = getattr(events, "close", None)
                if close is not None:
                    close()
            passed = (
                bool(deltas) and len(finals) == 1 and "".join(deltas) == finals[0].message.content
            )
            status = "pass" if passed else "fail"
            detail = f"text deltas={len(deltas)}, final events={len(finals)}; text must match final"
        elif capability == "tools":
            from dataclasses import replace

            request = replace(
                request,
                messages=(
                    AIMessage(
                        MessageRole.USER,
                        "Call record_answer with answer=7. Do not answer in prose.",
                    ),
                ),
                tools=(
                    AIToolDefinition(
                        "record_answer",
                        "Record an integer answer",
                        (AIToolParameter("answer", "integer", "The answer"),),
                    ),
                ),
            )
            response = client.complete(request)
            calls = response.tool_calls or response.message.tool_calls
            passed = (
                len(calls) == 1
                and calls[0].name == "record_answer"
                and calls[0].arguments == {"answer": 7}
                and type(calls[0].arguments.get("answer")) is int
            )
            status = "pass" if passed else "fail"
            detail = "one exact named call and integer argument required; no tool executed"
        elif capability == "structured_output" and isinstance(
            client, (SchemaProbeOllamaClient, SchemaProbeOpenAIClient)
        ):
            response = client.complete(request)
            try:
                value = json.loads(response.message.content)
            except ValueError:
                value = None
            passed = (
                isinstance(value, dict)
                and value == {"answer": 7}
                and type(value.get("answer")) is int
            )
            status = "pass" if passed else "fail"
            protocol = (
                "Ollama native format schema"
                if isinstance(client, SchemaProbeOllamaClient)
                else "OpenAI-compatible response_format JSON schema"
            )
            detail = f"{protocol}; exact object with integer answer required"
        elif capability != "structured_output":
            raise ValueError(f"Unknown capability: {capability}")
    except ProviderError as exc:
        # Avoid raw provider bodies, prompts, URLs and credentials in evidence.
        detail = f"provider error category={exc.category.value}; support undetermined"
    return Verdict(
        route_id, capability, status, checked, round(time.monotonic() - start, 3), detail
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--route", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-root", type=Path)
    parser.add_argument(
        "--allow-hosted",
        action="store_true",
        help="Requires a current owner allowance; never inferred from credentials",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; preserve consumed runs")
    catalog = tomllib.loads(args.catalog.read_text(encoding="utf-8"))["models"]
    selected = []
    for route_id in dict.fromkeys(args.route):
        rows = [row for row in catalog if row["route_id"] == route_id]
        if len(rows) != 1:
            parser.error(f"route must resolve exactly once: {route_id}")
        row = rows[0]
        if row["provider"] != "ollama" and not args.allow_hosted:
            parser.error("hosted routes require an explicit current allowance and --allow-hosted")
        if row["access_method"] == "codex_cli":
            if (
                row["provider"] != "openai"
                or row.get("billing_source") != "chatgpt_subscription_allowance"
                or not args.allow_hosted
            ):
                parser.error("Codex eval requires the explicit subscription allowance route")
        elif row["access_method"] not in {"local_runtime", "provider_api"}:
            parser.error("native subscription clients require their own capability protocol")
        selected.append(row)
    if any(row["access_method"] == "codex_cli" for row in selected) and len(selected) != 1:
        parser.error("native allowance evaluation requires exactly one explicit route per run")
    load_dotenv(args.env_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as sink:
        for row in selected:
            if row["access_method"] == "codex_cli":
                from ai_provider.native_capability_eval import probe_codex

                result = probe_codex(row["route_id"], row["model"], args.output)
                sink.write(json.dumps(asdict(result)) + "\n")
                sink.flush()
                if result.status != "pass":
                    raise SystemExit(1)
                continue
            config = BackendConfig(
                provider=ProviderKind(row["provider"]),
                model=row["model"],
                base_url=row.get("base_url"),
                timeout_seconds=90,
                require_free_model=row.get("cost_policy_tier") == "free_only",
            )
            client = create_probe_client(config)
            for capability in ("tools", "streaming", "structured_output"):
                result = probe(client, row["route_id"], capability)
                sink.write(json.dumps(asdict(result)) + "\n")
                sink.flush()
                print(
                    f"{result.route_id} {capability}: {result.status} ({result.elapsed_seconds}s)",
                    flush=True,
                )


if __name__ == "__main__":
    main()
