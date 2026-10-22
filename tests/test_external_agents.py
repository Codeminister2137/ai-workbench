import json
import subprocess
import sys
from pathlib import Path

import pytest
from ai_orchestrator import AccessMethod
from ai_provider.external_agents import (
    ExternalAgentConfig,
    _external_agent_progress_line,
    _external_agent_result_from_completed_process,
    _external_agent_stderr_progress_line,
    build_codex_plugin_command,
    build_external_agent_command,
    codex_plugin_status_by_name,
    external_agent_command,
    parse_codex_plugin_list,
    parse_external_agent_jsonl,
    run_diagnostic_command,
    validate_codex_plugin_selector,
)

PRIVATE_COMMAND = "private_command"
PRIVATE_ARGUMENT = "--private_arg"


def test_completed_event_with_structured_overload_error_is_failure():
    from ai_provider.external_agents import parse_external_agent_jsonl

    event = {
        "type": "task_complete",
        "error": {
            "message": "Selected model is at capacity. Please try a different model.",
            "codex_error_info": "server_overloaded",
        },
    }
    summary = parse_external_agent_jsonl(json.dumps(event))
    assert summary.failure_reason == event["error"]["message"]


class TestUsageReceipts:
    def test_copilot_final_result_retains_existing_raw_usage_contract(self):
        events = [
            {
                "type": "session.usage_checkpoint",
                "data": {
                    "totalPremiumRequests": 1,
                    "totalNanoAiu": 200,
                },
            },
            {
                "type": "result",
                "usage": {
                    "premiumRequests": 2,
                    "codeChanges": {"private_file": "private change"},
                },
            },
        ]
        usage = parse_external_agent_jsonl("\n".join(json.dumps(event) for event in events)).usage
        assert usage == events[-1]["usage"]

    def test_latest_copilot_checkpoint_is_retained_without_summing_or_private_cache_state(self):
        checkpoints = [
            {
                "type": "session.usage_checkpoint",
                "data": {
                    "totalPremiumRequests": amount,
                    "totalNanoAiu": amount * 100,
                    "modelCacheState": {"private": "must not be exported"},
                    "promptCacheBreakState": "private prompt state",
                },
            }
            for amount in (1, 3)
        ]
        events = "\n".join(json.dumps(event) for event in checkpoints)
        usage = parse_external_agent_jsonl(events).usage
        assert usage == {"premium_requests": 3, "nano_aiu": 300, "scope": "session_checkpoint"}
        assert "private" not in json.dumps(usage)
        progress = _external_agent_progress_line(json.dumps(checkpoints[-1]))
        assert progress is not None and '"premium_requests": 3' in progress
        assert "private" not in progress

    @pytest.mark.parametrize("invalid", [True, -1, "1", float("nan"), float("inf")])
    def test_invalid_copilot_counters_remain_unknown(self, invalid):
        event = {
            "type": "session.usage_checkpoint",
            "data": {"totalPremiumRequests": invalid, "totalNanoAiu": invalid},
        }
        assert parse_external_agent_jsonl(json.dumps(event)).usage is None


def test_antigravity_zero_exit_permission_refusal_is_a_failure(tmp_path: Path) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.ANTIGRAVITY_CLI,
        command="agy",
        model="fixture",
        cwd=tmp_path,
        timeout_seconds=60.0,
    )
    diagnostic = (
        'jetski: no output produced \u2014 a tool required the "mcp" permission that '
        "headless mode cannot prompt for, so it was auto-denied."
    )
    result = _external_agent_result_from_completed_process(
        ("agy",), config, subprocess.CompletedProcess(("agy",), 0, "", diagnostic)
    )

    assert result.returncode == 0
    assert result.stderr == diagnostic
    assert result.events is not None
    assert result.events.failure_reason is not None
    assert "headless tool permission was denied" in result.events.failure_reason


