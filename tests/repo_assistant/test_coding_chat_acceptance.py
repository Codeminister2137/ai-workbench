"""Synthetic comparison preparation remains deterministic and requires live opt-in."""

import importlib.util
import json
from pathlib import Path

import pytest


def script():
    path = Path(__file__).resolve().parents[2] / "scripts/coding-chat-acceptance.py"
    spec = importlib.util.spec_from_file_location("coding_acceptance", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "options",
    [
        ["--restart"],
        ["--attended"],
        ["--attended", "--conversation", "--arm", "reduced"],
        ["--attended", "--live", "--arm", "reduced"],
    ],
)
def test_invalid_attended_or_restart_mode_refuses_before_fixture_creation(monkeypatch, options):
    import io

    acceptance = script()
    monkeypatch.setattr("sys.argv", ["acceptance", *options])
    monkeypatch.setattr("sys.stdin", io.StringIO())
    monkeypatch.setattr(
        acceptance.tempfile, "mkdtemp", lambda **kwargs: pytest.fail("refuse before setup")
    )
    with pytest.raises(SystemExit, match="2"):
        acceptance.main()


def test_attended_console_keeps_prompt_visible_and_in_local_evidence():
    import io

    acceptance = script()
    evidence, console = io.StringIO(), io.StringIO()
    output = acceptance.LoggedConsole(evidence, console)
    message = "Exact operation\nReply /approve fresh-ID yes or no"
    assert output.write(message) == len(message)
    output.flush()
    assert evidence.getvalue() == console.getvalue()
    assert "Reply /approve fresh-ID" in console.getvalue()
    evidence.close()
    console.close()
    output.flush()


@pytest.mark.parametrize("outcome", ["setup", "timeout"])
def test_attended_live_setup_preserves_owner_input_and_uses_interactive_policy(
    tmp_path, monkeypatch, capsys, outcome
):
    import builtins
    import io
    import sys

    class OwnerTerminal(io.StringIO):
        def isatty(self):
            return True

    acceptance = script()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    owner_terminal = OwnerTerminal()
    monkeypatch.setattr(sys, "stdin", owner_terminal)
    original_input = builtins.input
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "acceptance",
            "--attended",
            "--arm",
            "reduced",
            "--live",
            "--codex-command",
            "synthetic-no-account",
            "--effective-settings",
            str(settings),
        ],
    )

    def setup_only(arguments):
        assert sys.stdin is owner_terminal
        assert builtins.input is original_input
        assert arguments[arguments.index("--approval-policy") + 1] == "interactive"
        print("visible exact approval prompt")
        (fixture / "reduced/range_tools.py").write_text(acceptance.CASES["boundary"].reference)
        return 0

    terminals = []
    if outcome == "setup":
        monkeypatch.setattr(acceptance.cli, "main", setup_only)
        monkeypatch.setattr(
            acceptance, "run_external_agent", lambda *args, **kwargs: pytest.fail("setup test only")
        )
    else:
        import subprocess

        from ai_agent.coding_chat_input import CodingChatInput

        class ControlledTerminal(CodingChatInput):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                terminals.append(self)

            def in_flight(self, poll=None):
                return super().in_flight(lambda: None)

        monkeypatch.setattr(acceptance.coding_chat_cli, "CodingChatInput", ControlledTerminal)

        def timeout(prompt, config, **kwargs):
            assert terminals[0].thread is not None
            terminals[0].feed("Queued correction must not execute after timeout")
            raise subprocess.TimeoutExpired(
                ["synthetic-no-account", "-p", "synthetic-private-history" * 1000],
                120,
                output=b'{"type":"synthetic.partial"}\n',
                stderr=b"synthetic timeout detail",
            )

        monkeypatch.setattr(acceptance, "run_external_agent", timeout)
    assert acceptance.main() == 1
    output = capsys.readouterr().out
    assert ("visible exact approval prompt" if outcome == "setup" else "timed out") in output
    record = json.loads(
        next((tmp_path / "artifacts/coding-chat-acceptance").glob("*/results.json")).read_text()
    )
    assert record["live_calls"] == (0 if outcome == "setup" else 1)
    assert record["arms"][0]["attended_arbitration_verified"] is False
    assert record["arms"][0]["client_operations_permitted"] is False
    assert record["arms"][0]["tests_passed"] is False
    if outcome == "setup":
        assert (
            "visible exact approval prompt"
            in next(
                (tmp_path / "artifacts/coding-chat-acceptance").glob("*/reduced.log")
            ).read_text()
        )
    else:
        assert terminals[0].closed and terminals[0].thread is None
        assert "synthetic-private-history" not in output
        from ai_agent.coding_chat import CodingChatController
        from ai_provider.chat_transcripts import SQLiteChatTranscriptStore

        store = SQLiteChatTranscriptStore(fixture / "reduced/session.sqlite3")
        session = store.latest_session(repo_root=fixture / "reduced")
        assert session is not None
        history = CodingChatController(
            store,
            session.session_id,
            fixture / "reduced",
            "public_or_low_risk",
            history_budget_chars=4000,
        ).history(current_text="Inspect the partial effects")
        assert len(history) + len("Inspect the partial effects") <= 4000
        assert "timed out after 120 seconds" in history
        artifact = tmp_path / "artifacts/coding-chat-acceptance" / fixture.name
        assert (
            artifact / "reduced.turn-1.events.jsonl"
        ).read_text() == '{"type":"synthetic.partial"}\n'
        assert (artifact / "reduced.turn-1.stderr.log").read_text() == "synthetic timeout detail"


