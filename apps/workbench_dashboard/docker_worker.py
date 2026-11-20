"""EXPERIMENTAL Docker Desktop Linux worker prototype (ADR-095, unwired).

Bounded synthetic containment probe: runs ordinary coding checks plus
negative host-write/descendant/link cases inside a locked-down Linux
container and collects a bounded result. NOT imported by any
production path; the drain keeps host execution until the proving
matrix passes and the owner approves integration.

Prototype contract (from ADR-095): pinned official image, private Git
metadata, non-root user, dropped capabilities, no-new-privileges,
read-only root, no network, bounded CPU/memory/PIDs/time. No Docker
socket, host namespaces, privileged mode, profile, credentials, or
shared Git mounts. Synthetic inputs only; host owns result collection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROTOTYPE_IMAGE = "python:3.14-slim"
PROTOTYPE_USER = "65532:65532"
PROTOTYPE_CPUS = "1.0"
PROTOTYPE_MEMORY = "512m"
PROTOTYPE_PIDS_LIMIT = "64"
PROTOTYPE_TIMEOUT_SECONDS = 300
MAX_RESULT_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    """Immutable launch parameters; the image digest pins at run time."""

    workspace_host_dir: Path
    result_host_dir: Path
    image: str = PROTOTYPE_IMAGE
    image_digest: str | None = None
    cpus: str = PROTOTYPE_CPUS
    memory: str = PROTOTYPE_MEMORY
    pids_limit: str = PROTOTYPE_PIDS_LIMIT
    timeout_seconds: int = PROTOTYPE_TIMEOUT_SECONDS
    extra_args: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.workspace_host_dir.is_absolute() or not self.result_host_dir.is_absolute():
            raise ValueError("Prototype mounts require absolute host paths")
        if self.timeout_seconds <= 0:
            raise ValueError("Prototype timeout must be positive")


GUEST_PROBE = r"""
import json, os, subprocess, sys

findings = {}
ws = "/workspace"

def check(name, fn):
    try:
        findings[name] = {"ok": True, "detail": fn()}
    except Exception as exc:  # noqa: BLE001 - probe records, never raises
        findings[name] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

def positive_python():
    return sys.version.split()[0]

def positive_write():
    path = os.path.join(ws, "probe.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("worker-writes-here")
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == "worker-writes-here"
    return "workspace write/read round-trip"

def positive_git():
    env = {**os.environ, "GIT_AUTHOR_NAME": "probe", "GIT_AUTHOR_EMAIL": "probe@local",
           "GIT_COMMITTER_NAME": "probe", "GIT_COMMITTER_EMAIL": "probe@local",
           "GIT_CONFIG_NOSYSTEM": "1", "HOME": "/tmp"}
    repo = os.path.join(ws, "repo")
    os.makedirs(repo, exist_ok=True)
    subprocess.run(["git", "init", "-q", repo], check=True, env=env, timeout=60)
    subprocess.run(["git", "-C", repo, "checkout", "-qb", "probe"], check=True, env=env, timeout=60)
    with open(os.path.join(repo, "f.txt"), "w", encoding="utf-8") as handle:
        handle.write("v1")
    subprocess.run(["git", "-C", repo, "add", "f.txt"], check=True, env=env, timeout=60)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "v1"], check=True, env=env, timeout=60)
    diff = subprocess.run(["git", "-C", repo, "show", "--stat", "HEAD"], check=True, env=env,
                          capture_output=True, text=True, timeout=60).stdout
    assert os.path.isdir(os.path.join(repo, ".git"))
    assert "f.txt" in diff
    return "private git init/branch/commit/diff"

def negative_root_write():
    try:
        with open("/host-sentinel-probe", "w", encoding="utf-8") as handle:
            handle.write("escape")
    except OSError:
        return "read-only root refused host-style write"
    raise AssertionError("root write unexpectedly succeeded")

def negative_symlink_escape():
    link = os.path.join(ws, "escape-link")
    try:
        os.symlink("/etc/hostname", link)
    except OSError:
        return "symlink creation refused"
    with open(link, encoding="utf-8") as handle:
        content = handle.read()
    assert "worker-writes-here" not in content
    return "symlink stays inside container filesystem"

def negative_descendant():
    proc = subprocess.run([sys.executable, "-c", "open('/host-sentinel-child', 'w')"],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode == 0:
        raise AssertionError("child process escaped read-only root")
    return "child process inherits confinement"

def negative_env():
    # GPG_KEY is baked into official python images: the PUBLIC key fingerprint
    # used to verify the Python tarball at image build time (published on
    # python.org), not a host credential. Only image-inherited allowlisted.
    allowlisted = {"GPG_KEY"}
    leaked = [key for key in os.environ
              if ("KEY" in key.upper() or "TOKEN" in key.upper()) and key not in allowlisted]
    assert not leaked, f"credential-like env leaked: {leaked}"
    return "no credential-like environment"

for name, fn in (("positive_python", positive_python), ("positive_write", positive_write),
                 ("positive_git", positive_git), ("negative_root_write", negative_root_write),
                 ("negative_symlink_escape", negative_symlink_escape),
                 ("negative_descendant", negative_descendant), ("negative_env", negative_env)):
    check(name, fn)

print(json.dumps({"findings": findings}))
"""


def build_worker_command(spec: WorkerSpec, *, guest_script: str = GUEST_PROBE) -> list[str]:
    """Fixed docker run argv for the bounded synthetic worker."""
    image = spec.image if spec.image_digest is None else f"{spec.image}@{spec.image_digest}"
    return [
        "docker",
        "run",
        "--rm",
        "--user",
        PROTOTYPE_USER,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",
        "--network",
        "none",
        "--cpus",
        spec.cpus,
        "--memory",
        spec.memory,
        "--pids-limit",
        spec.pids_limit,
        "-v",
        f"{spec.workspace_host_dir}:/workspace:rw",
        "-v",
        f"{spec.result_host_dir}:/result:rw",
        "--workdir",
        "/workspace",
        *spec.extra_args,
        image,
        "python",
        "-c",
        guest_script,
    ]


def parse_probe_output(stdout: str) -> dict:
    """Parse the guest JSON report; reject oversized or malformed output."""
    raw = stdout.encode("utf-8", "replace")
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError("Guest report exceeds the bounded result size")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Guest report is not JSON: {exc}") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), dict):
        raise ValueError("Guest report lacks a findings object")
    return payload["findings"]