def test_antigravity_permission_diagnostic_does_not_override_answer(tmp_path: Path) -> None:
    answer_path = tmp_path / "answer.txt"
    answer_path.write_text("Review complete.", encoding="utf-8")
    config = ExternalAgentConfig(
        access_method=AccessMethod.ANTIGRAVITY_CLI,
        command="agy",
        model="fixture",
        cwd=tmp_path,
        timeout_seconds=60.0,
        output_last_message_path=answer_path,
    )
    result = _external_agent_result_from_completed_process(
        ("agy",),
        config,
        subprocess.CompletedProcess(
            ("agy",),
            0,
            "",
            "jetski: no output produced; headless mode tool auto-denied",
        ),
    )

    assert result.last_message == "Review complete."
    assert result.events is None


def test_antigravity_benign_stderr_does_not_create_a_failure(tmp_path: Path) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.ANTIGRAVITY_CLI,
        command="agy",
        model="fixture",
        cwd=tmp_path,
        timeout_seconds=60.0,
    )
    result = _external_agent_result_from_completed_process(
        ("agy",), config, subprocess.CompletedProcess(("agy",), 0, "", "warning: retrying")
    )

    assert result.events is None


def test_build_external_agent_command_can_enable_codex_search(tmp_path: Path) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.CODEX_CLI,
        command="codex",
        model="gpt-5.5",
        cwd=tmp_path,
        timeout_seconds=60.0,
        web_search=True,
    )

    command = build_external_agent_command(config)

    assert command[:5] == ("codex", "--search", "--ask-for-approval", "never", "exec")
    assert "exec" in command
    assert command[-1] == "-"


def test_build_external_agent_command_omits_codex_search_by_default(tmp_path: Path) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.CODEX_CLI,
        command="codex",
        model="gpt-5.5",
        cwd=tmp_path,
        timeout_seconds=60.0,
    )

    command = build_external_agent_command(config)

    assert "--search" not in command
    assert command[:4] == ("codex", "--ask-for-approval", "never", "exec")


def test_build_external_agent_command_can_enable_project_mcp_tools(tmp_path: Path) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.CODEX_CLI,
        command="codex",
        model="gpt-5.5",
        cwd=tmp_path,
        timeout_seconds=60.0,
        codex_mcp_tools=True,
    )

    command = build_external_agent_command(config)

    assert command[0] == "codex"
    assert "exec" in command
    assert command.index("-c") < command.index("exec")
    command_text = " ".join(command)
    escaped_python = sys.executable.replace("\\", "\\\\")
    assert f"mcp_servers.repo_assistant_tools.command='{escaped_python}'" in command_text
    assert "ai_agent.mcp_server" in command_text
    assert "delegate_task" in command_text
    assert str(tmp_path.resolve()) in command_text


def test_build_external_agent_command_maps_interactive_approval(tmp_path: Path) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.CODEX_CLI,
        command="codex",
        model="gpt-5.5",
        cwd=tmp_path,
        timeout_seconds=60.0,
        approval_policy="interactive",
    )

    command = build_external_agent_command(config)

    assert command[:4] == ("codex", "--ask-for-approval", "on-request", "exec")


def test_build_external_agent_command_resume_preserves_repo_root_and_sandbox(
    tmp_path: Path,
) -> None:
    config = ExternalAgentConfig(
        access_method=AccessMethod.CODEX_CLI,
        command="codex",
        model="gpt-5.5",
        cwd=tmp_path,
        timeout_seconds=60.0,
        sandbox="danger-full-access",
        approval_policy="never",
        resume="last",
    )

    command = build_external_agent_command(config)

    assert command == (
        "codex",
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(tmp_path),
        "--model",
        "gpt-5.5",
        "--sandbox",
        "danger-full-access",
        "resume",
        "--json",
        "--last",
        "-",
    )


def test_build_external_agent_command_can_attach_codex_images(tmp_path: Path) -> None:
    first_image = tmp_path / "before.png"
    second_image = tmp_path / "after.jpg"
    config = ExternalAgentConfig(
        access_method=AccessMethod.CODEX_CLI,
        command="codex",
        model="gpt-5.5",
        cwd=tmp_path,
        timeout_seconds=60.0,
        image_paths=(first_image, second_image),
    )

    command = build_external_agent_command(config)

    assert command.count("--image") == 2
    assert str(first_image) in command
    assert str(second_image) in command
    assert command[-1] == "-"


