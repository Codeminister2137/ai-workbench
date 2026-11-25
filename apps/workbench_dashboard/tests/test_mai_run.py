"""Mai-session run executor: argv handoff, receipts, failure classes."""

from __future__ import annotations

from pathlib import Path

from mai_run import (
    MAI_INSTRUCTION_BUDGET_CHARS,
    TAIL_CHARS,
    MaiRunOutcome,
    build_mai_argv,
    build_mai_executor,
    capture_tail,
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


def test_argv_accepts_explicit_overrides(tmp_path) -> None:
    argv = build_mai_argv(
        _run(),
        repo_root=tmp_path,
        user_config=tmp_path / "user.toml",
        coding_session="abc",
        provider="ollama",
        model="qwen3:14b",
    )
    assert argv[argv.index("--coding-session") + 1] == "abc"
    assert argv[argv.index("--provider") + 1] == "ollama"
    assert argv[argv.index("--model") + 1] == "qwen3:14b"


def test_argv_timeout_override_clamped(tmp_path) -> None:
    from mai_run import _run_timeout_seconds

    argv = build_mai_argv(_run(), repo_root=tmp_path, user_config="u", timeout_seconds=1200.0)
    assert argv[argv.index("--timeout-seconds") + 1] == "1200"
    assert _run_timeout_seconds({"mai_timeout_seconds": 30}) is None
    assert _run_timeout_seconds({"mai_timeout_seconds": "xx"}) is None
    assert _run_timeout_seconds({"mai_timeout_seconds": 99999}) == 1740.0


def test_invalid_timeout_overrides_fall_back_before_argv_construction(tmp_path) -> None:
    from mai_run import _run_timeout_seconds

    for raw in ("nan", float("nan"), "inf", "-inf", float("inf"), 10**1000):
        timeout = _run_timeout_seconds({"mai_timeout_seconds": raw})
        assert timeout is None
        argv = build_mai_argv(_run(), repo_root=tmp_path, user_config="u", timeout_seconds=timeout)
        assert "--timeout-seconds" not in argv


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
    assert slow.timed_out is True
    assert mai_receipt(slow, ["x"])["status"] == "failed"
    assert mai_receipt(slow, ["x"])["timed_out"] is True
    assert mai_receipt(ok, ["x"]).get("timed_out", False) is False
    missing = run_mai_subprocess(["ignored"], cmd_prefix=["definitely-not-a-binary-xyz"])
    assert missing.exit_code == 3 and "spawn failed" in (missing.error or "")


def test_subprocess_backend_survives_nonlocale_bytes() -> None:
    import sys

    from mai_run import run_mai_subprocess

    # 0x81 is undefined in cp1252; locale decoding used to crash capture.
    raw = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'ok\\x81done\\n')"]
    outcome = run_mai_subprocess(["ignored"], cmd_prefix=raw, timeout_seconds=30)
    assert outcome.exit_code == 0
    assert "ok" in outcome.stdout_tail and "done" in outcome.stdout_tail


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


def test_empty_output_on_exit_zero_is_provider_failure() -> None:
    def runner(argv):
        return 0

    outcome = run_mai_session(["prompt"], runner=runner)
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "failed"
    assert receipt["failure_class"] == "provider"
    assert "empty output" in receipt["error"]


def test_reported_failure_on_exit_zero_is_failed_not_completed() -> None:
    from mai_run import MaiRunOutcome

    tail = (
        "coding_session_id: s1\n"
        "## **SUMMARY**\n"
        "- Notes: status=failed; execution_status=failed; "
        "failure_reason=No model candidate satisfied the task profile "
        "(route requires cost policy allowances_allowed); "
        "provider=unknown\n"
    )
    outcome = MaiRunOutcome(exit_code=0, stdout_tail=tail, stderr_tail="")
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "failed"
    assert "No model candidate" in receipt["error"]
    assert receipt["failure_class"] == "allowance"
    assert receipt["source"] == "mai-session"


