from pathlib import Path
from typing import Any

from ai_provider.codex_mcp import build_codex_mcp_add_command, setup_project_codex_mcp


def test_setup_project_codex_mcp_creates_project_config(tmp_path: Path) -> None:
    result = setup_project_codex_mcp(tmp_path, register_global=False)

    text = (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert result.created is True
    assert result.config_path == tmp_path / ".codex" / "config.toml"
    assert "[mcp_servers.repo_assistant_tools]" in text
    assert 'command = "python"' in text
    assert '"-m", "uv", "run", "ai-agent-mcp", "--workspace-root"' in text
    assert f'"{str(tmp_path).replace(chr(92), chr(92) * 2)}"' in text
    assert 'enabled_tools = ["read_file", "list_dir", "find_files", "grep_search"]' in text
    assert 'default_tools_approval_mode = "auto"' in text
    assert "required = false" in text
    assert result.global_registered is False


def test_setup_project_codex_mcp_preserves_other_config_and_replaces_server(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "\n".join(
            [
                'model = "gpt-5.5"',
                "",
                "[mcp_servers.repo_assistant_tools]",
                'command = "old"',
                "",
                "[mcp_servers.other]",
                'command = "other"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = setup_project_codex_mcp(tmp_path, register_global=False)

    text = config_path.read_text(encoding="utf-8")
    assert result.created is False
    assert 'model = "gpt-5.5"' in text
    assert 'command = "old"' not in text
    assert text.count("[mcp_servers.repo_assistant_tools]") == 1
    assert "[mcp_servers.other]" in text


def test_setup_project_codex_mcp_preserves_escaped_windows_paths_when_replacing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / ".codex" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        "\n".join(
            [
                "[mcp_servers.repo_assistant_tools]",
                'command = "old"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    setup_project_codex_mcp(tmp_path, register_global=False)

    text = config_path.read_text(encoding="utf-8")
    escaped_repo_path = str(tmp_path.resolve()).replace("\\", "\\\\")
    assert f'"{escaped_repo_path}"' in text


def test_setup_project_codex_mcp_can_register_global_with_codex_cli(tmp_path: Path) -> None:
    calls: list[tuple[Any, ...]] = []

    def fake_runner(command, **kwargs):
        calls.append(tuple(command))
        return __import__("subprocess").CompletedProcess(
            command,
            0,
            stdout="Added global MCP server 'repo_assistant_tools'.\n",
            stderr="",
        )

    result = setup_project_codex_mcp(
        tmp_path,
        register_global=True,
        codex_command="codex-test",
        runner=fake_runner,
    )

    assert calls[0] == ("codex-test", "mcp", "remove", "repo_assistant_tools")
    assert calls[1] == build_codex_mcp_add_command(
        tmp_path,
        server_name="repo_assistant_tools",
        codex_command="codex-test",
    )
    assert result.global_registered is True
    assert "Added global MCP server" in result.global_add_stdout


def test_build_codex_mcp_add_command_uses_repo_workspace_root(tmp_path: Path) -> None:
    command = build_codex_mcp_add_command(
        tmp_path,
        codex_command="codex-test",
    )

    assert command == (
        "codex-test",
        "mcp",
        "add",
        "repo_assistant_tools",
        "--",
        "python",
        "-m",
        "uv",
        "run",
        "ai-agent-mcp",
        "--workspace-root",
        str(tmp_path.resolve()),
    )