def test_external_agent_command_discovers_antigravity_agy_alias(monkeypatch) -> None:
    monkeypatch.delenv("ANTIGRAVITY_COMMAND", raising=False)

    def fake_which(command: str) -> str | None:
        return "C:/tools/agy.exe" if command == "agy" else None

    monkeypatch.setattr("ai_provider.external_agents.shutil.which", fake_which)

    assert external_agent_command(AccessMethod.ANTIGRAVITY_CLI) == "C:/tools/agy.exe"


def test_external_agent_command_discovers_kiro_cli_alias(monkeypatch) -> None:
    monkeypatch.delenv("KIRO_COMMAND", raising=False)

    def fake_which(command: str) -> str | None:
        return "C:/tools/kiro-cli.exe" if command == "kiro-cli" else None

    monkeypatch.setattr("ai_provider.external_agents.shutil.which", fake_which)

    assert external_agent_command(AccessMethod.KIRO_CLI) == "C:/tools/kiro-cli.exe"


def test_parse_external_agent_jsonl_counts_web_search_events() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            [
                '{"type":"item.started","item":{"type":"web_search","query":""}}',
                '{"type":"item.completed","item":{"type":"web_search","query":"OpenAI"}}',
                '{"type":"final_answer","content":"done"}',
            ]
        )
    )

    assert len(events.web_search_events) == 2
    assert events.final_answer == "done"


def test_parse_external_agent_jsonl_ignores_completed_command_output_failures() -> None:
    events = parse_external_agent_jsonl(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "status": "completed",
                            "aggregated_output": "FAILED tests/test_example.py::test_case",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": "## SUMMARY\nValidation found one failed test before the fix.",
                        },
                    }
                ),
                '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}',
            ]
        )
    )

    assert events.failure_reason is None


@pytest.mark.parametrize(
    "config_path", [r"C:\Users\Owner\.codex\config.toml", "/home/owner/.codex/config.toml"]
)
def test_codex_feature_notice_preserves_successful_answer(config_path: str) -> None:
    notice = (
        "Under-development features enabled: code_mode, skip_host_skill_discovery. "
        "Under-development features are incomplete and may behave unpredictably. "
        "To suppress this warning, set `suppress_unstable_features_warning = true` "
        f"in {config_path}."
    )
    warning = {"type": "item.completed", "item": {"type": "error", "message": notice}}
    events = parse_external_agent_jsonl(
        "\n".join(
            map(
                json.dumps,
                [
                    warning,
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "Review complete."},
                    },
                    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
                ],
            )
        )
    )
    assert events.failure_reason is None
    assert events.final_answer == "Review complete."
    assert events.usage == {"input_tokens": 10, "output_tokens": 2}
    assert "failure -" not in (_external_agent_progress_line(json.dumps(warning)) or "")


@pytest.mark.parametrize(
    "event_type,item_status,message_suffix",
    [
        ("item.failed", None, ""),
        ("item.completed", "failed", ""),
        ("item.completed", None, " Additional fatal failure."),
    ],
)
def test_codex_feature_notice_does_not_hide_failure_labels_or_extra_errors(
    event_type: str,
    item_status: str | None,
    message_suffix: str,
) -> None:
    message = (
        "Under-development features enabled: code_mode, skip_host_skill_discovery. "
        "Under-development features are incomplete and may behave unpredictably. "
        "To suppress this warning, set `suppress_unstable_features_warning = true` "
        "in /home/owner/.codex/config.toml." + message_suffix
    )
    item = {"type": "error", "message": message}
    if item_status is not None:
        item["status"] = item_status
    assert parse_external_agent_jsonl(json.dumps({"type": event_type, "item": item})).failure_reason


