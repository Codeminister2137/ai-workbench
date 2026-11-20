"""Synthetic Compose transport proof. No model/provider calls or production wiring.

Uses only an existing pinned local image. Always tears down its unique project;
keeps exact Compose input, network inspection, guest findings and cleanup evidence.
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

IMAGE = "ai-workbench/docker-probe@sha256:099d274cc88dddd3c289aae5cf6681c9bccca6a53ed258f087c04e854298d66b"
ROOT = Path(__file__).resolve().parent.parent

PROXY = """
import socket, sys
sys.path.insert(0, '/boundary')
from inference_proxy import RunGrant, make_server
grant = RunGrant('synthetic', 'synthetic-capability-for-transport-proof', 'synthetic')
server = make_server((socket.gethostbyname(socket.gethostname()), 8080), grant,
                     lambda model, messages: {'model': model, 'text': 'synthetic completion'})
server.serve_forever()
"""

WORKER = r"""
import http.client, json, socket, time
findings = {}
def check(name, fn):
    try:
        fn()
        findings[name] = True
    except Exception as exc:
        findings[name] = type(exc).__name__ + ': ' + str(exc)[:200]
def request(path='/runs/synthetic/inference', token='synthetic-capability-for-transport-proof',
            body=None, method='POST'):
    conn = http.client.HTTPConnection('proxy', 8080, timeout=3)
    conn.request(method, path, json.dumps(body if body is not None else
                 {'messages': [{'role': 'user', 'content': 'synthetic'}]}),
                 {'Authorization': 'Bearer ' + token})
    response = conn.getresponse()
    status, data = response.status, response.read()
    conn.close()
    return status, data
def status(expected, **kwargs):
    actual, _ = request(**kwargs)
    assert actual == expected, (actual, expected)
def positive():
    for attempt in range(20):
        try:
            code, body = request()
            assert code == 200 and json.loads(body)['text'] == 'synthetic completion'
            return
        except OSError:
            time.sleep(.2)
    raise AssertionError('proxy unavailable')
def denied(host, port):
    try:
        conn = socket.create_connection((host, port), timeout=1)
    except OSError:
        return
    conn.close()
    raise AssertionError('unexpected connection to ' + host)
def dns_denied():
    try:
        socket.getaddrinfo('example.com', 443)
    except OSError:
        return
    raise AssertionError('external DNS resolution succeeded')
check('inference_http', positive)
check('missing_or_wrong_token', lambda: status(401, token='wrong'))
check('foreign_run', lambda: status(404, path='/runs/foreign/inference'))
check('dashboard_endpoint', lambda: status(404, path='/api/inbox'))
check('absolute_url', lambda: status(404, path='http://host.docker.internal:8080/api/inbox'))
check('connect_tunnel', lambda: status(501, method='CONNECT', path='host.docker.internal:443'))
check('worker_upstream_selection', lambda: status(400, body={'url':'http://host.docker.internal'}))
check('oversized_body', lambda: status(413, body={'messages':[{'role':'user','content':'x'*70000}]}))
check('public_ip', lambda: denied('1.1.1.1', 443))
check('host_dashboard', lambda: denied('host.docker.internal', 8000))
check('host_gateway', lambda: denied('gateway.docker.internal', 80))
check('host_loopback', lambda: denied('127.0.0.1', 8000))
check('external_dns', dns_denied)
check('host_sentinel', lambda: denied('host.docker.internal', HOST_SENTINEL_PORT))
def no_default_route():
    with open('/proc/net/route') as handle:
        assert not any(row.split()[1] == '00000000' for row in list(handle)[1:])
