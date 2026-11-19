"""Docker worker prototype: fixed argv, validation, bounded parsing (mocked daemon)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docker_worker import (  # noqa: E402
    GUEST_PROBE,
    PROTOTYPE_IMAGE,
    WorkerSpec,
    build_worker_command,
    parse_probe_output,
)


@pytest.fixture
def spec(tmp_path: Path) -> WorkerSpec:
    workspace = tmp_path / "ws"
    result = tmp_path / "res"
    workspace.mkdir()
    result.mkdir()
    return WorkerSpec(workspace_host_dir=workspace.resolve(), result_host_dir=result.resolve())


def test_worker_argv_locks_every_boundary(spec: WorkerSpec) -> None:
    command = build_worker_command(spec)
    joined = " ".join(command)
    for required in (
        "--rm",
        "--user",
        "65532:65532",
        "--cap-drop",
        "ALL",
        "no-new-privileges",
        "--read-only",
        "--network",
        "none",
        "--cpus",
        "--memory",
        "--pids-limit",
        "--workdir",
        "/workspace",
    ):
        assert required in command, required
    assert "--privileged" not in command
    assert not any("docker.sock" in part for part in command)
    assert not any("profile" in part.lower() for part in command)
    mounts = [command[index + 1] for index, part in enumerate(command) if part == "-v"]
    assert len(mounts) == 2
    assert mounts[0] == f"{spec.workspace_host_dir}:/workspace:rw"
    assert mounts[1] == f"{spec.result_host_dir}:/result:rw"
    assert joined.count("python:3.14-slim") == 1


def test_worker_pins_digest_when_known(spec: WorkerSpec, tmp_path: Path) -> None:
    pinned = WorkerSpec(
        workspace_host_dir=spec.workspace_host_dir,
        result_host_dir=spec.result_host_dir,
        image_digest="sha256:abc123",
    )
    command = build_worker_command(pinned)
    assert f"{PROTOTYPE_IMAGE}@sha256:abc123" in command


def test_worker_rejects_relative_mounts_and_bad_timeouts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        WorkerSpec(
            workspace_host_dir=Path("relative/ws"),
            result_host_dir=(tmp_path / "res").resolve(),
        )
    with pytest.raises(ValueError, match="positive"):
        WorkerSpec(
            workspace_host_dir=(tmp_path / "ws").resolve(),
            result_host_dir=(tmp_path / "res").resolve(),
            timeout_seconds=0,
        )


def test_guest_probe_covers_matrix_and_parses() -> None:
    compile(GUEST_PROBE, "<guest-probe>", "exec")
    for name in (
        "positive_python",
        "positive_write",
        "positive_git",
        "negative_root_write",
        "negative_symlink_escape",
        "negative_descendant",
        "negative_env",
    ):
        assert name in GUEST_PROBE


def test_parse_probe_output_bounds_and_validates() -> None:
    good = '{"findings": {"positive_python": {"ok": true, "detail": "3.14"}}}'
    assert parse_probe_output(good)["positive_python"]["ok"] is True
    with pytest.raises(ValueError, match="not JSON"):
        parse_probe_output("not json")
    with pytest.raises(ValueError, match="findings object"):
        parse_probe_output('{"nope": 1}')
    with pytest.raises(ValueError, match="bounded result size"):
        parse_probe_output('{"findings": {}}' + " " * 70000)