@pytest.mark.parametrize(
    "error_event",
    [
        {"type": "error", "message": "Quota exhausted."},
        {"type": "turn.failed", "error": {"message": "Authentication failed."}},
        {"type": "item.completed", "item": {"type": "error", "message": "Tool failed."}},
    ],
)
@pytest.mark.parametrize("warning_first", [True, False])
def test_codex_feature_notice_does_not_clear_real_stream_failure(
    error_event: dict,
    warning_first: bool,
) -> None:
    warning = {
        "type": "item.completed",
        "item": {
            "type": "error",
            "message": (
                "Under-development features enabled: code_mode. Under-development features "
                "are incomplete and may behave unpredictably. To suppress this warning, "
                "set `suppress_unstable_features_warning = true` in /home/owner/.codex/config.toml."
            ),
        },
    }
    stream = [warning, error_event] if warning_first else [error_event, warning]
    assert parse_external_agent_jsonl("\n".join(map(json.dumps, stream))).failure_reason == (
        parse_external_agent_jsonl(json.dumps(error_event)).failure_reason
    )


@pytest.mark.parametrize("returncode,expected_status", [(0, "completed"), (7, "failed")])
def test_codex_feature_notice_preserves_process_exit_and_session_receipt(
    tmp_path: Path,
    returncode: int,
    expected_status: str,
) -> None:
    from ai_provider.coding_sessions import ACTIVE_SESSION, CodingSession
    from ai_provider.external_agents import run_external_agent

    session = CodingSession.open(tmp_path / "coding.sqlite3", "new", tmp_path, "Review", [])
    config = ExternalAgentConfig(AccessMethod.CODEX_CLI, "codex", "fixture", tmp_path, 60.0)
    stream = "\n".join(
        map(
            json.dumps,
            [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "error",
                        "message": (
                            "Under-development features enabled: code_mode. "
                            "Under-development features are incomplete and may behave "
                            "unpredictably. To suppress this warning, set "
                            "`suppress_unstable_features_warning = true` "
                            "in /home/owner/.codex/config.toml."
                        ),
                    },
                },
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "Review complete."},
                },
                {"type": "turn.completed"},
            ],
        )
    )
    token = ACTIVE_SESSION.set(session)
    try:
        result = run_external_agent(
            "Review only",
            config,
            runner=lambda command, **kw: subprocess.CompletedProcess(
                command, returncode, stream, ""
            ),
        )
        assert result.returncode == returncode
        assert result.events is not None
        assert result.events.failure_reason is None
        assert result.events.final_answer == "Review complete."
        assert result.stdout == stream  # Keep the notice in the native evidence.
        with session.connection() as connection:
            rows = connection.execute("SELECT status FROM coding_receipts").fetchall()
        assert [row["status"] for row in rows] == [expected_status]
    finally:
        ACTIVE_SESSION.reset(token)
        session.supervisor.close()


def test_parse_external_agent_jsonl_reports_explicit_failed_status() -> None:
    events = parse_external_agent_jsonl(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "status": "failed",
                    "error": {"message": "pytest failed"},
                },
            }
        )
    )

    assert events.failure_reason == "pytest failed"


def _mcp_event(status: str, *, tool: str = "edit_file", call_id: str = "call") -> dict:
    """Build representative offline events, not a reconstructed live stream."""
    return {
        "type": "item.started" if status == "in_progress" else "item.completed",
        "item": {
            "id": call_id,
            "type": "mcp_tool_call",
            "server": "repo_shared",
            "tool": tool,
            "status": status,
        },
    }


@pytest.mark.parametrize("returncode", [0, 7])
def test_mcp_recovery_preserves_receipts_and_native_exit(tmp_path, returncode):
    from ai_provider.external_agents import run_external_agent

    stream = [
        _mcp_event("failed"),
        _mcp_event("completed", call_id="call"),
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Done."}},
        {"type": "turn.completed"},
    ]
    raw = "\n".join(map(json.dumps, stream))
    result = run_external_agent(
        "fixture",
        ExternalAgentConfig(AccessMethod.CODEX_CLI, "codex", "fixture", tmp_path, 5),
        runner=lambda command, **kwargs: subprocess.CompletedProcess(command, returncode, raw, ""),
    )
    assert result.returncode == returncode
    assert result.stdout == raw
    assert result.events is not None
    assert result.events.failure_reason is None
    assert result.events.final_answer == "Done."
    assert result.events.tool_events == tuple(stream[:2])


