"""Relay proof: worker with no network completes a turn via the host mailbox.

Brings up the relay compose project (worker only, network_mode none,
mailbox + relay-module mounts), mediates one synthetic turn from the
host, and asserts the worker-side findings: relay turn answered, no
default route, no DNS, minimal boundary mount, assistant present.
Evidence preserved; hosted credentials stay on the host.
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workbench_dashboard"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai_provider" / "src"))

from docker_compose import RelaySpec, compose, compose_file_content  # noqa: E402
from relay_mailbox import HostMediator, RelayGrant  # noqa: E402

WORKER_PROGRAM = "\n".join(
    [
        "import json, os, socket, subprocess, sys",
        "sys.path.insert(0, '/boundary')",
        "from relay_mailbox import RelayGrant, WorkerClient",
        "findings = {}",
        "MODEL = 'MODEL_PLACEHOLDER'",
        "RUN = 'RUN_PLACEHOLDER'",
        "def check(name, fn):",
        "    try:",
        "        fn()",
        "        findings[name] = True",
        "    except Exception as exc:",
        "        findings[name] = type(exc).__name__ + ': ' + str(exc)[:200]",
        "def relay_turn():",
        "    client = WorkerClient('/mailbox', RelayGrant(RUN, MODEL))",
        "    result = client.complete([{'role': 'user', 'content': 'PROMPT_PLACEHOLDER'}], timeout_s=300)",
        "    assert 'EXPECT_PLACEHOLDER' in (result.get('text') or ''), result",
        "check('relay_turn', relay_turn)",
        "def no_default_route():",
        "    rows = open('/proc/net/route').read().splitlines()[1:]",
        "    assert not any(row.split()[1] == '00000000' for row in rows)",
        "check('no_default_route', no_default_route)",
        "def no_dns():",
        "    try:",
        "        socket.gethostbyname('proxy.invalid-test-xyz')",
        "    except OSError:",
        "        return",
        "    raise AssertionError('unexpected DNS answer')",
        "check('no_dns', no_dns)",
        "def boundary_minimal():",
        "    names = sorted(os.listdir('/boundary'))",
        "    assert names == ['relay_mailbox.py'], names",
        "check('boundary_minimal', boundary_minimal)",
        "def mailbox_clean():",
        "    leftovers = [p for p in os.listdir('/mailbox') if not p.endswith('.tmp')]",
        "    assert leftovers == [], leftovers",
        "check('mailbox_clean', mailbox_clean)",
        "def assistant_present():",
        "    proc = subprocess.run(['ai-assistant', '--help'], capture_output=True,",
        "                          text=True, timeout=30)",
        "    assert proc.returncode == 0, proc.returncode",
        "    assert 'usage:' in (proc.stdout or '').lower()",
        "check('assistant_present', assistant_present)",
        "print(json.dumps(findings))",
    ]
)


def _ollama_callback(model: str):
    """Real local callback: host reaches Ollama; the worker never can."""

    from ai_provider.config import BackendConfig, ProviderKind
    from ai_provider.contracts import AIMessage, AIRequest, MessageRole
    from ai_provider.factory import create_chat_client

    client = create_chat_client(BackendConfig(ProviderKind.OLLAMA, model, None, None, 300.0))

    def complete(granted: str, messages: list[dict[str, str]]) -> dict:
        request = AIRequest(
            messages=tuple(AIMessage(MessageRole(m["role"]), m["content"]) for m in messages),
            temperature=0.0,
            # Thinking models spend tokens before answering; 64 truncated
            # qwen3 to an empty reply in the first live attempt.
            max_output_tokens=512,
        )
        response = client.complete(request)
        return {"model": granted, "text": response.message.content}

    return complete


HOSTED_ROUTE = "requesty/free-nvidia/nemotron-3.5-lightning-30b-a3b"
HOSTED_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


def _hosted_callback(observations: dict):
    """One synthetic Requesty turn, live zero-price admission, no fallback."""
    from ai_provider.config import BackendConfig, ProviderKind
    from ai_provider.contracts import AIMessage, AIRequest, MessageRole, PrivacyClass
    from ai_provider.factory import create_chat_client
    from ai_provider.secrets import load_dotenv
    from proxy_model_callback import ScopedGrant, make_scoped_callback

    load_dotenv(REPO_ROOT)
    client = create_chat_client(
        BackendConfig(
            ProviderKind.REQUESTY,
            HOSTED_MODEL,
            timeout_seconds=120,
            require_free_model=True,
        )
    )
    observations.update(
        route=HOSTED_ROUTE,
        cost_policy="free_only",
        attempts=0,
        max_calls=1,
        token_budget=1024,
        max_output_tokens=512,
        call_timeout_s=120,
        started_utc=datetime.now(UTC).isoformat(),
    )

    def complete(model, messages, timeout_s):
        # Consume before dispatch, including failures: never replay a failed call.
        if observations["attempts"]:
            raise RuntimeError("single hosted attempt already consumed")
        observations["attempts"] += 1
        started = time.monotonic()
        try:
            response = client.complete(
                AIRequest(
                    messages=tuple(
                        AIMessage(MessageRole(m["role"]), m["content"]) for m in messages
                    ),
                    temperature=0.0,
                    max_output_tokens=512,
                    privacy_class=PrivacyClass.PUBLIC_OR_LOW_RISK,
                    metadata={"public_or_synthetic": True},
                )
            )
            observations.update(
                usage=asdict(response.usage),
                response_text=response.message.content,
                finish_reason=str(response.finish_reason),
            )
            return {
                "model": model,
                "text": response.message.content,
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            }
        except Exception as exc:
            observations["error_type"] = type(exc).__name__
            raise
        finally:
            observations["elapsed_s"] = time.monotonic() - started

    return make_scoped_callback(
        grant=ScopedGrant(HOSTED_ROUTE, max_calls=1, token_budget=1024, call_timeout_s=120),
        complete=complete,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--live-ollama", action="store_true")
    modes.add_argument("--live-hosted", action="store_true")
    parser.add_argument("--live-model", default="qwen3:14b")
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    mailbox = evidence / "mailbox"
    mailbox.mkdir()
    run_id = "relay-proof"
    live = bool(args.live_ollama or args.live_hosted)
    model = HOSTED_ROUTE if args.live_hosted else (args.live_model if live else "synthetic")
    prompt = "Say the word relay-ok and nothing else." if live else "hi"
    expect = "relay-ok" if live else "synthetic"
    program = (
        WORKER_PROGRAM.replace("MODEL_PLACEHOLDER", model)
        .replace("RUN_PLACEHOLDER", run_id)
        .replace("PROMPT_PLACEHOLDER", prompt)
        .replace("EXPECT_PLACEHOLDER", expect)
    )
    spec = RelaySpec(
        run_id=run_id,
        project_name="relay-proof-" + secrets.token_hex(6),
        mailbox_host_path=mailbox,
        relay_module_host_path=REPO_ROOT / "apps/workbench_dashboard/relay_mailbox.py",
        worker_command=("python", "-B", "-u", "-c", program),
    )
    (evidence / "relay.json").write_text(
        json.dumps(
            {
                "services": list(
                    __import__("docker_compose").build_relay_project(spec)["services"]
                ),
                "network_mode": "none",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    receipt: dict = {"passed": False, "live": live, "hosted": {}}
    compose_file = evidence / "docker-compose.yml"
    compose_file.write_text(compose_file_content(spec), encoding="utf-8")
    callback = (
        _hosted_callback(receipt["hosted"])
        if args.live_hosted
        else (
            _ollama_callback(model)
            if live
            else (lambda m, messages: {"model": m, "text": "synthetic"})
        )
    )
    mediator = HostMediator(mailbox, RelayGrant(run_id, model), callback)
    served: dict = {}

    def mediate() -> None:
        try:
            served["turns"] = 0
            while served["turns"] < 1:
                if not mediator.serve_once(timeout_s=60):
                    break
                served["turns"] += 1
        except Exception as exc:  # noqa: BLE001 - proof capture
            served["error"] = f"{type(exc).__name__}: {exc}"

    host = threading.Thread(target=mediate, daemon=True)

    def run_transport() -> int:
        up = compose(compose_file, spec.project_name, "up", "--wait", "--wait-timeout", "180")
        receipt["up"] = {
            "exit_code": up.returncode,
            "tail": ((up.stdout or "") + (up.stderr or ""))[-500:],
        }
        if up.returncode != 0:
            return 1
        host.start()
        host.join(timeout=240)
        receipt["served"] = served
        # The response precedes the worker checks; wait for worker exit before logs.
        waited = compose(compose_file, spec.project_name, "wait", "worker", timeout_seconds=60)
        receipt["worker_wait_exit"] = waited.returncode
        logs = compose(compose_file, spec.project_name, "logs", "--no-color", "worker")
        receipt["worker_logs_tail"] = (logs.stdout or "")[-2000:]
        try:
            lines = []
            for raw in (logs.stdout or "").splitlines():
                text = raw.split("|", 1)[1] if "|" in raw else raw
                if text.strip().startswith("{"):
                    lines.append(text.strip())
            receipt["findings"] = json.loads(lines[-1])
        except (IndexError, ValueError) as exc:
            receipt["findings_error"] = f"{type(exc).__name__}: {exc}"
            return 1
        findings = receipt["findings"]
        receipt["passed"] = (
            isinstance(findings, dict)
            and all(v is True for v in findings.values())
            and served.get("turns") == 1
        )
        return 0 if receipt["passed"] else 1

    try:
        code = run_transport()
    finally:
        down = compose(compose_file, spec.project_name, "down", "--volumes", "--remove-orphans")
        receipt["teardown_exit"] = down.returncode
        receipt["teardown_listing"] = _teardown_listing(spec.project_name)
        receipt["cleanup_verified"] = (
            down.returncode == 0 and receipt["teardown_listing"]["empty_verified"]
        )
        receipt["passed"] = receipt["passed"] and receipt["cleanup_verified"]
        try:
            (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        except OSError:
            pass
    return _write(evidence, receipt, code if receipt["cleanup_verified"] else 1)


def _teardown_listing(project_name: str) -> dict:
    """Independently list remaining project containers, including stopped ones."""
    command = [
        "docker",
        "ps",
        "--all",
        "--filter",
        f"label=com.docker.compose.project={project_name}",
        "--format",
        "{{.ID}} {{.Names}} {{.Status}}",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    return {
        "command": command,
        "observed_at": datetime.now(UTC).isoformat(),
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "empty_verified": result.returncode == 0 and not result.stdout.strip(),
    }


def _write(evidence: Path, receipt: dict, code: int) -> int:
    print(json.dumps(receipt, indent=1)[:1200])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
