"""Prepare or execute one explicitly reviewed task without repository tools."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from ai_provider import BackendConfig, ProviderError, ProviderKind, create_chat_client
from ai_provider.contracts import FinishReason
from ai_provider.reviewed_input import (
    MAX_REVIEWED_INPUT_BYTES,
    reviewed_input_request,
    reviewed_input_sha256,
)

DEFAULT_MODEL = "google/gemma-4-31b-it:free"


def main(argv: Sequence[str] | None = None) -> int:
    """Default to local preparation; execution requires exact-input owner review."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path, help="UTF-8 task text reviewed in a local editor.")
    parser.add_argument("--execute", action="store_true", help="Send exactly one model request.")
    parser.add_argument("--approved-sha256", help="Digest of the complete text you reviewed.")
    parser.add_argument(
        "--confirm-non-sensitive",
        action="store_true",
        help="Attest no secrets/genuinely private data; approve possible retention/training.",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="Exact named OpenRouter :free model."
    )
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument(
        "--timeout-seconds", type=int, default=60, help="Per HTTP operation, 1..120."
    )
    args = parser.parse_args(argv)
    if not 1 <= args.timeout_seconds <= 120:
        parser.error("--timeout-seconds must be between 1 and 120.")
    if not args.model.endswith(":free") or args.model.startswith("openrouter/"):
        parser.error("An exact named :free model is required; routers and paid models are refused.")
    if not 1 <= args.max_output_tokens <= 8192:
        parser.error("--max-output-tokens must be between 1 and 8192.")
    if args.execute and (not args.confirm_non_sensitive or not args.approved_sha256):
        parser.error("Execution requires --confirm-non-sensitive and --approved-sha256.")
    try:
        with args.input_file.open("rb") as source:
            raw = source.read(MAX_REVIEWED_INPUT_BYTES + 1)
        if len(raw) > MAX_REVIEWED_INPUT_BYTES:
            raise ValueError("Reviewed input exceeds 65536 UTF-8 bytes.")
        text = raw.decode("utf-8")
        # A single in-memory snapshot avoids a second file read after review checks.
        request = reviewed_input_request(
            text,
            approved_sha256=args.approved_sha256 or reviewed_input_sha256(text),
            model=args.model,
            max_output_tokens=args.max_output_tokens,
        )
    except (OSError, ValueError):
        print("reviewed_input: refused; unreadable/invalid input or mismatched review digest")
        return 2
    print(
        json.dumps(
            {
                "mode": "execute" if args.execute else "prepare_only",
                "input_sha256": reviewed_input_sha256(text),
                "input_bytes": len(raw),
                "model": args.model,
                "max_output_tokens": args.max_output_tokens,
                "tools": 0,
                "ambient_context": False,
                "history": False,
                "max_inference_calls": 1,
                "timeout_seconds_per_http_operation": args.timeout_seconds,
            },
            sort_keys=True,
        )
    )
    if not args.execute:
        print("Review the entire file locally. Preparation does not attest review or send data.")
        return 0
    try:
        client = create_chat_client(
            BackendConfig(
                ProviderKind.OPENROUTER,
                args.model,
                timeout_seconds=args.timeout_seconds,
                require_free_model=True,
            )
        )
        response = client.complete(request)
    except ProviderError as exc:
        print(f"reviewed_input: provider refused/failed ({exc.category.value}); no retry")
        return 1
    complete = response.finish_reason is FinishReason.STOP and not response.tool_calls
    print("## **SUMMARY**")
    print("- Changed: received a restricted response; no workspace operation was executed.")
    print("- Validated: exact-input review and provider admission checks; no task tests executed.")
    print("- Notes: model output is unverified; no tools, continuation, retry or fallback.")
    print("\nAgent response (unverified):\n" + response.message.content)
    if not complete:
        print("\nreviewed_input: incomplete response; no tool execution or continuation attempted")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