@pytest.mark.parametrize(
    "tail",
    [
        [],
        [_mcp_event("completed", tool="read_file")],
        [_mcp_event("in_progress", call_id="call")],
        [_mcp_event("completed", call_id="call")],
        [_mcp_event("completed", call_id="call"), {"type": "turn.completed"}],
        [
            _mcp_event("completed", call_id="call"),
            {"type": "final_answer", "content": "Done."},
        ],
        [
            _mcp_event("completed", call_id="call"),
            _mcp_event("in_progress", call_id="unfinished"),
            {"type": "final_answer", "content": "Done."},
            {"type": "turn.completed"},
        ],
    ],
)
def test_mcp_recovery_requires_supported_completion(tail):
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, [_mcp_event("failed"), *tail])))
    assert events.failure_reason is not None


@pytest.mark.parametrize(
    "fatal",
    [
        {"type": "error", "message": "fatal"},
        {"type": "turn.failed", "error": {"message": "fatal"}},
        {"type": "item.completed", "item": {"type": "error", "message": "fatal"}},
        {"type": "item.failed", "item": {"type": "mcp_tool_call", "error": "fatal"}},
    ],
)
@pytest.mark.parametrize("fatal_first", [True, False])
def test_mcp_recovery_never_clears_fatal_errors(fatal, fatal_first):
    recovery = [_mcp_event("failed"), _mcp_event("completed", call_id="call")]
    stream = [fatal, *recovery] if fatal_first else [*recovery, fatal]
    stream += [{"type": "final_answer", "content": "Done."}, {"type": "turn.completed"}]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason == parse_external_agent_jsonl(json.dumps(fatal)).failure_reason


@pytest.mark.parametrize("missing", [None, "id", "server", "tool"])
def test_mcp_unresolved_failures_are_retained_as_separate_warnings(missing):
    # ADR-064: each unresolved MCP failure stays visible. Resolving a different
    # call cannot erase an independently unresolved one.
    first = _mcp_event("failed", call_id="first")
    second = _mcp_event("failed", call_id="second")
    first["item"]["arguments"] = {"path": "first.py"}
    second["item"]["arguments"] = {"path": "second.py"}
    first["item"]["error"] = {"message": "first failure"}
    second["item"]["error"] = {"message": "second failure"}
    unrelated = _mcp_event("completed", call_id="unrelated")
    unrelated["item"]["arguments"] = {"path": "third.py"}
    if missing:
        first["item"].pop(missing)
    finish = [{"type": "final_answer", "content": "Done."}, {"type": "turn.completed"}]
    stream = [first, second, unrelated, *finish]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason is None
    assert events.mcp_warnings == ("first failure", "second failure")
    assert events.tool_events == tuple(stream[:3])
    # Resolving the second call cannot erase the independently unresolved first.
    stream = [first, second, _mcp_event("completed", call_id="second"), *finish]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason is None
    assert events.mcp_warnings == ("first failure",)


def test_mcp_same_tool_retry_with_new_call_id_is_reported_as_warning():
    # ADR-064: a same-tool retry under a new call id cannot be proven by call
    # identity. When the run independently completed, that is a visible
    # warning, not a failed run.
    failure = _mcp_event("failed", call_id="first")
    success = _mcp_event("completed", call_id="different")
    for event in (failure, success):
        event["item"]["arguments"] = {"path": "same.py", "old_text": "a", "new_text": "b"}
    stream = [
        failure,
        success,
        {"type": "final_answer", "content": "Done."},
        {"type": "turn.completed"},
    ]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason is None
    assert events.mcp_warnings == ("mcp_tool_call",)
    assert events.final_answer == "Done."