@pytest.mark.parametrize("case_name", tuple(script().CASES))
def test_pair_preparation_has_identical_code_and_owner_history_without_inference(
    tmp_path, monkeypatch, case_name
):
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore

    acceptance = script()
    monkeypatch.setattr(
        acceptance,
        "run_external_agent",
        lambda *args, **kwargs: pytest.fail("offline preparation must not call models"),
    )
    case = acceptance.CASES[case_name]
    full_id, full_chars = acceptance.prepare(tmp_path / "full", 0, case_name)
    reduced_id, reduced_chars = acceptance.prepare(tmp_path / "reduced", 4000, case_name)
    assert reduced_chars == 4000 < full_chars
    for filename in (case.module, f"test_{case.module}", "AGENTS.md", "catalog.toml"):
        assert (tmp_path / "full" / filename).read_bytes() == (
            tmp_path / "reduced" / filename
        ).read_bytes()
    full = SQLiteChatTranscriptStore(tmp_path / "full/session.sqlite3").list_messages(full_id)
    reduced = SQLiteChatTranscriptStore(tmp_path / "reduced/session.sqlite3").list_messages(
        reduced_id
    )
    assert [(m.role, m.content) for m in full] == [(m.role, m.content) for m in reduced]


@pytest.mark.parametrize("case_name", tuple(script().CASES))
def test_case_host_tests_detect_original_bug_and_accept_reference(tmp_path, case_name):
    import subprocess
    import sys

    acceptance = script()
    case = acceptance.CASES[case_name]
    workspace = tmp_path / case_name
    acceptance.prepare(workspace, 4000, case_name)
    tests_before = (workspace / f"test_{case.module}").read_bytes()

    def validate():
        return subprocess.run(
            [sys.executable, f"test_{case.module}"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )

    assert validate().returncode != 0
    (workspace / case.module).write_text(case.reference, encoding="utf-8")
    corrected = validate()
    assert corrected.returncode == 0, corrected.stdout + corrected.stderr
    assert (workspace / f"test_{case.module}").read_bytes() == tests_before


def test_live_requires_explicit_effective_model_and_reasoning_receipt(tmp_path, monkeypatch):
    acceptance = script()
    receipt = tmp_path / "settings.json"
    receipt.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "low"}))
    monkeypatch.setattr(
        "sys.argv",
        ["acceptance", "--live", "--codex-command", "codex", "--effective-settings", str(receipt)],
    )
    monkeypatch.setattr(
        acceptance,
        "prepare",
        lambda *args: pytest.fail("wrong model must refuse before setup or inference"),
    )
    with pytest.raises(SystemExit, match="2"):
        acceptance.main()


