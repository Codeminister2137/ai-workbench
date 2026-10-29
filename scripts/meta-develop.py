"""Bound one public-repository Meta coding task using the existing Workbench CLI.

Run with the project's configured Python environment. No daemon, installation,
fallback or unattended multi-task scheduler. Artifacts are per-task evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_BYTES = 131072
MAX_OUTPUT = 8192
MAX_CALLS = 8
RESERVE = (
    Decimal(MAX_BYTES + 4096) * Decimal("1.25") + Decimal(MAX_OUTPUT) * Decimal("4.25")
) / Decimal(1000000)


def reserve(receipt: dict, elapsed: float, size: int) -> dict:
    if len(receipt["requests"]) >= MAX_CALLS or elapsed >= 900:
        raise ValueError("Named task request/time allowance exhausted")
    call = {
        "index": len(receipt["requests"]) + 1,
        "request_bytes": size,
        "reserved_usd": str(RESERVE),
        "status": "reserved_before_send",
    }
    receipt["requests"].append(call)
    return call


def meta_catalog(source: Path) -> str:
    import tomllib

    entries = [
        "[[models]]" + block for block in source.read_text(encoding="utf-8").split("[[models]]")[1:]
    ]
    matches = [
        block
        for block in entries
        if tomllib.loads(block)["models"][0].get("route_id") == "meta/muse-spark-1.3"
    ]
    if len(matches) != 1:
        raise ValueError("Expected one configured Spark route")
    return matches[0]


def admit(payload: dict, url: str, method: str) -> bytes:
    if url != "https://api.meta.ai/v1/responses" or method != "POST":
        raise ValueError("Only direct Meta Responses is admitted")
    if payload.get("model") != "muse-spark-1.3" or payload.get("stream"):
        raise ValueError("Only non-streaming Spark Standard is admitted")
    if payload.get("previous_response_id"):
        raise ValueError("Server-managed prior context is excluded")
    if any(tool.get("type") != "function" for tool in payload.get("tools", [])):
        raise ValueError("Hosted or non-function tools are excluded")
    pending = [payload.get("input")]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if item.get("type") in {"input_image", "input_file", "input_audio"}:
                raise ValueError("This task admits text input only")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    payload["store"] = False
    payload["max_output_tokens"] = min(payload.get("max_output_tokens", MAX_OUTPUT), MAX_OUTPUT)
    if type(payload["max_output_tokens"]) is not int or payload["max_output_tokens"] < 16:
        raise ValueError("Invalid output bound")
    # A declared first-task setting; do not trim instructions/history to fit.
    payload["reasoning"] = {"effort": "low"}
    raw = json.dumps(payload).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError("Complete request exceeds 128KiB; reduce task scope, not required context")
    return raw


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--task-file", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--check", action="store_true", help="Validate local setup without inference"
    )
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    task = args.task_file.resolve(strict=True).read_text(encoding="utf-8")
    if not (root / ".git").exists() or not (root / "AGENTS.md").is_file():
        parser.error("Expected an explicit repository with AGENTS.md")
    if args.check:
        print(
            json.dumps(
                {
                    "repository": str(root),
                    "task_bytes": len(task.encode()),
                    "max_calls": MAX_CALLS,
                    "max_reserved_usd": str(RESERVE * MAX_CALLS),
                    "inference_calls": 0,
                }
            )
        )
        return 0
    run = args.run_dir.resolve()
    run.mkdir(parents=True, exist_ok=False)
    catalog = run / "meta-catalog.toml"
    catalog.write_text(
        meta_catalog(
            Path(__file__).resolve().parents[1]
            / "packages/ai_orchestrator/examples/model_catalog.toml"
        ),
        encoding="utf-8",
    )
    # Load exactly one credential, not the Workbench .env as process configuration.
    key = os.environ.get("META_API_KEY")
    if not key:
        env_file = Path(__file__).resolve().parents[1] / ".env"
        values = [
            line.partition("=")[2].strip().strip("\"'")
            for line in env_file.read_text(encoding="utf-8-sig").splitlines()
            if line.partition("=")[0].strip() == "META_API_KEY"
        ]
        if len(values) != 1 or not values[0]:
            raise ValueError("One META_API_KEY is required")
        key = values[0]
    os.environ["META_API_KEY"] = key
    from ai_agent.cli import main as cli_main
    from ai_provider.adapters import openai_responses

    receipt = {
        "max_requests": MAX_CALLS,
        "max_reserved_usd": "2.00",
        "requests": [],
        "status": "running",
    }
    receipt_path = run / "receipt.json"
    started = time.monotonic()

    def record():
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    class Response:
        def __init__(self, response, call):
            self.response, self.call = response, call

        def __enter__(self):
            self.response.__enter__()
            return self

        def __exit__(self, *exc):
            return self.response.__exit__(*exc)

        def read(self):
            raw = self.response.read(1048577)
            if len(raw) > 1048576:
                raise ValueError("Response byte bound exceeded; reservation retained")
            data = json.loads(raw)
            self.call.update(
                status="received", usage=data.get("usage"), response_status=data.get("status")
            )
            record()
            return raw

    def transport(request, *, timeout):
        raw = admit(json.loads(request.data), request.full_url, request.get_method())
        call = reserve(receipt, time.monotonic() - started, len(raw))
        record()
        bounded = Request(
            request.full_url, data=raw, headers=dict(request.header_items()), method="POST"
        )
        return Response(
            build_opener(NoRedirect(), ProxyHandler({})).open(bounded, timeout=min(timeout, 90)),
            call,
        )

    original = openai_responses.urlopen
    openai_responses.urlopen = transport
    record()
    try:
        status = cli_main(
            [
                task,
                "--repo-root",
                str(root),
                "--provider",
                "meta",
                "--catalog",
                str(catalog),
                "--model",
                "muse-spark-1.3",
                "--mode",
                "implement",
                "--execute",
                "--native-tools",
                "--shared-tools",
                "coding",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "prepaid_credits_allowed",
                "--approval-policy",
                "workspace_write",
                "--skip-prompt-review",
                "--max-action-rounds",
                "8",
                "--timeout-seconds",
                "90",
                "--command-timeout-seconds",
                "30",
                "--log-file",
                str(run / "assistant.log"),
            ]
        )
        receipt.update(status="cli_finished", exit_code=status)
        return status
    except BaseException as error:
        receipt.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        openai_responses.urlopen = original
        receipt["elapsed_seconds"] = time.monotonic() - started
        record()


if __name__ == "__main__":
    raise SystemExit(main())
