"""Run a fresh, bounded Baseten synthetic acceptance against the event alias.

This script makes at most four non-sensitive chat-completion calls through the
Baseten event adapter, records the result, and verifies that the declared source
tree is unchanged. It stops on the first failure and never retries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from ai_provider.adapters.baseten import baseten_hackathon_config
from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass
from ai_provider.factory import create_chat_client

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "scripts/baseten-synthetic-acceptance.py",
    "packages/ai_provider/src/ai_provider/adapters/baseten.py",
    "packages/ai_provider/src/ai_provider/adapters/openai_compatible.py",
    "packages/ai_provider/src/ai_provider/factory.py",
    "packages/ai_provider/src/ai_provider/contracts.py",
)
PROMPTS = (
    (
        "system",
        "You are a helpful assistant. Keep answers short and omit private info.",
    ),
    (
        "user",
        "Say 'Baseten event alias is reachable' and nothing else.",
    ),
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_sources(root: Path) -> dict[str, str]:
    return {name: _sha256_file(root / name) for name in SOURCES}


def _excerpt(text: str, limit: int = 200) -> str:
    if len(text) <= limit * 2:
        return text
    return text[:limit] + "\n...\n" + text[-limit:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, default=4)
    args = parser.parse_args(argv)

    output: Path = args.output_dir.resolve()
    artifacts_root = (ROOT / "artifacts").resolve()
    if not output.is_relative_to(artifacts_root):
        parser.error(f"Output must be under {artifacts_root}")
    output.mkdir(parents=True, exist_ok=False)

    before_hashes = _snapshot_sources(ROOT)
    receipt: dict = {
        "mode": "baseten_synthetic_acceptance",
        "started_at": datetime.now(UTC).isoformat(),
        "max_calls": args.max_calls,
        "status": "running",
        "calls": [],
        "source_hashes_before": before_hashes,
        "source_hashes_after": {},
        "protected_sources_unchanged": None,
    }

    client = None
    try:
        config = baseten_hackathon_config(timeout_seconds=30.0)
        client = create_chat_client(config)
    except Exception as exc:  # pragma: no cover - acceptance harness
        receipt["status"] = "failed"
        receipt["failure"] = {
            "phase": "client_creation",
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        _write_receipt(output, receipt)
        return 1

    messages = tuple(
        AIMessage(role=MessageRole(role), content=content) for role, content in PROMPTS
    )

    for call_number in range(1, args.max_calls + 1):
        request = AIRequest(
            messages=messages,
            max_output_tokens=128,
            privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
            metadata={"call_number": call_number, "acceptance": "baseten-synthetic"},
        )
        request_bytes = json.dumps(_request_to_dict(request), sort_keys=True).encode()
        request_hash = hashlib.sha256(request_bytes).hexdigest()
        call_record: dict = {
            "call_number": call_number,
            "request_hash": request_hash,
            "started_at": datetime.now(UTC).isoformat(),
            "state": "started",
        }
        receipt["calls"].append(call_record)

        started = time.perf_counter()
        try:
            response = client.complete(request)
            latency_ms = (time.perf_counter() - started) * 1000
            response_text = response.message.content or ""
            response_bytes = json.dumps(
                {
                    "content": response_text,
                    "finish_reason": response.finish_reason.value,
                    "usage": asdict(response.usage) if response.usage else None,
                },
                sort_keys=True,
            ).encode()
            call_record.update(
                {
                    "state": "response_received",
                    "response_hash": hashlib.sha256(response_bytes).hexdigest(),
                    "finish_reason": response.finish_reason.value,
                    "usage": asdict(response.usage) if response.usage else None,
                    "latency_ms": round(latency_ms, 3),
                    "content_excerpt": _excerpt(response_text),
                }
            )
        except Exception as exc:  # pragma: no cover - acceptance harness
            latency_ms = (time.perf_counter() - started) * 1000
            call_record.update(
                {
                    "state": "error",
                    "latency_ms": round(latency_ms, 3),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            receipt["status"] = "failed"
            receipt["failure"] = {
                "phase": f"call_{call_number}",
                "type": type(exc).__name__,
                "message": str(exc),
            }
            _write_receipt(output, receipt)
            return 1

    receipt["status"] = "passed"
    after_hashes = _snapshot_sources(ROOT)
    receipt["source_hashes_after"] = after_hashes
    receipt["protected_sources_unchanged"] = before_hashes == after_hashes
    _write_receipt(output, receipt)

    print(f"Baseten synthetic acceptance passed: {args.max_calls} calls")
    print(f"Receipt: {output / 'receipt.json'}")
    if not receipt["protected_sources_unchanged"]:
        print("WARNING: declared source files changed during the run", file=sys.stderr)
        return 2
    return 0


def _request_to_dict(request: AIRequest) -> dict:
    """Serialize a request for hashing; omit mutable metadata ordering issues."""
    return {
        "messages": [
            {"role": msg.role.value, "content": msg.content, "name": msg.name}
            for msg in request.messages
        ],
        "model": request.model,
        "temperature": request.temperature,
        "max_output_tokens": request.max_output_tokens,
        "privacy_class": request.privacy_class.value,
        "tools": [tool.name for tool in request.tools],
        "metadata": dict(sorted(request.metadata.items())),
        "top_p": request.top_p,
    }


def _write_receipt(output: Path, receipt: dict) -> None:
    receipt["finished_at"] = datetime.now(UTC).isoformat()
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