def test_live_flag_without_preflight_refuses_before_setup(monkeypatch):
    acceptance = script()
    monkeypatch.setattr("sys.argv", ["acceptance", "--live"])
    monkeypatch.setattr(acceptance, "prepare", lambda *args: pytest.fail("preflight required"))
    with pytest.raises(SystemExit, match="2"):
        acceptance.main()


def test_acceptance_command_preserves_token_forwarding_and_explicit_settings():
    acceptance = script()
    command = (
        "codex",
        "-c",
        'mcp_servers.repo_shared.env_vars=["AI_SCOPED_TOKEN"]',
        "exec",
        "--model",
        "gpt-6.1-sol",
        "--sandbox",
        "read-only",
        "-",
    )
    actual = acceptance.comparison_command(command)
    value = next(v for v in actual if v.startswith("mcp_servers.repo_shared.env_vars="))
    assert json.loads(value.split("=", 1)[1]) == ["AI_SCOPED_TOKEN", "PYTHONPATH"]
    assert "model_reasoning_effort=medium" in actual
    assert "--ignore-user-config" in actual
    assert actual[actual.index("--sandbox") + 1] == "read-only"


@pytest.mark.parametrize("client_status", [0, 1])
def test_failed_arm_stops_pair_and_restores_terminal_state(
    tmp_path, monkeypatch, capsys, client_status
):
    import builtins
    import io
    import sys

    acceptance = script()
    receipt = tmp_path / "settings.json"
    receipt.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(
        "sys.argv",
        ["acceptance", "--live", "--codex-command", "codex", "--effective-settings", str(receipt)],
    )
    calls = []

    class ControllingTerminal(io.StringIO):
        def isatty(self):
            return True

    original = ControllingTerminal()
    monkeypatch.setattr(sys, "stdin", original)
    original_input = builtins.input

    def failed_cli(arguments):
        assert not sys.stdin.isatty()
        assert builtins.input("You> ") == "/exit"
        calls.append(arguments)
        return client_status

    monkeypatch.setattr(acceptance.cli, "main", failed_cli)
    assert acceptance.main() == 1
    assert len(calls) == 1
    assert sys.stdin is original
    assert builtins.input is original_input
    record = json.loads(capsys.readouterr().out)
    assert record["stopped_after_failure"]
    assert len(record["arms"]) == 1
    assert record["arms"][0]["status"] == client_status
    assert not record["arms"][0]["tests_passed"]
    assert not record["parity_established"]


@pytest.mark.parametrize("protected_name", ["AGENTS.md", "catalog.toml"])
def test_model_cannot_pass_by_changing_protected_instructions_or_routing(
    tmp_path, monkeypatch, capsys, protected_name
):
    acceptance = script()
    receipt = tmp_path / "settings.json"
    receipt.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(
        "sys.argv",
        ["acceptance", "--live", "--codex-command", "codex", "--effective-settings", str(receipt)],
    )

    def tamper(arguments):
        workspace = fixture / "full"
        (workspace / "range_tools.py").write_text(acceptance.CASES["boundary"].reference)
        (workspace / protected_name).write_text("unrequested change")
        return 0

    monkeypatch.setattr(acceptance.cli, "main", tamper)
    assert acceptance.main() == 1
    record = json.loads(capsys.readouterr().out)
    assert len(record["arms"]) == 1
    assert record["arms"][0]["status"] == 0
    assert record["arms"][0]["tests_unchanged"]
    assert not record["arms"][0]["protected_files_unchanged"]
    assert not record["arms"][0]["tests_passed"]
    assert record["stopped_after_failure"]
    assert not record["parity_established"]


