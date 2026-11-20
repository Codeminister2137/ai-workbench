"""Phase-3 proof: Mai worker image on the isolated proxy bridge (manual).

Brings up the compose project from docker_compose.py (Mai worker image +
synthetic proxy), runs worker-side checks (proxy reachable with a valid
grant, refused without; host/gateway/DNS unreachable; no default route;
ai-assistant present), then tears the project down. Evidence preserved;
never touches the real repo, credentials, or shared Git metadata.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "workbench_dashboard"))

from docker_compose import (  # noqa: E402
    ComposeSpec,
    build_project,
    compose,
    compose_file_content,
)

WORKER_CHECKS = "\n".join(
    [
        "import json, socket, subprocess, urllib.request, urllib.error",
        "findings = {}",
        "TOKEN = 'TOKEN_PLACEHOLDER'",
        "RUN = 'RUN_PLACEHOLDER'",
        "def check(name, fn):",
        "    try:",
        "        fn()",
        "        findings[name] = True",
        "    except Exception as exc:",
        "        findings[name] = type(exc).__name__ + ': ' + str(exc)[:200]",
        "def call(token):",
        "    body = json.dumps({'messages': [{'role': 'user', 'content': 'hi'}]}).encode()",
        "    req = urllib.request.Request('http://proxy:8080/runs/' + RUN + '/inference',",
        "                             data=body, method='POST',",
        "                             headers={'Authorization': 'Bearer ' + token,",
        "                                      'Content-Type': 'application/json'})",
        "    with urllib.request.urlopen(req, timeout=10) as resp:",
        "        return resp.status, json.loads(resp.read().decode())",
        "import time",
        "def positive():",
        "    deadline = time.monotonic() + 30",
        "    last = None",
        "    while time.monotonic() < deadline:",
        "        try:",
        "            status, payload = call(TOKEN)",
        "        except OSError as exc:",
        "            last = exc",
        "            time.sleep(1)",
        "            continue",
        "        assert status == 200, status",
        "        assert payload.get('text') == 'synthetic', payload",
        "        return",
        "    raise AssertionError(f'proxy never came up: {last!r}')",
        "check('proxy_reachable', positive)",
        "def refused():",
        "    try:",
        "        call('wrong-token-0000000000000000000000')",
        "    except urllib.error.HTTPError as err:",
        "        assert err.code == 401, err.code",
        "        return",
        "    raise AssertionError('bad token accepted')",
        "check('bad_token_refused', refused)",
        "def denied(host):",
        "    try:",
        "        sock = socket.create_connection((host, 80), timeout=3)",
        "    except OSError:",
        "        return",
        "    sock.close()",
        "    raise AssertionError('reachable: ' + host)",
        "check('host_gateway', lambda: denied('172.18.0.1'))",
        "check('host_loopback', lambda: denied('127.0.0.1'))",
        "def no_dns():",
        "    try:",
        "        socket.gethostbyname('proxy.invalid-test-xyz')",
        "    except OSError:",
        "        return",
        "    raise AssertionError('unexpected DNS answer')",
        "check('no_dns', no_dns)",
        "def no_default_route():",
        "    rows = open('/proc/net/route').read().splitlines()[1:]",
        "    assert not any(row.split()[1] == '00000000' for row in rows)",
        "check('no_default_route', no_default_route)",
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
    token = secrets.token_hex(20)
    run_id = "compose-proof"
    worker_checks = WORKER_CHECKS.replace("TOKEN_PLACEHOLDER", token).replace(
        "RUN_PLACEHOLDER", run_id
    )
    spec = ComposeSpec(
        run_id=run_id,
        project_name="worker-proof-" + secrets.token_hex(6),
        proxy_token=token,
        proxy_module_host_path=REPO_ROOT / "apps/workbench_dashboard/inference_proxy.py",
        worker_command=("python", "-B", "-u", "-c", worker_checks),
    )
    (evidence / "compose.json").write_text(
        json.dumps(build_project(spec), indent=2), encoding="utf-8"
    )
    receipt: dict = {"passed": False}
    compose_file = evidence / "docker-compose.yml"
    compose_file.write_text(compose_file_content(spec), encoding="utf-8")
    try:
        up = compose(compose_file, spec.project_name, "up", "--wait", "--wait-timeout", "180")
        receipt["up"] = {
            "exit_code": up.returncode,
            "tail": ((up.stdout or "") + (up.stderr or ""))[-500:],
        }
        time.sleep(2)
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
        receipt["passed"] = isinstance(findings, dict) and all(v is True for v in findings.values())
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
