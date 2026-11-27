"""Docker launcher: locked-down profile, safe prep, failed-not-raised."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from docker_launcher import (
    DockerResult,
    DockerRunSpec,
    build_docker_argv,
    launch,
    prepare_workspace,
)


@pytest.fixture
def src(tmp_path):
    root = tmp_path / "src"
    (root / "sub").mkdir(parents=True)
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "sub" / "data.txt").write_text("x" * 100, encoding="utf-8")
    return root


@pytest.fixture
def spec(src, tmp_path):
    return DockerRunSpec(
        run_id="r1",
        argv=("python", "-c", "print(1)"),
        workspace_src=src,
        storage_root=tmp_path / "runs",
    )


def test_argv_matches_locked_down_profile(spec, tmp_path) -> None:
    argv = build_docker_argv(spec, tmp_path / "ws", tmp_path / "res")
    assert argv[:4] == ["docker", "run", "--rm", "--pull"]
    assert "--image" not in argv
    joined = " ".join(argv)
    for flag in (
        "--user",
        "65532:65532",
        "--cap-drop",
        "ALL",
        "no-new-privileges",
        "--read-only",
        "/tmp:rw,nosuid,nodev,size=64m",
        "--network",
        "none",
        "--cpus",
        "--memory",
        "--pids-limit",
        "never",
    ):
        assert flag in argv, flag
    assert "sha256:099d274c" in joined
    image_at = argv.index(spec.image)
    assert argv[image_at + 1 :] == ["python", "-c", "print(1)"]
    assert f"{tmp_path / 'ws'}:/workspace:rw" in argv
    assert f"{tmp_path / 'res'}:/result:rw" in argv


def test_argv_never_shells_command_words(spec, tmp_path) -> None:
    evil = DockerRunSpec(
        run_id="r2",
        argv=("sh", "-c", "x; rm -rf /"),
        workspace_src=spec.workspace_src,
        storage_root=spec.storage_root,
    )
    argv = build_docker_argv(evil, tmp_path / "ws", tmp_path / "res")
    assert "x; rm -rf /" in argv  # one opaque word, not shell-split


def test_prepare_copies_tree(spec, src) -> None:
    dest = prepare_workspace(spec)
    assert (dest / "main.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert (dest / "sub" / "data.txt").stat().st_size == 100
    assert dest.parent.name == "r1"


def test_prepare_refuses_escaping_symlink(spec, src, tmp_path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("s3cret", encoding="utf-8")
    try:
        (src / "leak").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks require privileges on this host")
    with pytest.raises(RuntimeError, match="escapes source"):
        prepare_workspace(spec)
    assert not (spec.storage_root / "r1").exists()


def test_prepare_refuses_over_cap(spec, src) -> None:
    tiny = DockerRunSpec(
        run_id="r3",
        argv=(),
        workspace_src=src,
        workspace_cap_bytes=10,
        storage_root=spec.storage_root,
    )
    with pytest.raises(RuntimeError, match="over .* byte cap"):
        prepare_workspace(tiny)
    assert not (spec.storage_root / "r3").exists()


def _completed(result_path: Path, payload: dict | None = None) -> object:
    class Done:
        returncode = 0
        stdout = ""
        stderr = ""

    if payload is not None:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(payload), encoding="utf-8")
    return Done()


def test_launch_happy_path_cleans_storage(spec, monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        assert argv[0] == "docker"
        result_file = spec.storage_root / "r1" / "result" / "result.json"
        return _completed(result_file, {"findings": {"a": True}})

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = launch(spec)
    assert isinstance(out, DockerResult)
    assert out.ok is True
    assert out.result == {"findings": {"a": True}}
    assert out.exit_code == 0
    assert not (spec.storage_root / "r1").exists()


def test_launch_engine_down_returns_failed_result(spec, monkeypatch) -> None:
    def missing(argv, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", missing)
    out = launch(spec)
    assert out.ok is False
    assert "unsandboxed" in out.error
    assert not (spec.storage_root / "r1").exists()


def test_launch_timeout_and_bad_results_are_failed_not_raised(spec, monkeypatch) -> None:
    def timeout(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=1)

    monkeypatch.setattr(subprocess, "run", timeout)
    out = launch(spec)
    assert out.ok is False and "exceeded" in out.error

    class Bad:
        returncode = 3
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Bad())
    out = launch(spec)
    assert out.ok is False and out.exit_code == 3 and "boom" in out.error

    class NoResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: NoResult())
    out = launch(spec)
    assert out.ok is False and "no result.json" in out.error