@pytest.mark.parametrize("reasoning", ["medium", "low"])
def test_settings_preflight_reads_config_without_starting_a_model_turn(reasoning, monkeypatch):
    import io

    acceptance = script()
    processes = []

    class Input(io.StringIO):
        def close(self):
            self.recorded = self.getvalue()
            super().close()

    class Process:
        def __init__(self, command, **kwargs):
            assert "model_reasoning_effort=medium" in command
            assert "--no-daemon" in command
            self.stdin = Input()
            self.stdout = io.StringIO(
                json.dumps({"id": 1, "result": {"userAgent": "fixture-client"}})
                + "\n"
                + json.dumps(
                    {
                        "id": 2,
                        "result": {
                            "config": {
                                "model": "gpt-6.1-sol",
                                "model_reasoning_effort": reasoning,
                                "secret": "must-not-persist",
                            }
                        },
                    }
                )
                + "\n"
            )
            self.terminated = False
            processes.append(self)

        def terminate(self):
            self.terminated = True

        def wait(self, **kwargs):
            return 0

    monkeypatch.setattr(acceptance.subprocess, "Popen", Process)
    if reasoning == "medium":
        record = acceptance.effective_settings(Path("codex.exe"))
        assert record["inference_requests"] == 0
        assert "secret" not in record
    else:
        with pytest.raises(ValueError, match="did not apply"):
            acceptance.effective_settings(Path("codex.exe"))
    process = processes[0]
    methods = [json.loads(line)["method"] for line in process.stdin.recorded.splitlines()]
    assert methods == ["initialize", "initialized", "config/read"]
    assert process.terminated
    assert process.stdin.closed and process.stdout.closed


@pytest.mark.parametrize(("outer_deadline", "expected"), [(150, 150), (500, 220)])
def test_live_invocation_caps_overall_deadline_and_preserves_shorter_bound(
    tmp_path, monkeypatch, capsys, outer_deadline, expected
):
    from types import SimpleNamespace

    acceptance = script()
    receipt = tmp_path / "settings.json"
    receipt.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(acceptance.time, "perf_counter", lambda: 100)
    monkeypatch.setattr(
        "sys.argv",
        ["acceptance", "--live", "--codex-command", "codex", "--effective-settings", str(receipt)],
    )
    deadlines = []

    def fake_execute(prompt, config, **kwargs):
        deadlines.append(kwargs["deadline"])
        return SimpleNamespace(stdout="", stderr="synthetic failure", events=None)

    def failed_cli(arguments):
        acceptance.cli._run_external_agent(
            "synthetic",
            SimpleNamespace(
                model="gpt-6.1-sol",
                cwd=fixture / "full",
                shared_task_id="synthetic-task",
                shared_run_id="synthetic-run",
            ),
            deadline=outer_deadline,
        )
        return 1

    monkeypatch.setattr(acceptance, "run_external_agent", fake_execute)
    monkeypatch.setattr(acceptance.cli, "main", failed_cli)
    assert acceptance.main() == 1
    assert deadlines == [expected]
    record = json.loads(capsys.readouterr().out)
    assert record["live_calls"] == 1
    assert record["stopped_after_failure"]


def test_conversation_refuses_two_arms_before_setup(monkeypatch):
    acceptance = script()
    monkeypatch.setattr("sys.argv", ["acceptance", "--conversation"])
    monkeypatch.setattr(
        acceptance.tempfile, "mkdtemp", lambda **kwargs: pytest.fail("refuse before setup")
    )
    with pytest.raises(SystemExit, match="2"):
        acceptance.main()


