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


def test_argv_honors_explicit_catalog(tmp_path) -> None:
    argv = build_mai_argv(_run(), repo_root=tmp_path, user_config="u", catalog="c.toml")
    assert argv[argv.index("--catalog") + 1] == "c.toml"


def test_parse_mai_facts_pulls_session_and_route() -> None:
    from mai_run import parse_mai_facts

    facts = parse_mai_facts("noise\ncoding_session_id: abc123\neffective_route_id: ollama/q\n")
    assert facts == {"coding_session_id": "abc123", "effective_route_id": "ollama/q"}
    assert parse_mai_facts("nothing here") == {}


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

    receipt = build_mai_executor(".", "user.toml", runner=runner)(_run())
    assert receipt["status"] == "completed"
    assert "did the thing" in receipt["stdout_tail"]
    assert receipt["mai_argv"][0].startswith("Run r1:")


def test_classify_failure_prefers_allowance_then_provider() -> None:
    assert classify_failure("allowance exhausted for route") == "allowance"
    assert classify_failure("ProviderError: boom") == "provider"
    assert classify_failure("model auth timeout") == "provider"
    assert classify_failure("weird local crash") == "unknown"
    assert classify_failure("denied", "ProviderError: x") == "allowance"
