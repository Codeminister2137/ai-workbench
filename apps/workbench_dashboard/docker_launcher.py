"""Docker launcher for isolated drain runs (OS-isolation phase 1, unwired).

Runs an opaque guest command inside the locked-down container profile
proven by the ADR-095 probe: pinned digest, numeric non-root user,
cap-drop ALL, no-new-privileges, read-only root with tmpfs, no network,
bounded CPU/memory/PIDs/time. The host prepares a private workspace
copy; the worker never sees shared refs. Failures return evidence,
never raise, and never fall back to unsandboxed execution.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

PROBE_IMAGE_DIGEST = (
    "ai-workbench/docker-probe"
    "@sha256:099d274cc88dddd3c289aae5cf6681c9bccca6a53ed258f087c04e854298d66b"
)
CONTAINER_USER = "65532:65532"
WORKSPACE_MOUNT = "/workspace"
DEFAULT_CPUS = "2.0"
DEFAULT_MEMORY = "1g"
DEFAULT_PIDS_LIMIT = "128"
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_WORKSPACE_CAP_BYTES = 256 * 1024 * 1024
DEFAULT_RESULT_CAP_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class DockerRunSpec:
    """One locked-down container invocation."""

    run_id: str
    argv: tuple[str, ...]
    workspace_src: Path
    image: str = PROBE_IMAGE_DIGEST
    cpus: str = DEFAULT_CPUS
    memory: str = DEFAULT_MEMORY
    pids_limit: str = DEFAULT_PIDS_LIMIT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    workspace_cap_bytes: int = DEFAULT_WORKSPACE_CAP_BYTES
    storage_root: Path = field(default_factory=lambda: Path(".tmp/docker-runs"))


@dataclass(frozen=True, slots=True)
class DockerResult:
    """Bounded outcome of one container invocation (never raises)."""

    run_id: str
    ok: bool
    exit_code: int | None
    elapsed_seconds: float
    result: dict | None
    error: str


def _workspace_size_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        total += path.stat().st_size
    return total


def prepare_workspace(spec: DockerRunSpec) -> Path:
    """Copy the pinned source tree into per-run container storage.

    Refuses symlinks escaping the source and trees over the byte cap.
    Raises RuntimeError with evidence (the caller converts to a failed
    result); the destination is removed on any failure.
    """
    src = spec.workspace_src.resolve()
    dest = (spec.storage_root / spec.run_id / "workspace").resolve()
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    try:
        for path in src.rglob("*"):
            if path.is_symlink() and path.resolve() != path and src not in path.resolve().parents:
                raise RuntimeError(f"workspace symlink escapes source: {path}")
        if _workspace_size_bytes(src) > spec.workspace_cap_bytes:
            raise RuntimeError(f"workspace over {spec.workspace_cap_bytes} byte cap: {src}")
        shutil.copytree(src, dest, symlinks=False)
    except Exception:
        shutil.rmtree(dest.parent, ignore_errors=True)
        raise
    return dest


def build_docker_argv(spec: DockerRunSpec, workspace: Path, result_dir: Path) -> list[str]:
    """Locked-down `docker run` argv; command words are never shelled.

    Mirrors the proven ADR-095 probe profile flag for flag (plus
    `--pull never`, proven by the compose transport probe): pinned
    digest, non-root user, dropped caps, no-new-privileges, read-only
    root, tmpfs scratch, no network, bounded resources. Known gap
    shared with the probe: a timed-out run orphans its container
    (client kill does not stop it); a named-container cleanup pass
    is follow-up work, not part of this slice.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--user",
        CONTAINER_USER,
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
        f"{workspace}:/workspace:rw",
        "-v",
        f"{result_dir}:/result:rw",
        "--workdir",
        WORKSPACE_MOUNT,
        spec.image,
        *spec.argv,
    ]


def launch(spec: DockerRunSpec) -> DockerResult:
    """Prepare, run, collect, clean up. Never raises, never unsandboxed."""
    started = time.monotonic()
    storage = (spec.storage_root / spec.run_id).resolve()

    def fail(error: str, exit_code: int | None = None) -> DockerResult:
        shutil.rmtree(storage, ignore_errors=True)
        return DockerResult(
            run_id=spec.run_id,
            ok=False,
            exit_code=exit_code,
            elapsed_seconds=round(time.monotonic() - started, 1),
            result=None,
            error=error[:1000],
        )

    try:
        workspace = prepare_workspace(spec)
        result_dir = storage / "result"
        result_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return fail(f"workspace prep failed: {type(exc).__name__}: {exc}")
    try:
        proc = subprocess.run(
            build_docker_argv(spec, workspace, result_dir),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
        )
    except FileNotFoundError:
        return fail("docker executable not found; refusing unsandboxed run")
    except subprocess.TimeoutExpired:
        return fail(f"container exceeded {spec.timeout_seconds}s; killed, no result kept")
    except OSError as exc:
        return fail(f"container launch failed: {exc}")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        return fail(f"guest exited {proc.returncode}: {tail}", exit_code=proc.returncode)
    result_file = result_dir / "result.json"
    try:
        raw = result_file.read_bytes()
    except OSError:
        return fail("guest wrote no result.json", exit_code=proc.returncode)
    if len(raw) > DEFAULT_RESULT_CAP_BYTES:
        return fail("guest result over size cap", exit_code=proc.returncode)
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        return fail("guest result is not valid JSON", exit_code=proc.returncode)
    if not isinstance(result, dict):
        return fail("guest result must be a JSON object", exit_code=proc.returncode)
    elapsed = round(time.monotonic() - started, 1)
    shutil.rmtree(storage, ignore_errors=True)
    return DockerResult(
        run_id=spec.run_id,
        ok=True,
        exit_code=proc.returncode,
        elapsed_seconds=elapsed,
        result=result,
        error="",
    )
