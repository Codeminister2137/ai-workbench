from pathlib import Path

from ai_orchestrator import AccessMethod
from ai_provider.external_agents import (
    ExternalAgentConfig,
    build_external_agent_command,
    parse_codex_plugin_list,
    parse_external_agent_jsonl,
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


def test_parse_codex_plugin_list_summarizes_marketplace_rows() -> None:
    summary = parse_codex_plugin_list(
        "\n".join(
            [
                "Marketplace `openai-curated`",
                "C:\\codex\\.tmp\\plugins\\.agents\\plugins\\marketplace.json",
                "",
                "PLUGIN                 STATUS         VERSION  PATH",
                "linear@openai-curated  not installed           C:\\codex\\plugins\\linear",
                "github@openai-curated  installed      1.2.3    C:\\codex\\plugins\\github",
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
    assert summary.plugins[1].status == "installed"
    assert summary.plugins[1].version == "1.2.3"
