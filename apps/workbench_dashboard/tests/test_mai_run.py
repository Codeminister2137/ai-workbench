"""Mai-session run executor: argv handoff, receipts, failure classes."""

from __future__ import annotations

from mai_run import (
    build_mai_argv,
    build_mai_executor,
    classify_failure,
    mai_receipt,
    run_mai_session,
)


def _run(**overrides):
    record = {"id": "r1", "title": "Do it", "body": "Details."}
    record.update(overrides)
    return record


def test_argv_hands_task_to_mai_without_model_override(tmp_path) -> None:
    argv = build_mai_argv(_run(), repo_root=tmp_path, user_config=tmp_path / "user.toml")
    assert argv[0].startswith("Run r1: Do it")
    assert "Details." in argv[0]
    assert "--model" not in argv  # orchestrator decides inside Mai
    assert argv[argv.index("--mode") + 1] == "implement"
    assert "--execute" in argv
    assert argv[argv.index("--coding-session") + 1] == "new"
    assert argv[argv.index("--repo-root") + 1] == str(tmp_path)
    assert argv[argv.index("--catalog") + 1].endswith("model_catalog.toml")
    assert argv[argv.index("--approval-policy") + 1] == "trusted_local"


def test_session_stdin_is_eof_not_a_hang() -> None:
    import sys

    seen = {}

    def runner(argv):
        seen["data"] = sys.stdin.read()
        seen["tty"] = sys.stdin.isatty()
        return 0

    real_stdin = sys.stdin
    run_mai_session(["prompt"], runner=runner)
    assert seen == {"data": "", "tty": False}
    assert sys.stdin is real_stdin


def test_argv_honors_explicit_catalog(tmp_path) -> None:
    argv = build_mai_argv(_run(), repo_root=tmp_path, user_config="u", catalog="c.toml")
    assert argv[argv.index("--catalog") + 1] == "c.toml"


def test_parse_mai_facts_pulls_session_and_route() -> None:
    from mai_run import parse_mai_facts

    facts = parse_mai_facts("noise\ncoding_session_id: abc123\neffective_route_id: ollama/q\n")
    assert facts == {"coding_session_id": "abc123", "effective_route_id": "ollama/q"}
    assert parse_mai_facts("nothing here") == {}


def test_subprocess_backend_captures_and_times_out(tmp_path) -> None:
    import sys

    from mai_run import mai_receipt, run_mai_subprocess

    echo = [sys.executable, "-c", "print('coding_session_id: s9')"]
    ok = run_mai_subprocess(["ignored"], cmd_prefix=echo, timeout_seconds=30)
    assert ok.exit_code == 0 and ok.facts == {"coding_session_id": "s9"}
    assert mai_receipt(ok, ["x"])["status"] == "completed"
    sleepy = [sys.executable, "-c", "import time; time.sleep(30)"]
    slow = run_mai_subprocess(["ignored"], cmd_prefix=sleepy, timeout_seconds=1)
    assert slow.exit_code == 3 and "timed out" in (slow.error or "")
    assert mai_receipt(slow, ["x"])["status"] == "failed"
    missing = run_mai_subprocess(["ignored"], cmd_prefix=["definitely-not-a-binary-xyz"])
    assert missing.exit_code == 3 and "spawn failed" in (missing.error or "")


def test_executor_backend_dispatch() -> None:
    seen: dict = {}

    def fake_session(argv, runner=None):
        seen["in_process"] = True
        from mai_run import MaiRunOutcome

        return MaiRunOutcome(exit_code=0, stdout_tail="", stderr_tail="")

    import mai_run

    real_session, real_subprocess = mai_run.run_mai_session, mai_run.run_mai_subprocess
    try:

        def fake_subprocess(argv, cmd_prefix=None, timeout_seconds=0, cwd=None):
            seen["subprocess"] = True
            from mai_run import MaiRunOutcome

            return MaiRunOutcome(exit_code=0, stdout_tail="", stderr_tail="")

        mai_run.run_mai_subprocess = fake_subprocess
        build_mai_executor(".", "u")(_run())
        assert seen == {"subprocess": True}
        seen.clear()
        mai_run.run_mai_session = fake_session
        build_mai_executor(".", "u", backend="in-process")(_run())
        assert seen == {"in_process": True}
    finally:
        mai_run.run_mai_session = real_session
        mai_run.run_mai_subprocess = real_subprocess


def test_config_validates_mai_backend(tmp_path) -> None:
    import json

    import pytest
    from dashboard_config import load_config

    path = tmp_path / "dashboard.json"
    assert load_config(path).mai_backend == "subprocess"
    path.write_text(json.dumps({"mai_backend": "in-process"}), encoding="utf-8")
    assert load_config(path).mai_backend == "in-process"
    path.write_text(json.dumps({"mai_backend": "subprocess"}), encoding="utf-8")
    assert load_config(path).mai_backend == "subprocess"
    path.write_text(json.dumps({"mai_backend": "telepathy"}), encoding="utf-8")
    with pytest.raises(ValueError, match="mai_backend"):
        load_config(path)


def test_facts_survive_tail_truncation() -> None:
    def runner(argv):
        print("coding_session_id: s1")
        print("x" * 5000)
        return 0

    outcome = run_mai_session(["prompt"], runner=runner)
    assert "coding_session_id" not in outcome.stdout_tail
    assert outcome.facts == {"coding_session_id": "s1"}
    assert mai_receipt(outcome, ["prompt"])["mai_session_id"] == "s1"


def test_session_captures_output_and_exit_code() -> None:
    def runner(argv):
        print("routing: fake/route")
        return 0

    outcome = run_mai_session(["prompt"], runner=runner)
    assert outcome.exit_code == 0 and outcome.error is None
    assert "fake/route" in outcome.stdout_tail


def test_session_failure_maps_to_receipt() -> None:
    def boom(argv):
        raise RuntimeError("boom")

    outcome = run_mai_session(["prompt"], runner=boom)
    assert outcome.error == "RuntimeError: boom"
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "failed"
    assert receipt["failure_class"] == "unknown"
    assert receipt["source"] == "mai-session"


def test_nonzero_exit_without_error_uses_exit_text() -> None:
    outcome = run_mai_session(["prompt"], runner=lambda argv: 2)
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "failed"
    assert "exited with code 2" in receipt["error"]


def test_completed_receipt_carries_transcript_tails() -> None:
    def runner(argv):
        print("did the thing")
        return 0

    receipt = build_mai_executor(".", "user.toml", runner=runner, backend="in-process")(_run())
    assert receipt["status"] == "completed"
    assert "did the thing" in receipt["stdout_tail"]
    assert receipt["mai_argv"][0].startswith("Run r1:")


def test_classify_failure_prefers_allowance_then_provider() -> None:
    assert classify_failure("allowance exhausted for route") == "allowance"
    assert classify_failure("ProviderError: boom") == "provider"
    assert classify_failure("model auth timeout") == "provider"
    assert classify_failure("weird local crash") == "unknown"
    assert classify_failure("denied", "ProviderError: x") == "allowance"