@pytest.mark.parametrize("answer_position", ["before_failure", "before_recovery", "after_recovery"])
def test_mcp_recovery_requires_fresh_answer(answer_position):
    answer = {"type": "final_answer", "content": "Done."}
    failure = _mcp_event("failed")
    success = _mcp_event("completed")
    streams = {
        "before_failure": [answer, failure, success],
        "before_recovery": [failure, answer, success],
        "after_recovery": [failure, success, answer],
    }
    stream = [*streams[answer_position], {"type": "turn.completed"}]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.final_answer == "Done."
    assert (events.failure_reason is None) == (answer_position == "after_recovery")
    assert events.tool_events == (failure, success)


@pytest.mark.parametrize("call_id", [None, "", 7])
@pytest.mark.parametrize("event_type", ["item.started", "item.updated"])
@pytest.mark.parametrize("later_success", [False, True])
def test_unidentified_unfinished_mcp_call_remains_unverified(call_id, event_type, later_success):
    unfinished = _mcp_event("in_progress")
    unfinished["type"] = event_type
    if call_id is None:
        unfinished["item"].pop("id")
    else:
        unfinished["item"]["id"] = call_id
    stream = [unfinished]
    if later_success:
        stream.append(_mcp_event("completed"))
    stream += [{"type": "final_answer", "content": "Done."}, {"type": "turn.completed"}]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason == "incomplete MCP tool call"
    assert events.final_answer == "Done."
    assert events.tool_events == tuple(stream[:-2])


def test_mcp_each_identified_failure_requires_its_own_recovery():
    failures = [_mcp_event("failed", call_id=name) for name in ("first", "second")]
    successes = [_mcp_event("completed", call_id=name) for name in ("first", "second")]
    stream = [
        *failures,
        *successes,
        {"type": "final_answer", "content": "Done."},
        {"type": "turn.completed"},
    ]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason is None
    assert events.tool_events == tuple(stream[:4])


def _unresolved_failure() -> dict:
    """An MCP failure whose call identity the stream never establishes."""
    failure = _mcp_event("failed")
    failure["item"].pop("id")
    failure["item"]["error"] = {"message": "unresolved failure"}
    return failure


def test_mcp_unresolved_identity_failure_in_a_completed_run_is_a_warning():
    stream = [
        _unresolved_failure(),
        {"type": "final_answer", "content": "Done."},
        {"type": "turn.completed"},
    ]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason is None
    assert events.mcp_warnings == ("unresolved failure",)
    assert events.final_answer == "Done."


def test_mcp_identified_failure_without_retry_in_a_completed_run_is_a_warning():
    # ADR-064 covers every MCP failure that call identity cannot resolve,
    # including one the agent never retried.
    stream = [
        _mcp_event("failed", call_id="only"),
        {"type": "final_answer", "content": "Done."},
        {"type": "turn.completed"},
    ]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason is None
    assert events.mcp_warnings == ("mcp_tool_call",)


@pytest.mark.parametrize(
    "tail,expected",
    [
        ([{"type": "final_answer", "content": "Done."}], "unresolved failure"),
        ([{"type": "turn.completed"}], "unresolved failure"),
        (
            [
                {"type": "final_answer", "content": "Done."},
                {"type": "turn.completed"},
                {"type": "error", "message": "fatal"},
            ],
            "fatal",
        ),
    ],
)
def test_mcp_unresolved_failure_still_fails_without_independent_completion(tail, expected):
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, [_unresolved_failure(), *tail])))
    assert events.failure_reason == expected
    assert events.mcp_warnings == ()


def test_mcp_unresolved_failure_with_an_unfinished_call_stays_incomplete():
    unfinished = _mcp_event("in_progress")
    unfinished["type"] = "item.started"
    unfinished["item"].pop("id")
    stream = [
        _unresolved_failure(),
        unfinished,
        {"type": "final_answer", "content": "Done."},
        {"type": "turn.completed"},
    ]
    events = parse_external_agent_jsonl("\n".join(map(json.dumps, stream)))
    assert events.failure_reason == "unresolved failure"
    assert events.mcp_warnings == ()


