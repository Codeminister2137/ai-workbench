"""Deterministic coverage for the bounded acceptance controller.

The controller is the offline preparation and judging half of a bounded live
CLI acceptance run. These tests never send a network request and never invoke a
model: they check that preparation writes a coherent directory, that the
coherence gate refuses a mis-prepared or already-passing fixture, that the
launch gate refuses without an explicit owner grant or bounds, and that the
validation gate judges a synthetic successful run correctly.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/bounded-acceptance-controller.py"

BROKEN_SOURCE = "def add(a, b):\n    return a - b\n"
FIXED_SOURCE = "def add(a, b):\n    return a + b\n"
TEST_SOURCE = "from math_ops import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"


def controller():
    spec = importlib.util.spec_from_file_location("bounded_acceptance_controller", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare(module, fixture: Path, controller_dir: Path, *extra: str) -> int:
    argv = [
        "prepare",
        "--route-id",
        "kimi-k2.7-code",
        "--fixture-dir",
        str(fixture),
        "--controller-dir",
        str(controller_dir),
        "--editable",
        "math_ops.py",
        "--frozen",
        "test_math_ops.py",
        *extra,
    ]
    old = sys.argv
    sys.argv = ["controller", *argv]
    try:
        return module.main()
    finally:
        sys.argv = old


def _fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "math_ops.py").write_text(BROKEN_SOURCE, encoding="utf-8")
    (fixture / "test_math_ops.py").write_text(TEST_SOURCE, encoding="utf-8")
    return fixture


def test_prepare_writes_a_complete_controller_directory(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"

    assert _prepare(module, fixture, controller_dir) == 0

    for name in ("run.json", "checksums.json", "task.md", "coherence.py", "validate.py"):
        assert (controller_dir / name).exists(), name

    run = json.loads((controller_dir / "run.json").read_text(encoding="utf-8"))
    assert run["route_id"] == "kimi-k2.7-code"
    assert run["editable_files"] == ["math_ops.py"]
    assert run["frozen_files"] == ["math_ops.py", "test_math_ops.py"]
    assert run["validation_command"]

    task = (controller_dir / "task.md").read_text(encoding="utf-8")
    assert "kimi-k2.7-code" in task
    assert "math_ops.py" in task


def test_coherence_gate_passes_on_a_well_prepared_fixture(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    run = subprocess.run(
        [sys.executable, str(controller_dir / "coherence.py")],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_coherence_gate_refuses_when_frozen_input_changed(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    (fixture / "test_math_ops.py").write_text(
        "def test_add():\n    assert True\n", encoding="utf-8"
    )

    run = subprocess.run(
        [sys.executable, str(controller_dir / "coherence.py")],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "coherence_failure:" in run.stdout


def test_coherence_gate_refuses_when_fixture_tests_already_pass(tmp_path):
    """A seeded defect must fail before launch, or the run proves nothing."""
    module = controller()
    fixture = _fixture(tmp_path)
    (fixture / "math_ops.py").write_text(FIXED_SOURCE, encoding="utf-8")
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    run = subprocess.run(
        [sys.executable, str(controller_dir / "coherence.py")],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "already pass" in run.stdout


def test_prepare_refuses_when_fixture_directory_is_missing(tmp_path, capsys):
    module = controller()
    assert _prepare(module, tmp_path / "absent", tmp_path / "controller") == 1
    assert "fixture directory" in capsys.readouterr().out


def test_prepare_refuses_to_overwrite_an_existing_controller(tmp_path, capsys):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    assert _prepare(module, fixture, controller_dir) == 1
    assert "not empty" in capsys.readouterr().out


def test_launch_refuses_without_grant_or_bounds(tmp_path, capsys):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    sys.argv = ["controller", "launch", "--controller-dir", str(controller_dir)]
    try:
        assert module.main() == 1
    finally:
        sys.argv = ["pytest"]
    assert "requires an explicit --grant or --bounds" in capsys.readouterr().out


def test_launch_with_grant_runs_coherence_and_reports_ready(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    sys.argv = [
        "controller",
        "launch",
        "--controller-dir",
        str(controller_dir),
        "--grant",
        "opencode-go-baseline-20261022",
    ]
    try:
        assert module.main() == 0
    finally:
        sys.argv = ["pytest"]


def test_launch_with_bounds_refuses_when_coherence_fails(tmp_path, capsys):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0
    (fixture / "test_math_ops.py").write_text("def test_x():\n    pass\n", encoding="utf-8")

    sys.argv = [
        "controller",
        "launch",
        "--controller-dir",
        str(controller_dir),
        "--bounds",
        "2cli/1200sec",
    ]
    try:
        assert module.main() == 1
    finally:
        sys.argv = ["pytest"]
    assert "coherence gate did not pass" in capsys.readouterr().out


def test_validate_gate_passes_on_a_synthetic_successful_run(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    (fixture / "math_ops.py").write_text(FIXED_SOURCE, encoding="utf-8")
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    run = subprocess.run(
        [sys.executable, str(controller_dir / "validate.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_validate_gate_fails_when_no_editable_file_changed(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    run = subprocess.run(
        [sys.executable, str(controller_dir / "validate.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "no editable file changed" in run.stdout


def test_validate_gate_fails_when_a_frozen_test_was_modified(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    (fixture / "math_ops.py").write_text(FIXED_SOURCE, encoding="utf-8")
    (fixture / "test_math_ops.py").write_text(
        "from math_ops import add\n\n\ndef test_add():\n    assert add(0, 0) == 0\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    run = subprocess.run(
        [sys.executable, str(controller_dir / "validate.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "frozen file test_math_ops.py was modified" in run.stdout


def test_validate_gate_fails_when_an_unexpected_file_appears(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert _prepare(module, fixture, controller_dir) == 0

    (fixture / "math_ops.py").write_text(FIXED_SOURCE, encoding="utf-8")
    (fixture / "sneaky.py").write_text("import os\n", encoding="utf-8")
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    run = subprocess.run(
        [sys.executable, str(controller_dir / "validate.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1
    assert "unexpected new files" in run.stdout


def test_validate_gate_allows_declared_new_paths_and_cache_directories(tmp_path):
    module = controller()
    fixture = _fixture(tmp_path)
    controller_dir = tmp_path / "controller"
    assert (
        _prepare(
            module,
            fixture,
            controller_dir,
            "--allowed-new-path",
            "report.md",
        )
        == 0
    )

    (fixture / "math_ops.py").write_text(FIXED_SOURCE, encoding="utf-8")
    (fixture / "report.md").write_text("## Done\n", encoding="utf-8")
    (fixture / "__pycache__").mkdir()
    (fixture / "__pycache__" / "math_ops.cpython-314.pyc").write_bytes(b"\x00")
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()

    run = subprocess.run(
        [sys.executable, str(controller_dir / "validate.py"), "--run-dir", str(run_dir)],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
