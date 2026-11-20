"""Relay proof: worker with no network completes a turn via the host mailbox.

Brings up the relay compose project (worker only, network_mode none,
mailbox + relay-module mounts), mediates one synthetic turn from the
host, and asserts the worker-side findings: relay turn answered, no
default route, no DNS, minimal boundary mount, assistant present.
Evidence preserved; never touches the real repo or credentials.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workbench_dashboard"))

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
        "    result = client.complete([{'role': 'user', 'content': 'hi'}], timeout_s=120)",
        "    assert result.get('text') == 'synthetic', result",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    mailbox = evidence / "mailbox"
    mailbox.mkdir()
    run_id = "relay-proof"
    model = "synthetic"
    program = WORKER_PROGRAM.replace("MODEL_PLACEHOLDER", model).replace("RUN_PLACEHOLDER", run_id)
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
    receipt: dict = {"passed": False}
    compose_file = evidence / "docker-compose.yml"
    compose_file.write_text(compose_file_content(spec), encoding="utf-8")
    mediator = HostMediator(
        mailbox,
        RelayGrant(run_id, model),
        lambda m, messages: {"model": m, "text": "synthetic"},
    )
    served: dict = {}

    def mediate() -> None:
        try:
            served["turns"] = 0
            while served["turns"] < 3:
                if not mediator.serve_once(timeout_s=60):
                    break
                served["turns"] += 1
        except Exception as exc:  # noqa: BLE001 - proof capture
            served["error"] = f"{type(exc).__name__}: {exc}"

    host = threading.Thread(target=mediate, daemon=True)
    try:
        up = compose(compose_file, spec.project_name, "up", "--wait", "--wait-timeout", "180")
        receipt["up"] = {
            "exit_code": up.returncode,
            "tail": ((up.stdout or "") + (up.stderr or ""))[-500:],
        }
        host.start()
        host.join(timeout=240)
        receipt["served"] = served
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
            return _write(evidence, receipt, 1)
        findings = receipt["findings"]
        receipt["passed"] = (
            isinstance(findings, dict)
            and all(v is True for v in findings.values())
            and served.get("turns") == 1
        )
        return _write(evidence, receipt, 0 if receipt["passed"] else 1)
    finally:
        down = compose(compose_file, spec.project_name, "down", "--volumes", "--remove-orphans")
        receipt["teardown_exit"] = down.returncode
        try:
            (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        except OSError:
            pass


def _write(evidence: Path, receipt: dict, code: int) -> int:
    print(json.dumps(receipt, indent=1)[:1200])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