def test_intermediate_failure_with_completed_execution_stays_completed() -> None:
    from mai_run import MaiRunOutcome

    tail = (
        "coding_session_id: s1\n"
        "external_agent_warning: intermediate failure (command_execution)"
        " with complete final result\n"
        "## **SUMMARY**\n"
        "- Notes: status=ready; execution_status=completed; "
        "failure_reason=command_execution\n"
    )
    outcome = MaiRunOutcome(exit_code=0, stdout_tail=tail, stderr_tail="")
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "completed"


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


def test_exhaustion_handoff_sets_receipt_flag() -> None:
    def runner(argv):
        print("fallback_handoff=status:continuation_stopped, reason:deadline_or_no_route")
        return 1

    outcome = run_mai_session(["prompt"], runner=runner)
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "failed"
    assert receipt["exhausted_tree"] is True


def test_plain_failure_leaves_receipt_flag_clear() -> None:
    def runner(argv):
        print("execution_status: failed")
        return 1

    outcome = run_mai_session(["prompt"], runner=runner)
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["status"] == "failed"
    assert receipt["exhausted_tree"] is False


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


def test_classify_failure_ignores_budget_prose_in_tails() -> None:
    assert (
        classify_failure(
            "Mai reported failure: command_execution",
            "report: defer allowance routes without a bound; quota fine",
        )
        != "allowance"
    )
    assert (
        classify_failure(
            "Mai reported failure: command_execution",
            "report: defer allowance routes without a bound; quota fine",
        )
        != "config"
    )
    assert (
        classify_failure("Required instructions exceed instruction_budget_chars=64000: AGENTS.md")
        == "config"
    )


def test_native_context_rejection_is_config_not_allowance() -> None:
    outcome = mai_receipt(
        MaiRunOutcome(
            exit_code=1,
            stdout_tail="",
            stderr_tail=(
                "failure_reason: Native model input does not fit the estimated context budget; "
                "input_tokens=66744 output_tokens=8192 framing_tokens=256 context_tokens=65536"
            ),
        ),
        [],
    )
    assert outcome["failure_class"] == "config"
    assert "context_tokens=65536" in outcome["stderr_tail"]


def test_loop_compaction_thrash_is_config_not_allowance() -> None:
    """Loop-context budget overflow must not pause the drain as allowance."""
    outcome = mai_receipt(
        MaiRunOutcome(
            exit_code=1,
            stdout_tail="",
            stderr_tail=(
                "failure_reason: loop context still exceeds its budget after 3 compactions; "
                "one large output likely refills the window."
            ),
        ),
        [],
    )
    assert outcome["failure_class"] == "config"


def test_argv_carries_raised_instruction_budget(tmp_path) -> None:
    argv = build_mai_argv(_run(), repo_root=tmp_path, user_config=tmp_path / "user.toml")
    assert argv[argv.index("--instruction-budget-chars") + 1] == str(MAI_INSTRUCTION_BUDGET_CHARS)


def test_instruction_budget_covers_repo_agents_md() -> None:
    # Regression: every Mai run failed once root AGENTS.md outgrew 64000.
    agents = Path(__file__).resolve().parents[3] / "AGENTS.md"
    assert MAI_INSTRUCTION_BUDGET_CHARS > agents.stat().st_size


def test_progress_subprocess_and_executor(tmp_path):
    import sys

    from chat_agent import read_progress

    path = tmp_path / "progress.jsonl"
    command = [
        sys.executable,
        "-u",
        "-c",
        "print('Tool read'); print('coding_session_id: s1'); print('done')",
    ]
    receipt = build_mai_executor(
        tmp_path, tmp_path / "u.toml", mai_cmd_prefix=command, progress_path=path
    )(_run())
    assert read_progress(path) == ["Tool read", "coding_session_id: s1", "done"]
    assert receipt["status"] == "completed"
    assert receipt["mai_session_id"] == "s1"
    assert receipt["stdout_tail"].endswith("done\n")
    assert "--approval-policy" in receipt["mai_argv"]


