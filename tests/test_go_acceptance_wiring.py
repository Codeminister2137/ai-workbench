"""Go harness wiring: controller prepare + gates around the seeded fixture (offline)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/opencode-go-acceptance.py"
SPEC = importlib.util.spec_from_file_location("opencode_go_acceptance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def test_prepare_coherence_validate_round_trip(tmp_path) -> None:
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    controller = tmp_path / "controller"

    harness.write_go_fixture(fixture)
    assert harness.prepare_controller(repo, fixture, controller) == 0
    assert (controller / "coherence.py").exists()
    assert (controller / "validate.py").exists()
    assert harness.run_gate(controller / "coherence.py", []).returncode == 0

    # Pre-fix: tests fail, editable unchanged -> validation gate refuses.
    refused = harness.run_gate(controller / "validate.py", ["--run-dir", str(fixture)])
    assert refused.returncode != 0

    # Simulated agent edit: fix the bug, keep tests frozen.
    (fixture / "math_ops.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    passed = harness.run_gate(controller / "validate.py", ["--run-dir", str(fixture)])
    assert passed.returncode == 0, passed.stdout


def test_coherence_refuses_already_fixed_fixture(tmp_path) -> None:
    repo = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    controller = tmp_path / "controller"

    harness.write_go_fixture(fixture)
    (fixture / "math_ops.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    assert harness.prepare_controller(repo, fixture, controller) == 0
    refused = harness.run_gate(controller / "coherence.py", [])
    assert refused.returncode != 0
    assert "already pass" in refused.stdout