check('no_default_route', no_default_route)
print(json.dumps(findings))
raise SystemExit(0 if all(v is True for v in findings.values()) else 1)
"""


def compose_spec(host_sentinel_port: int) -> dict:
    """Two containers, one private isolated bridge, no published ports."""
    limits = {
        "image": IMAGE,
        "pull_policy": "never",
        "user": "65532:65532",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "tmpfs": ["/tmp:rw,nosuid,nodev,size=16m"],
        "cpus": 1,
        "mem_limit": "128m",
        "pids_limit": 32,
        "networks": ["inference"],
    }
    return {
        "services": {
            "proxy": {
                **limits,
                "command": ["python", "-B", "-u", "-c", PROXY],
                "volumes": [
                    f"{ROOT / 'apps/workbench_dashboard/inference_proxy.py'}:/boundary/inference_proxy.py:ro"
                ],
            },
            "worker": {
                **limits,
                "command": [
                    "python",
                    "-B",
                    "-c",
                    f"HOST_SENTINEL_PORT = {host_sentinel_port}\n" + WORKER,
                ],
            },
        },
        "networks": {
            "inference": {
                "internal": True,
                "driver": "bridge",
                "driver_opts": {
                    "com.docker.network.bridge.gateway_mode_ipv4": "isolated",
                    "com.docker.network.bridge.gateway_mode_ipv6": "isolated",
                },
            }
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    nonce = secrets.token_hex(16)

    class Sentinel(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(nonce.encode())

        def log_message(self, format: str, *args: object) -> None:
            pass

    sentinel = HTTPServer(("127.0.0.1", 0), Sentinel)
    thread = threading.Thread(target=sentinel.serve_forever, daemon=True)
    thread.start()
    config = evidence / "compose.json"
    config.write_text(json.dumps(compose_spec(sentinel.server_port), indent=2), encoding="utf-8")
    project = "proxy-proof-" + secrets.token_hex(6)
    base = ["docker", "compose", "-p", project, "-f", str(config)]
    results = {}

    def run(name: str, command: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        results[name] = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        (evidence / "receipt.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return result

    passed = False
    try:
        control = (
            "import urllib.request; "
            f"r=urllib.request.urlopen('http://host.docker.internal:{sentinel.server_port}', timeout=5); "
            f"assert r.read().decode() == {nonce!r}; print('host sentinel reachable on control bridge')"
        )
        if run(
            "host_positive_control",
            [
                "docker",
                "run",
                "--rm",
                "--pull=never",
                "--network",
                "bridge",
                "--user",
                "65532:65532",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--read-only",
                "--memory",
                "128m",
                "--pids-limit",
                "32",
                "--cpus",
                "1",
                IMAGE,
                "python",
                "-c",
                control,
            ],
        ).returncode:
            return 1
        if run("config", [*base, "config", "--quiet"]).returncode:
            return 1
        if run("start", [*base, "up", "-d", "--no-build", "proxy"]).returncode:
            return 1
        inspected = run("network", ["docker", "network", "inspect", project + "_inference"])
        if inspected.returncode:
            return 1
        network = json.loads(inspected.stdout)[0]
        assert network["Internal"] is True
        assert network["Options"]["com.docker.network.bridge.gateway_mode_ipv4"] == "isolated"
        result = run("worker", [*base, "run", "--rm", "--no-deps", "worker"], timeout=90)
        findings = json.loads(result.stdout)
        passed = (
            result.returncode == 0
            and bool(findings)
            and all(value is True for value in findings.values())
        )
    finally:
        sentinel.shutdown()
        sentinel.server_close()
        thread.join(timeout=2)
        cleanup = run("cleanup", [*base, "down", "--timeout", "5", "--volumes", "--remove-orphans"])
        remaining = run(
            "remaining",
            ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project],
        )
        networks = run(
            "remaining_networks",
            [
                "docker",
                "network",
                "ls",
                "-q",
                "--filter",
                "label=com.docker.compose.project=" + project,
            ],
        )
        passed = (
            passed
            and cleanup.returncode == 0
            and remaining.returncode == 0
            and not remaining.stdout.strip()
            and networks.returncode == 0
            and not networks.stdout.strip()
        )
        results["passed"] = passed
        (evidence / "receipt.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps({"passed": passed, "evidence": str(evidence)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