def test_progress_failure_does_not_break_capture(tmp_path):
    import sys

    from mai_run import run_mai_subprocess

    outcome = run_mai_subprocess(
        [], cmd_prefix=[sys.executable, "-c", "print('done')"], progress_path=tmp_path
    )
    assert outcome.exit_code == 0
    assert outcome.stdout_tail == "done\n"


def test_progress_arrives_before_process_exit(tmp_path):
    import sys
    import time
    from concurrent.futures import ThreadPoolExecutor

    from chat_agent import read_progress
    from mai_run import run_mai_subprocess

    path = tmp_path / "live.jsonl"
    release = tmp_path / "release"
    script = (
        "import pathlib,sys,time; print('Tool read'); "
        "release=pathlib.Path(sys.argv[1]); "
        "exec('while not release.exists(): time.sleep(0.01)')"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            run_mai_subprocess,
            [],
            cmd_prefix=[sys.executable, "-c", script, str(release)],
            progress_path=path,
            timeout_seconds=10,
        )
        try:
            deadline = time.monotonic() + 5
            while not read_progress(path) and time.monotonic() < deadline:
                time.sleep(0.01)
            assert read_progress(path) == ["Tool read"]
            assert not future.done()
        finally:
            release.touch()
        assert future.result(timeout=10).exit_code == 0


def test_capture_tail_marks_truncation_at_line_boundary() -> None:
    body = "".join(f"line {i:04d} with enough padding to fill bytes\n" for i in range(500))
    assert len(body) > TAIL_CHARS
    tail = capture_tail(body)
    assert "truncated" in tail.splitlines()[0]
    assert tail.splitlines()[1].startswith("line ")  # no mid-line start
    assert tail.endswith(body[-200:])


def test_capture_tail_passthrough_short_output() -> None:
    assert capture_tail("short\n") == "short\n"


def test_executor_refuses_empty_task_body() -> None:
    # An instruction-only run used to reach Mai with an empty Task section
    # and burn a session answering nothing (2026-11-18 chat turn).
    receipt = build_mai_executor(".", "u")({"id": "chat-x", "instruction": "lost"})
    assert receipt["status"] == "failed"
    assert "empty task body" in receipt["error"]
    blank = build_mai_executor(".", "u")(_run(body="   "))
    assert blank["status"] == "failed"


def test_receipt_surfaces_mai_failure_reason() -> None:
    from mai_run import MaiRunOutcome, mai_failure_reason

    tail = "Notes: status=failed; failure_reason=External agent timed out after 180 seconds; category=unknown"
    assert mai_failure_reason(tail) == "External agent timed out after 180 seconds"
    assert mai_failure_reason("nothing here") is None
    outcome = MaiRunOutcome(exit_code=1, stdout_tail=tail, stderr_tail="")
    receipt = mai_receipt(outcome, ["prompt"])
    assert receipt["error"] == (
        "Mai session exited with code 1: External agent timed out after 180 seconds"
    )
    assert receipt["failure_class"] == "provider"
    bare = mai_receipt(MaiRunOutcome(exit_code=1, stdout_tail="", stderr_tail=""), ["p"])
    assert bare["error"] == "Mai session exited with code 1"


def test_receipt_surfaces_colon_failure_diagnostic():
    from mai_run import MaiRunOutcome

    reason = "loop instructions plus the latest message exceed the loop context budget"
    receipt = mai_receipt(MaiRunOutcome(1, f"failure_reason: {reason}\n", ""), ["p"])
    assert receipt["error"].endswith(reason)


def test_mai_loop_budget_reserves_instruction_and_history_space():
    argv = build_mai_argv(_run(), repo_root=".", user_config="u")
    budget = int(argv[argv.index("--loop-context-budget-chars") + 1])
    assert budget >= MAI_INSTRUCTION_BUDGET_CHARS + 2 * 7000 + 30000