@pytest.mark.parametrize(
    "violation",
    ["command", "network", "native_write", "other_tool", "other_path", "unknown_events"],
)
def test_correct_source_cannot_hide_a_forbidden_client_operation(
    tmp_path, monkeypatch, capsys, violation
):
    from ai_provider.external_agents import ExternalAgentResult, parse_external_agent_jsonl

    acceptance = script()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(
        "sys.argv",
        [
            "acceptance",
            "--live",
            "--codex-command",
            "synthetic-no-account",
            "--effective-settings",
            str(settings),
        ],
    )
    calls = []

    def synthetic_turn(prompt, config, **kwargs):
        calls.append(config)
        (config.cwd / "range_tools.py").write_text(acceptance.CASES["boundary"].reference)
        item = {
            "command": {"type": "command_execution", "command": "forbidden"},
            "network": {"type": "web_search", "query": "forbidden"},
            "native_write": {"type": "file_change", "changes": []},
            "other_tool": {
                "type": "mcp_tool_call",
                "tool": "process_start",
                "arguments": {},
            },
            "other_path": {
                "type": "mcp_tool_call",
                "tool": "edit_file",
                "arguments": {"path": "AGENTS.md"},
            },
            "unknown_events": {},
        }[violation]
        raw = json.dumps({"type": "item.completed", "item": item})
        return ExternalAgentResult(
            (),
            0,
            raw,
            "",
            events=None if violation == "unknown_events" else parse_external_agent_jsonl(raw),
        )

    monkeypatch.setattr(acceptance, "run_external_agent", synthetic_turn)
    assert acceptance.main() == 1
    record = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert record["stopped_after_failure"]
    arm = record["arms"][0]
    assert arm["host_tests_passed"] is True
    assert arm["client_operations_permitted"] is False
    assert arm["tests_passed"] is False


