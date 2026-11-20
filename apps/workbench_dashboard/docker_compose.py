"""Compose project builders: isolated proxy runs and host-relay runs.

Secret hygiene: per-run bearer tokens render into the generated compose
file, which lives under ignored per-run storage with a bounded TTL.
That is acceptable for synthetic proof tokens; production credentials
need tighter handling (purpose-scoped values, strict file modes) as
part of the production-callback follow-up.

One internal bridge network carries exactly one conversation: the worker
may reach the proxy's inference endpoint and nothing else (no host
loopback, no gateway, no DNS egress, no default route). Both services
use the locked-down profile: pinned digests, non-root user, dropped
caps, read-only roots, bounded resources. The proxy serves a caller
supplied completion callback; production wiring passes a scoped model
client, probes pass a synthetic one. No credentials live in this
module; callers inject them as single-purpose environment.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

PROBE_IMAGE_DIGEST = (
    "ai-workbench/docker-probe"
    "@sha256:099d274cc88dddd3c289aae5cf6681c9bccca6a53ed258f087c04e854298d66b"
)
WORKER_IMAGE = "ai-workbench/mai-worker:20261120"
PROXY_PORT = 8080


@dataclass(frozen=True, slots=True)
class ComposeSpec:
    """One per-run isolated compose project."""

    run_id: str
    project_name: str
    proxy_token: str
    worker_image: str = WORKER_IMAGE
    proxy_image: str = PROBE_IMAGE_DIGEST
    proxy_module_host_path: Path | None = None
    workspace_host_path: Path | None = None
    result_host_path: Path | None = None
    network_name: str = "inference"
    proxy_model: str = "synthetic"
    proxy_ttl_seconds: float = 300.0
    worker_command: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class RelaySpec:
    """One per-run host-relay project (answer R: no worker network at all).

    The worker's network is ``none``: it cannot reach host listeners,
    the public internet, or DNS because it has no interface beyond
    loopback. Inference flows only through the run mailbox that the
    host mediates (see relay_mailbox.py).
    """

    run_id: str
    project_name: str
    worker_image: str = WORKER_IMAGE
    mailbox_host_path: Path | None = None
    relay_module_host_path: Path | None = None
    worker_command: tuple[str, ...] | None = None


def _locked_down(image: str, *, cpus: float, mem_limit: str, pids: int) -> dict:
    return {
        "image": image,
        "pull_policy": "never",
        "user": "65532:65532",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "tmpfs": ["/tmp:rw,nosuid,nodev,size=16m"],
        "cpus": cpus,
        "mem_limit": mem_limit,
        "pids_limit": pids,
        "networks": ["inference"],
    }


def build_project(spec: ComposeSpec) -> dict:
    """Render the compose document for one isolated run."""
    if spec.proxy_module_host_path is None:
        raise ValueError("proxy module host path is required (read-only mount)")
    if len(spec.proxy_token) < 32:
        raise ValueError("proxy bearer token must be at least 32 characters")
    proxy_command = "\n".join(
        [
            "import os, socket, sys",
            "sys.path.insert(0, '/boundary')",
            "from inference_proxy import RunGrant, make_server",
            "grant = RunGrant(os.environ['PROXY_RUN_ID'], os.environ['PROXY_TOKEN'],",
            "                 os.environ.get('PROXY_MODEL', 'synthetic'),",
            "                 ttl=float(os.environ.get('PROXY_TTL', '300')))",
            # Synthetic completion: transport proof only. A production
            # callback (scoped model client) is follow-up work and must
            # enforce provider/privacy/usage admission per the proxy docs.
            "server = make_server((socket.gethostbyname(socket.gethostname()), 8080),",
            "                 grant,",
            "                 lambda model, messages: {'model': model, 'text': 'synthetic'})",
            "server.serve_forever()",
        ]
    )
    proxy = _locked_down(spec.proxy_image, cpus=1.0, mem_limit="128m", pids=32)
    proxy["command"] = ["python", "-B", "-u", "-c", proxy_command]
    proxy["environment"] = {
        "PROXY_RUN_ID": spec.run_id,
        "PROXY_TOKEN": spec.proxy_token,
        "PROXY_MODEL": spec.proxy_model,
        "PROXY_TTL": str(spec.proxy_ttl_seconds),
    }
    proxy["volumes"] = [f"{spec.proxy_module_host_path}:/boundary/inference_proxy.py:ro"]
    worker = _locked_down(spec.worker_image, cpus=2.0, mem_limit="1g", pids=128)
    worker["working_dir"] = "/workspace"
    if spec.worker_command is not None:
        worker["command"] = list(spec.worker_command)
    volumes = []
    if spec.workspace_host_path is not None:
        volumes.append(f"{spec.workspace_host_path}:/workspace:rw")
    if spec.result_host_path is not None:
        volumes.append(f"{spec.result_host_path}:/result:rw")
    if volumes:
        worker["volumes"] = volumes
    return {
        "services": {"proxy": proxy, "worker": worker},
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


def build_relay_project(spec: RelaySpec) -> dict:
    """Render the relay document: worker only, no network, mailbox mount."""
    if spec.mailbox_host_path is None:
        raise ValueError("mailbox host path is required (read-write mount)")
    if spec.relay_module_host_path is None:
        raise ValueError("relay module host path is required (read-only mount)")
    worker = _locked_down(spec.worker_image, cpus=2.0, mem_limit="1g", pids=128)
    worker.pop("networks")
    worker["network_mode"] = "none"
    worker["working_dir"] = "/workspace"
    worker["volumes"] = [
        f"{spec.mailbox_host_path}:/mailbox:rw",
        f"{spec.relay_module_host_path}:/boundary/relay_mailbox.py:ro",
    ]
    if spec.worker_command is not None:
        worker["command"] = list(spec.worker_command)
    return {"services": {"worker": worker}}


def compose_file_content(spec: ComposeSpec | RelaySpec) -> str:
    """Render the project as a compose YAML document (no yaml dependency)."""
    doc = build_relay_project(spec) if isinstance(spec, RelaySpec) else build_project(spec)
    lines = ["# Generated by docker_compose.py; do not hand-edit.", ""]
    lines.append("services:")
    for name, service in doc["services"].items():
        lines.append(f"  {name}:")
        lines.extend(_yaml_block(service, 4))
    if "networks" in doc:
        lines.append("networks:")
        lines.append("  inference:")
        lines.append("    internal: true")
        lines.append("    driver: bridge")
        lines.append("    driver_opts:")
        lines.append("      com.docker.network.bridge.gateway_mode_ipv4: isolated")
        lines.append("      com.docker.network.bridge.gateway_mode_ipv6: isolated")
    lines.append("")
    return "\n".join(lines)


def _yaml_block(value: object, indent: int) -> list[str]:
    pad = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_block(item, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_yaml_block(item, indent + 2))
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return lines
    return [f"{pad}{_yaml_scalar(value)}"]


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # Double-quoted YAML folds raw newlines into spaces, which would
    # destroy embedded programs; emit \-escapes the parser restores.
    text = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{text}"'


def compose(
    project_file: Path, project_name: str, *args: str, timeout_seconds: float = 300.0
) -> subprocess.CompletedProcess[str]:
    """Run one `docker compose` command against a project file."""
    return subprocess.run(
        [
            "docker",
            "compose",
            "--file",
            str(project_file),
            "--project-name",
            project_name,
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
