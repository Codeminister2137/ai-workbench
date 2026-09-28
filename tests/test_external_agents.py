import json
from pathlib import Path

from ai_orchestrator import AccessMethod
from ai_provider.external_agents import (
    ExternalAgentConfig,
    _external_agent_progress_line,
    build_codex_plugin_command,
    build_external_agent_command,
    codex_plugin_status_by_name,
    parse_codex_plugin_list,
    parse_external_agent_jsonl,
    validate_codex_plugin_selector,
)


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

    assert command[:3] == ("codex", "--search", "exec")
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
    assert command[:2] == ("codex", "exec")
    assert "--ask-for-approval" not in command


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


def test_external_agent_progress_line_summarizes_json_events() -> None:
    assert (
        _external_agent_progress_line('{"type":"response.reasoning_summary.delta"}\n')
        == "external_agent_activity: response.reasoning_summary.delta"
    )
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