@pytest.mark.parametrize(
    ("case_name", "outcome"),
    [
        ("boundary", outcome)
        for outcome in (
            "legitimate",
            "claim_only",
            "edit_before_read",
            "transient_write",
            "extra_file",
            "wrong_read",
        )
    ]
    + [("authenticated_redirect", "legitimate"), ("path_containment", "legitimate")],
)
def test_actual_host_receipts_and_fixture_paths_control_acceptance(
    tmp_path, monkeypatch, capsys, case_name, outcome
):
    import subprocess

    from ai_agent.http_proxy import HttpMcpConnection
    from ai_provider.external_agents import run_external_agent

    acceptance = script()
    case = acceptance.CASES[case_name]
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(
        "sys.argv",
        [
            "acceptance",
            "--live",
            "--arm",
            "reduced",
            "--case",
            case_name,
            "--codex-command",
            "synthetic-no-account",
            "--effective-settings",
            str(settings),
        ],
    )
    original_runs = []

    def synthetic_client(prompt, config, **kwargs):
        original_runs.append(config.shared_run_id)

        def runner(command, **options):
            overrides = dict(
                value.split("=", 1) for value in command if value.startswith("mcp_servers.")
            )
            proxy_args = json.loads(overrides["mcp_servers.repo_shared.args"])
            connection = HttpMcpConnection(
                proxy_args[proxy_args.index("--proxy-url") + 1],
                options["env"][proxy_args[proxy_args.index("--proxy-token-env") + 1]],
            )
            connection.send({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            connection.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            events = []

            def call(tool, arguments, *, report=True):
                response = connection.send(
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": tool, "arguments": arguments},
                    }
                )
                assert response is not None and not response["result"]["isError"]
                if report:
                    events.append(
                        {
                            "type": "item.completed",
                            "item": {
                                "type": "mcp_tool_call",
                                "tool": tool,
                                "arguments": arguments,
                                "status": "completed",
                                "error": None,
                                "result": response["result"],
                            },
                        }
                    )

            source = fixture / "reduced" / case.module
            edit = {"path": case.module, "new_text": case.reference}
            try:
                if outcome == "claim_only":
                    source.write_text(edit["new_text"])
                    for tool, arguments in [
                        ("read_file", {"path": case.module}),
                        ("edit_file", edit),
                    ]:
                        events.append(
                            {
                                "type": "item.completed",
                                "item": {
                                    "type": "mcp_tool_call",
                                    "tool": tool,
                                    "arguments": arguments,
                                },
                            }
                        )
                else:
                    if outcome == "edit_before_read":
                        call("edit_file", edit)
                    call(
                        "read_file",
                        {"path": "AGENTS.md" if outcome == "wrong_read" else case.module},
                    )
                    if outcome != "edit_before_read":
                        call("edit_file", edit)
                    if outcome == "transient_write":
                        original = (fixture / "reduced/AGENTS.md").read_text()
                        call(
                            "edit_file", {"path": "AGENTS.md", "new_text": "tampered"}, report=False
                        )
                        call("edit_file", {"path": "AGENTS.md", "new_text": original}, report=False)
                    if outcome == "extra_file":
                        (fixture / "reduced/unrequested.txt").write_text("unrequested effect")
                events.append({"type": "final_answer", "content": "Claimed success"})
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "\n".join(json.dumps(event) for event in events),
                    "",
                )
            finally:
                connection.close()

        kwargs["runner"] = runner
        return run_external_agent(prompt, config, **kwargs)

    monkeypatch.setattr(acceptance, "run_external_agent", synthetic_client)
    assert acceptance.main() == (0 if outcome == "legitimate" else 1)
    record = json.loads(capsys.readouterr().out)
    arm = record["arms"][0]
    assert arm["client_operations_permitted"]
    assert arm["tests_passed"] == (outcome == "legitimate")
    assert arm["fixture_paths_unchanged"] == (outcome != "extra_file")
    assert arm["host_read_then_edit"] == (outcome in {"legitimate", "extra_file"})
    if outcome != "claim_only":
        assert arm["host_operations"][0][0]["run_id"] != original_runs[0]


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "success_absolute",
        "success_restart",
        "planning_edit",
        "planning_failed",
        "planning_hidden_write",
        "planning_read_denied",
        "planning_extra_file",
    ],
)
@pytest.mark.parametrize("restart", [False, True])
def test_actual_cli_conversation_retains_plan_and_stops_on_first_phase_violation(
    tmp_path, monkeypatch, capsys, outcome, restart
):
    from ai_provider.chat_transcripts import SQLiteChatTranscriptStore
    from ai_provider.external_agents import ExternalAgentResult, parse_external_agent_jsonl

    acceptance = script()
    receipt = tmp_path / "settings.json"
    receipt.write_text(json.dumps({"model": "gpt-6.1-sol", "reasoning": "medium"}))
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    monkeypatch.setattr(acceptance, "__file__", str(tmp_path / "scripts/acceptance.py"))
    monkeypatch.setattr(acceptance.tempfile, "mkdtemp", lambda **kwargs: str(fixture))
    monkeypatch.setattr(
        "sys.argv",
        [
            "acceptance",
            "--live",
            "--conversation",
            "--arm",
            "reduced",
            "--codex-command",
            "synthetic-no-account",
            "--effective-settings",
            str(receipt),
        ]
        + (["--restart"] if restart or outcome == "success_restart" else []),
    )
    prompts, configs = [], []
    successful = outcome in {"success", "success_absolute", "success_restart"}

    def synthetic_turn(prompt, config, **kwargs):
        prompts.append(prompt)
        configs.append(config)
        from ai_agent.contracts import ToolCall
        from ai_agent.permissions import PermissionManager, PermissionPolicy
        from ai_agent.shared_approvals import scoped_registry
        from ai_agent.tool_profiles import shared_tool_registry
        from ai_agent.tools import ToolContext
        from ai_provider.coding_sessions import ACTIVE_SESSION

        session = ACTIVE_SESSION.get()
        assert session is not None
        registry = session.observe_registry(
            scoped_registry(
                shared_tool_registry("coding"),
                PermissionManager(PermissionPolicy.workspace_write()),
                config.cwd,
                config.shared_task_id,
                config.shared_run_id,
            ),
            operation_prefix=f"shared:{config.shared_task_id}:{config.shared_run_id}:",
        )
        path = (
            str(config.cwd / "range_tools.py")
            if outcome == "success_absolute"
            else "range_tools.py"
        )
        read_result = registry.execute(
            ToolCall(
                "read_file", {"path": "missing.py" if outcome == "planning_read_denied" else path}
            ),
            ToolContext(config.cwd),
        )
        if outcome == "planning_extra_file":
            (config.cwd / "unrequested.txt").write_text("unrequested planning effect")
        edit_arguments = None
        if len(prompts) == 2 or outcome in {"planning_edit", "planning_hidden_write"}:
            new_text = (
                acceptance.CASES["boundary"].source
                if outcome == "planning_hidden_write"
                else acceptance.CASES["boundary"].reference
            )
            edit_arguments = {"path": path, "new_text": new_text}
            result = registry.execute(
                ToolCall("edit_file", edit_arguments),
                ToolContext(config.cwd),
            )
            assert not result.is_error
        raw = (
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "tool": "edit_file" if outcome == "planning_hidden_write" else "read_file",
                        "arguments": {"path": path},
                        "status": "completed",
                        "error": None,
                        "result": {"isError": read_result.is_error},
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "final_answer",
                    "content": "Synthetic actual plan" if len(prompts) == 1 else "done",
                }
            )
            + "\n"
            + json.dumps({"type": "turn.completed", "usage": {"input_tokens": len(prompts) * 10}})
        )
        if edit_arguments is not None:
            raw += "\n" + json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "mcp_tool_call",
                        "tool": "edit_file",
                        "arguments": edit_arguments,
                        "status": "completed",
                        "error": None,
                    },
                }
            )
        return ExternalAgentResult(
            ("synthetic-no-account",),
            1 if outcome == "planning_failed" else 0,
            raw,
            "",
            events=parse_external_agent_jsonl(raw),
        )

    monkeypatch.setattr(acceptance, "run_external_agent", synthetic_turn)
    assert acceptance.main() == (0 if successful else 1)
    record = json.loads(capsys.readouterr().out)
    arm = record["arms"][0]
    assert arm["cli_invocations"] == (
        2 if successful and (restart or outcome == "success_restart") else 1
    )
    assert arm["usage_scope"] == "last_turn"
    assert arm["usage"]["input_tokens"] == len(prompts) * 10
    assert arm["planning_files_unchanged"] == (
        outcome not in {"planning_edit", "planning_extra_file"}
    )
    assert arm["planning_tools_read_only"] == (
        outcome not in {"planning_hidden_write", "planning_edit"}
    )
    assert arm["planning_source_read"] == (
        outcome not in {"planning_hidden_write", "planning_read_denied"}
    )
    assert record["live_calls"] == (2 if successful else 1)
    assert len(arm["turns"]) == len(prompts)
    store = SQLiteChatTranscriptStore(fixture / "reduced/session.sqlite3")
    session = store.latest_session(repo_root=fixture / "reduced")
    assert session is not None
    messages = store.list_messages(session.session_id)
    if successful:
        assert "Synthetic actual plan" in prompts[1]
        assert "Wait for the owner's follow-up" in prompts[1]
        assert acceptance.PROMPT in prompts[1]
        assert '"report_shortened": true' in prompts[1]
        assert configs[0].shared_task_id == configs[1].shared_task_id == session.session_id
        assert configs[0].shared_run_id != configs[1].shared_run_id
        assert all(config.shared_tool_profile == "coding" for config in configs)
        assert messages[-1].metadata is not None
        assert messages[-1].metadata["reply_to"] == messages[-2].message_id
        assert arm["tests_passed"] and arm["protected_files_unchanged"]
        assert arm["host_read_then_edit"] and arm["host_operations_permitted"]
    else:
        assert record["stopped_after_failure"]
        assert not arm["tests_passed"]
        assert not any(message.content == acceptance.PROMPT for message in messages)