def test_retrying_executor_retries_provider_timeouts_once() -> None:
    from mai_run import build_retrying_executor

    calls: list = []

    def flaky(run: dict) -> dict:
        calls.append(run)
        if len(calls) == 1:
            return {
                "status": "failed",
                "error": "Mai session exited with code 1: External agent timed out after 180 seconds",
                "failure_class": "provider",
            }
        return {"status": "completed", "stdout_tail": "recovered"}

    receipt = build_retrying_executor(flaky)({"id": "r1"})
    assert len(calls) == 2
    assert receipt["status"] == "completed"
    assert receipt["attempt"] == 2
    assert "timed out" in receipt["retry_of"]["error"]


def test_retrying_executor_prefers_structured_timeout_flag() -> None:
    """Scope C: supervisor kills retry on the machine flag, no text needed."""
    from mai_run import build_retrying_executor

    calls: list = []

    def killed(run: dict) -> dict:
        calls.append(run)
        if len(calls) == 1:
            return {
                "status": "failed",
                "error": "Mai session killed",  # no timeout words at all
                "failure_class": "provider",
                "timed_out": True,
            }
        return {"status": "completed", "stdout_tail": "recovered"}

    receipt = build_retrying_executor(killed)({"id": "r1"})
    assert len(calls) == 2
    assert receipt["status"] == "completed"


def test_retrying_executor_ignores_prose_only_timeouts() -> None:
    """Agent chatter mentioning timeouts must not trigger a retry."""
    from mai_run import build_retrying_executor

    seen: list = []

    def inner(run: dict) -> dict:
        seen.append(run)
        return {
            "status": "failed",
            "error": "Mai session exited with code 1",
            "failure_class": "provider",
            "timed_out": False,
            "stdout_tail": "I timed out waiting for the slow test suite",
            "stderr_tail": "",
        }

    receipt = build_retrying_executor(inner)({"id": "r"})
    assert len(seen) == 1
    assert "attempt" not in receipt
    assert receipt["status"] == "failed"


def test_retrying_executor_passes_through_other_failures() -> None:
    from mai_run import build_retrying_executor

    seen: list = []

    def inner(run: dict) -> dict:
        seen.append(run)
        return dict(run["canned"])

    cases = [
        {"status": "completed"},
        {"status": "failed", "error": "Mai session exited with code 1", "failure_class": "unknown"},
        {"status": "failed", "error": "allowance exhausted", "failure_class": "allowance"},
    ]
    for canned in cases:
        seen.clear()
        receipt = build_retrying_executor(inner)({"id": "r", "canned": canned})
        assert len(seen) == 1
        assert "attempt" not in receipt
        assert receipt["status"] == canned["status"]


def test_subprocess_is_unbuffered_and_streams_per_run(tmp_path) -> None:
    import sys

    from chat_agent import read_progress

    env_probe = [sys.executable, "-c", "import os; print(os.environ.get('PYTHONUNBUFFERED'))"]
    receipt = build_mai_executor(
        tmp_path, tmp_path / "u.toml", mai_cmd_prefix=env_probe, progress_dir=tmp_path / "prog"
    )(_run(id="r-9"))
    assert receipt["stdout_tail"].strip() == "1"
    stream = tmp_path / "prog" / "r-9.jsonl"
    assert stream.is_file()
    assert read_progress(stream) == ["1"]
    assert receipt["progress_path"] == str(stream)


def test_explicit_progress_path_wins_over_dir(tmp_path) -> None:
    import sys

    direct = tmp_path / "direct.jsonl"
    receipt = build_mai_executor(
        tmp_path,
        tmp_path / "u.toml",
        mai_cmd_prefix=[sys.executable, "-c", "print('hi')"],
        progress_path=direct,
        progress_dir=tmp_path / "prog",
    )(_run())
    assert receipt["progress_path"] == str(direct)
    assert direct.is_file()
    assert not (tmp_path / "prog").exists()