def test_external_agent_progress_line_summarizes_json_events() -> None:
    assert _external_agent_progress_line('{"type":"response.reasoning_summary.delta"}\n') is None
    assert (
        _external_agent_progress_line('{"type":"final_answer","content":"done"}\n')
        == "external_agent_activity: final_answer - done"
    )
    assert (
        _external_agent_progress_line(
            '{"type":"item.completed","item":{"type":"agent_message",'
            '"text":"Inspecting repository state before making a decision."}}\n'
        )
        == "external_agent_activity: item.completed - "
        "Inspecting repository state before making a decision."
    )
    assert (
        _external_agent_progress_line(
            '{"type":"item.started","item":{"type":"command_execution",'
            '"command":"git status --short","status":"in_progress"}}\n'
        )
        == "external_agent_activity: command_execution in_progress - command: git status --short"
    )
    assert (
        _external_agent_progress_line(
            '{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}\n'
        )
        == 'external_agent_activity: usage - {"input_tokens": 12, "output_tokens": 3}'
    )
    assert _external_agent_progress_line("plain progress\n") == "external_agent_activity: stdout"


def test_external_agent_stderr_progress_suppresses_noisy_codex_model_refresh() -> None:
    line = (
        "2026-09-28T08:57:23.532192Z ERROR codex_models_manager::manager: "
        "failed to refresh available models: unknown variant `max`"
    )

    assert _external_agent_stderr_progress_line(line) is None


def test_external_agent_progress_line_keeps_useful_command_detail() -> None:
    long_command = (
        '"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '
        '"Get-Content -Path packages\\ai_provider\\src\\ai_provider\\repo_coding_assistant.py '
        '| Select-Object -Skip 1380 -First 110"'
    )

    progress = _external_agent_progress_line(
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "type": "command_execution",
                    "command": long_command,
                    "status": "in_progress",
                },
            }
        )
        + "\n"
    )

    assert progress is not None
    assert "repo_coding_assistant.py" in progress
    assert len(progress) > 180


def test_parse_codex_plugin_list_summarizes_marketplace_rows() -> None:
    summary = parse_codex_plugin_list(
        "\n".join(
            [
                "Marketplace `openai-curated`",
                "C:\\codex\\.tmp\\plugins\\.agents\\plugins\\marketplace.json",
                "",
                "PLUGIN                 STATUS         VERSION  PATH",
                "linear@openai-curated  not installed           C:\\codex\\plugins\\linear",
                "github@openai-curated  installed, enabled  1.2.3    C:\\codex\\plugins\\github",
            ]
        )
    )

    assert summary.marketplaces == ("openai-curated",)
    assert summary.available_count == 2
    assert summary.installed_count == 1
    assert summary.plugins[0].name == "linear@openai-curated"
    assert summary.plugins[0].status == "not installed"
    assert summary.plugins[0].version is None
    assert summary.plugins[1].name == "github@openai-curated"
    assert summary.plugins[1].status == "installed, enabled"
    assert summary.plugins[1].version == "1.2.3"


def test_build_codex_plugin_command_requires_exact_selector() -> None:
    command = build_codex_plugin_command("codex", "add", "github@openai-curated")

    assert command == ("codex", "plugin", "add", "github@openai-curated")


def test_validate_codex_plugin_selector_rejects_missing_marketplace() -> None:
    try:
        validate_codex_plugin_selector("github")
    except ValueError as exc:
        assert "PLUGIN@MARKETPLACE" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("selector without marketplace should fail")


def test_codex_plugin_status_by_name_reports_requested_selectors() -> None:
    summary = parse_codex_plugin_list(
        "\n".join(
            [
                "Marketplace `openai-curated`",
                "PLUGIN                 STATUS         VERSION  PATH",
                "github@openai-curated  installed, enabled  1.2.3    C:\\codex\\plugins\\github",
            ]
        )
    )

    status = codex_plugin_status_by_name(
        summary,
        ("github@openai-curated", "missing@openai-curated"),
    )

    assert status["github@openai-curated"]["status"] == "installed, enabled"
    assert status["missing@openai-curated"]["status"] == "missing_from_plugin_list"


