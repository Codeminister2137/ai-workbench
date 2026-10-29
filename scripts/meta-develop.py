"""Bound one public-repository Meta coding task using the existing Workbench CLI.

Run with the project's configured Python environment. No daemon, installation,
fallback or unattended multi-task scheduler. Artifacts are per-task evidence.
"""

from __future__ import annotations

import argparse
import contextlib
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


class AllowanceExhausted(ValueError):
    """Expected stop of the shared foreground allowance."""


@contextlib.contextmanager
def hands_off_file_policy(enabled: bool):
    """Scope existing permissions to auto file edits and denied shell/custom tools.

    The override exists only in this foreground launcher process. It neither
    supplies human approvals nor changes shared configuration or product policy.
    """
    if not enabled:
        yield
        return
    from dataclasses import replace

    from ai_agent.contracts import PermissionAction
    from ai_agent.permissions import ApprovalPolicyPreset, PermissionPolicy

    descriptor = PermissionPolicy.__dict__["from_approval_preset"]
    original = PermissionPolicy.from_approval_preset

    @classmethod
    def scoped(cls, preset):
        policy = original(preset)
        if ApprovalPolicyPreset(preset) == ApprovalPolicyPreset.WORKSPACE_WRITE:
            return replace(
                policy, shell_action=PermissionAction.DENY, custom_action=PermissionAction.DENY
            )
        return policy

    PermissionPolicy.from_approval_preset = scoped
    try:
        yield
    finally:
        PermissionPolicy.from_approval_preset = descriptor


def reserve(receipt: dict, elapsed: float, size: int) -> dict:
    if len(receipt["requests"]) >= MAX_CALLS or elapsed >= 900:
        raise AllowanceExhausted("Named task request/time allowance exhausted")
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
    parser.add_argument("--task-file", type=Path)
    parser.add_argument("--chat", action="store_true", help="Use existing foreground coding-chat")
    parser.add_argument(
        "--hands-off",
        action="store_true",
        help="Auto scoped file edits; deny shell/custom tools without prompting",
    )
    parser.add_argument("--session-db", type=Path, help="Existing coding-chat transcript database")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--check", action="store_true", help="Validate local setup without inference"
    )
    args = parser.parse_args()
    root = args.repo_root.resolve(strict=True)
    if not args.chat and args.task_file is None:
        parser.error("--task-file is required outside --chat")
    if args.session_db is not None and not args.chat:
        parser.error("--session-db requires --chat")
    task = args.task_file.resolve(strict=True).read_text(encoding="utf-8") if args.task_file else ""
    session_db = (
        args.session_db or Path(__file__).resolve().parents[1] / "data/repo-assistant-chats.sqlite3"
    )
    if args.chat and not session_db.is_file():
        parser.error(
            "--chat requires an existing transcript database; no new storage is provisioned"
        )
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
                    "mode": "coding-chat" if args.chat else "implement",
                    "hands_off_file_edits": args.hands_off,
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
        "max_reserved_usd": str(RESERVE * MAX_CALLS),
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
    policy_scope = contextlib.ExitStack()
    record()
    try:
        policy_scope.enter_context(hands_off_file_policy(args.hands_off))
        if args.chat:
            print(
                f"Meta chat: {MAX_CALLS} total API calls, USD{RESERVE * MAX_CALLS} maximum, "
                "15-minute admission window. /exit ends chat."
            )
        status = cli_main(
            ([task] if task else [])
            + [
                "--repo-root",
                str(root),
                "--provider",
                "meta",
                "--catalog",
                str(catalog),
                "--model",
                "muse-spark-1.3",
                "--mode",
                "coding-chat" if args.chat else "implement",
                "--execute",
                "--native-tools",
                "--shared-tools",
                "coding",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "prepaid_credits_allowed",
                "--approval-policy",
                "interactive" if args.chat and not args.hands_off else "workspace_write",
                "--skip-prompt-review",
                "--max-action-rounds",
                str(MAX_CALLS),
                "--timeout-seconds",
                "90",
                "--command-timeout-seconds",
                "30",
                "--log-file",
                str(run / "assistant.log"),
            ]
            + (["--coding-session-db", str(session_db.resolve())] if args.chat else [])
        )
        receipt.update(status="cli_finished", exit_code=status)
        return status
    except AllowanceExhausted:
        receipt.update(status="allowance_exhausted", exit_code=2)
        print(
            "Meta session allowance exhausted; stopped before another request. "
            "Effects and receipts retained."
        )
        return 2
    except BaseException as error:
        receipt.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        policy_scope.close()
        openai_responses.urlopen = original
        receipt["elapsed_seconds"] = time.monotonic() - started
        record()


if __name__ == "__main__":
    raise SystemExit(main())
