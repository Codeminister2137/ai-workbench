"""Run the bounded Docker worker containment probe (ADR-095, experimental).

Requires a running Docker Desktop engine; refuses to run without one
(no unsandboxed fallback). Prepares a synthetic workspace, executes
the locked-down worker, pins the image digest, validates the bounded
result, and writes an independent host audit. Never touches the real
repo, credentials, or shared Git metadata.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "workbench_dashboard"))

from docker_worker import (  # noqa: E402
    PROTOTYPE_IMAGE,
    WorkerSpec,
    build_worker_command,
    parse_probe_output,
)


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def _require_engine() -> None:
    probe = _docker("version", "--format", "{{json .Server}}")
    if probe.returncode != 0 or not probe.stdout.strip() or probe.stdout.strip() == "null":
        raise SystemExit("Docker engine unavailable; refusing unsandboxed fallback")


def _pin_digest(image: str) -> str:
    inspect = _docker("image", "inspect", image, "--format", "{{json .RepoDigests}}")
    if inspect.returncode != 0:
        raise SystemExit(f"cannot inspect image {image}: {inspect.stderr.strip()[:200]}")
    try:
        digests = json.loads(inspect.stdout or "[]")
    except json.JSONDecodeError:
        raise SystemExit(f"cannot parse digests for image {image}") from None
    if not digests:
        raise SystemExit(f"image {image} has no recorded digest; refusing unpinned run")
    return str(digests[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=PROTOTYPE_IMAGE)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    _require_engine()
    digest = _pin_digest(args.image)
    print(f"pinned image: {digest}")

    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="docker-worker-") as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        result = root / "result"
        workspace.mkdir()
        result.mkdir()
        (workspace / "task.txt").write_text("synthetic task input\n", encoding="utf-8")
        spec = WorkerSpec(
            workspace_host_dir=workspace.resolve(),
            result_host_dir=result.resolve(),
            image=args.image,
            image_digest=digest.split("@", 1)[1] if "@" in digest else None,
        )
        command = build_worker_command(spec)
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=spec.timeout_seconds
            )
        except subprocess.TimeoutExpired:
            print("worker timed out; container removed by --rm")
            return 2
        findings = parse_probe_output(completed.stdout)
        (evidence / "guest-findings.json").write_text(
            json.dumps(findings, indent=1, sort_keys=True), encoding="utf-8"
        )
        audit = {
            "image": args.image,
            "image_digest": digest,
            "exit_code": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "stderr_tail": completed.stderr[-2000:],
            "passed": completed.returncode == 0
            and all(item.get("ok") is True for item in findings.values()),
        }
        (evidence / "host-audit.json").write_text(
            json.dumps(audit, indent=1, sort_keys=True), encoding="utf-8"
        )
        print(json.dumps(audit, indent=1))
        return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