def test_run_diagnostic_command_timeout(monkeypatch, tmp_path):
    def mock_run(*_, **__):
        raise subprocess.TimeoutExpired(
            cmd=[PRIVATE_COMMAND, PRIVATE_ARGUMENT],
            timeout=1,
            output=b"private_output",
            stderr=b"private_stderr",
        )

    monkeypatch.setattr("ai_provider.external_agents.run_owned_diagnostic", mock_run)
    result = run_diagnostic_command(PRIVATE_COMMAND, PRIVATE_ARGUMENT, timeout_seconds=1)
    assert not result["ok"]
    assert result["returncode"] is None
    assert result["stdout"] == ""
    assert result["stderr"] == "Diagnostic command timed out."
    assert set(result.keys()) == {"ok", "returncode", "stdout", "stderr"}
    expected = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "stderr": "Diagnostic command timed out.",
    }
    assert result == expected
    # Ensure no private data leaked
    assert "private_output" not in str(result)
    assert "private_stderr" not in str(result)
    assert PRIVATE_COMMAND not in str(result)
    assert PRIVATE_ARGUMENT not in str(result)


def test_run_diagnostic_command_not_found(monkeypatch, tmp_path):
    def mock_run(*_, **__):
        raise OSError(1, "private_error", "private_file")

    monkeypatch.setattr("ai_provider.external_agents.run_owned_diagnostic", mock_run)
    result = run_diagnostic_command(PRIVATE_COMMAND, PRIVATE_ARGUMENT, timeout_seconds=1)
    assert not result["ok"]
    assert result["returncode"] is None
    assert result["stdout"] == ""
    assert result["stderr"] == "Diagnostic command could not be executed."
    assert set(result.keys()) == {"ok", "returncode", "stdout", "stderr"}
    expected = {
        "ok": False,
        "returncode": None,
        "stdout": "",
        "stderr": "Diagnostic command could not be executed.",
    }
    assert result == expected
    # Ensure no private data leaked
    assert "private_error" not in str(result)
    assert "private_file" not in str(result)
    assert PRIVATE_COMMAND not in str(result)
    assert PRIVATE_ARGUMENT not in str(result)


def test_run_diagnostic_command_success(tmp_path):
    result = run_diagnostic_command(sys.executable, "-c", 'print("hello")', timeout_seconds=5)
    assert result["ok"]
    assert result["stdout"] == "hello"
    assert set(result.keys()) == {"ok", "returncode", "stdout", "stderr"}


@pytest.mark.parametrize("returncode", [0, 7])
def test_run_diagnostic_command_completed_process(returncode: int, monkeypatch):
    fake_output = "   hello padded  \n"
    fake_error = "   err padded\n"
    completed = subprocess.CompletedProcess(
        args=[PRIVATE_COMMAND, PRIVATE_ARGUMENT],
        returncode=returncode,
        stdout=fake_output,
        stderr=fake_error,
    )
    monkeypatch.setattr(
        "ai_provider.external_agents.run_owned_diagnostic", lambda *args, **kwargs: completed
    )
    result = run_diagnostic_command(PRIVATE_COMMAND, PRIVATE_ARGUMENT)
    assert result["ok"] == (returncode == 0)
    assert result["returncode"] == returncode
    assert result["stdout"] == fake_output.strip()
    assert result["stderr"] == fake_error.strip()
    assert set(result.keys()) == {"ok", "returncode", "stdout", "stderr"}
    expected = {
        "ok": (returncode == 0),
        "returncode": returncode,
        "stdout": fake_output.strip(),
        "stderr": fake_error.strip(),
    }
    assert result == expected
    # Ensure no private data leaked
    assert "private_arg" not in str(result)
    assert PRIVATE_COMMAND not in str(result)
    assert PRIVATE_ARGUMENT not in str(result)
