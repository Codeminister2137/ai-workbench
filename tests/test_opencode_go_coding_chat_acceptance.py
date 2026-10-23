"""Offline controls for the paid-route two-turn harness; no provider is contacted."""

from __future__ import annotations

import builtins
import importlib.util
import json
import os
import py_compile
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/opencode-go-coding-chat-acceptance.py"


@pytest.fixture
def harness(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("go_chat_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "scripts" / SCRIPT.name))
    monkeypatch.setattr(module, "_ollama_reachable", lambda: True)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--timeout-seconds", "10"])
    return module, tmp_path


def result(root):
    paths = list((root / "artifacts").glob("*/results.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text()), paths[0].parent


def test_exactly_two_requests_resume_one_session_and_run_real_validation(harness, monkeypatch):
    module, root = harness
    requests, invocations = [], []
    original_input, original_stdin = builtins.input, sys.stdin

    def scripted_cli(argv):
        invocations.append(list(argv))
        requests.append(argv[-1])
        assert float(argv[argv.index("--turn-timeout-seconds") + 1]) == 10
        if len(invocations) == 1:
            assert argv[argv.index("--coding-session") + 1] == "new"
            print("coding_session_id: preserved-session")
        else:
            assert argv[argv.index("--coding-session") + 1] == "preserved-session"
            fixture = Path(argv[argv.index("--repo-root") + 1])
            source = fixture / "math_ops.py"
            prior = source.stat()
            # Simulate stale bytecode from an earlier agent-side test. Keep
            # size and timestamp identical so ordinary import would reuse it.
            py_compile.compile(str(source), doraise=True)
            source.write_text("def add(a, b):\n    return a + b\n")
            os.utime(source, ns=(prior.st_atime_ns, prior.st_mtime_ns))
        while (answer := input("automated continuation")) != "/exit":
            requests.append(answer)
        return 0

    monkeypatch.setattr(module.cli, "main", scripted_cli)
    assert module.main() == 0
    assert requests == [module.TURN_ONE, module.TURN_TWO]
    assert len(invocations) == 2
    assert builtins.input is original_input and sys.stdin is original_stdin
    receipt, directory = result(root)
    assert receipt["passed"] and receipt["session_id"] == "preserved-session"
    assert receipt["first_turn_source_unchanged"] and receipt["first_turn_tests_unchanged"]
    assert receipt["validation_exit_code"] == 0
    assert "3 passed" in (directory / "validation.log").read_text()
    assert "not physical owner approval" in receipt["continuations"]


def test_modified_followup_tests_are_rejected_without_executing_them(harness, monkeypatch):
    module, root = harness
    fixtures = []

    def scripted_cli(argv):
        fixture = Path(argv[argv.index("--repo-root") + 1])
        fixtures.append(fixture)
        if len(fixtures) == 1:
            print("coding_session_id: preserved-session")
        else:
            (fixture / "math_ops.py").write_text("def add(a, b):\n    return a + b\n")
            (fixture / "test_math_ops.py").write_text(
                "from pathlib import Path\nPath('unexpected-test-execution').write_text('ran')\n"
            )
        return 0

    monkeypatch.setattr(module.cli, "main", scripted_cli)
    assert module.main() == 1
    receipt, directory = result(root)
    assert not receipt["passed"] and not receipt["tests_unchanged"]
    assert receipt["validation_exit_code"] is None
    assert "protected tests" in receipt["failure_reason"]
    assert not (directory / "validation.log").exists()
    assert not (fixtures[-1] / "unexpected-test-execution").exists()


@pytest.mark.parametrize("defect", ["source_edit", "test_edit", "cli_failure", "no_session"])
def test_first_turn_failure_or_premature_edit_stops_before_followup(harness, monkeypatch, defect):
    module, root = harness
    calls = []

    def scripted_cli(argv):
        calls.append(list(argv))
        assert len(calls) == 1, "follow-up must not run after a failed first turn"
        fixture = Path(argv[argv.index("--repo-root") + 1])
        if defect == "source_edit":
            (fixture / "math_ops.py").write_text("def add(a, b):\n    return a + b\n")
        elif defect == "test_edit":
            (fixture / "test_math_ops.py").write_text("# removed tests\n")
        if defect != "no_session":
            print("coding_session_id: preserved-session")
        return 1 if defect == "cli_failure" else 0

    monkeypatch.setattr(module.cli, "main", scripted_cli)
    assert module.main() == 1
    assert len(calls) == 1
    receipt, directory = result(root)
    assert not receipt["passed"] and receipt["failure_reason"]
    assert receipt["validation_exit_code"] is None
    assert not (directory / "validation.log").exists()
    assert receipt["first_turn_source_unchanged"] == (defect != "source_edit")
    assert receipt["first_turn_tests_unchanged"] == (defect != "test_edit")


def test_cli_exception_preserves_partial_log_and_restores_input(harness, monkeypatch):
    module, root = harness
    original_input, original_stdin = builtins.input, sys.stdin

    def interrupted_cli(argv):
        print("partial scripted execution evidence")
        raise RuntimeError("scripted failure")

    monkeypatch.setattr(module.cli, "main", interrupted_cli)
    with pytest.raises(RuntimeError, match="scripted failure"):
        module.main()
    assert builtins.input is original_input and sys.stdin is original_stdin
    logs = list((root / "artifacts").glob("*/assistant.log"))
    assert len(logs) == 1 and "partial scripted execution evidence" in logs[0].read_text()


@pytest.mark.parametrize("timeout", ["nan", "inf", "0", "-1"])
def test_invalid_timeout_refuses_before_preparing_or_contacting_cli(harness, monkeypatch, timeout):
    module, root = harness
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), f"--timeout-seconds={timeout}"])
    monkeypatch.setattr(module.cli, "main", lambda *_: pytest.fail("CLI was contacted"))
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 2
    assert not (root / "artifacts").exists()
