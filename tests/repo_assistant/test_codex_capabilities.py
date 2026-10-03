"""Repo-assistant codex capabilities regression contracts."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from ai_provider.codex_mcp import CodexMcpSetupResult

from .support import (
    _EXAMPLE,
    main,
)


def test_cli_can_setup_project_codex_mcp_without_prompt(
    tmp_path: Path,
    capsys,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    assert main(["--repo-root", str(repo_root), "--codex-mcp-setup"]) == 0

    output = capsys.readouterr().out
    config_file = repo_root / ".codex" / "config.toml"
    text = config_file.read_text(encoding="utf-8")
    assert "=== Codex MCP setup ===" in output
    assert f"repo_root: {repo_root.resolve()}" in output
    assert f"codex_mcp_config: {config_file}" in output
    assert "codex_mcp_server: repo_assistant_tools" in output
    assert "codex_mcp_enabled_tools_json:" in output
    assert "codex_mcp_global_registered: False" in output
    assert "[mcp_servers.repo_assistant_tools]" in text
    assert "ai_agent.mcp_server" in text
    assert "run_command" not in text


def test_cli_can_setup_and_register_codex_mcp_when_explicitly_requested(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    def fake_setup_project_codex_mcp(repo_root_arg: Path, *, register_global: bool):
        assert repo_root_arg == repo_root.resolve()
        assert register_global is True
        return CodexMcpSetupResult(
            config_path=repo_root / ".codex" / "config.toml",
            server_name="repo_assistant_tools",
            command=sys.executable,
            args=("-m", "ai_agent.mcp_server"),
            enabled_tools=("read_file", "list_dir", "find_files", "grep_search", "delegate_task"),
            created=True,
            global_registered=True,
            global_add_stdout="Added global MCP server.",
        )

    monkeypatch.setattr(_EXAMPLE, "setup_project_codex_mcp", fake_setup_project_codex_mcp)

    assert (
        main(["--repo-root", str(repo_root), "--codex-mcp-setup", "--codex-mcp-register-global"])
        == 0
    )

    output = capsys.readouterr().out
    assert "codex_mcp_global_registered: True" in output
    assert "codex_mcp_add_stdout: Added global MCP server." in output


def test_cli_can_refresh_codex_login(capsys, monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, *args, **kwargs):
        joined = tuple(command)
        calls.append(joined)
        if joined[1:] == ("login",):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "", "")
        if joined[1:] == ("login", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "Logged in using ChatGPT\n", "")
        raise AssertionError(joined)

    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert main(["--repo-root", str(tmp_path), "--codex-login"]) == 0

    output = capsys.readouterr().out
    assert ("codex", "login") in calls
    assert ("codex", "login", "status") in calls
    assert "codex_login_auth_boundary: local Codex auth refresh only" in output
    assert 'codex_login_command_line_json: ["codex", "login"]' in output
    assert "codex_login_status_stdout: Logged in using ChatGPT" in output
    assert "execution_status: completed" in output


def test_cli_can_refresh_codex_login_with_device_auth(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, *args, **kwargs):
        joined = tuple(command)
        calls.append(joined)
        if joined[1:] == ("login", "--device-auth"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "", "")
        if joined[1:] == ("login", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "Logged in using ChatGPT\n", "")
        raise AssertionError(joined)

    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    assert main(["--repo-root", str(tmp_path), "--codex-login-device"]) == 0

    output = capsys.readouterr().out
    assert ("codex", "login", "--device-auth") in calls
    assert 'codex_login_command_line_json: ["codex", "login", "--device-auth"]' in output


def test_codex_login_rejects_prompt_request(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--repo-root", str(tmp_path), "--codex-login", "Do work."])


def test_codex_login_modes_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--repo-root", str(tmp_path), "--codex-login", "--codex-login-device"])


def test_cli_can_plan_codex_output_schema(capsys, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    schema_file = tmp_path / "answer.schema.json"
    schema_file.write_text('{"type":"object"}', encoding="utf-8")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Return structured output.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-output-schema",
                str(schema_file),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_output_schema:" in output
    assert "--output-schema" in output
    assert str(schema_file) in output


def test_cli_can_plan_codex_search(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")

    assert (
        main(
            [
                "--mode",
                "plan",
                "Search for current documentation.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-search",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_web_search: True" in output
    assert '"codex-test", "--search", "--ask-for-approval", "never", "exec"' in output
    assert '"exec", "--search"' not in output


def test_cli_can_plan_codex_images(capsys, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_COMMAND", "codex-test")
    before_image = tmp_path / "before.png"
    after_image = tmp_path / "after.jpg"

    assert (
        main(
            [
                "--mode",
                "plan",
                "Compare the UI screenshots.",
                "--privacy",
                "external_allowed",
                "--route-id",
                "openai-codex-gpt-5-5",
                "--provider",
                "openai",
                "--model",
                "gpt-5.5",
                "--skip-prompt-review",
                "--codex-image",
                str(before_image),
                "--codex-image",
                str(after_image),
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "external_agent_images_json:" in output
    assert "--image" in output
    assert before_image.name in output
    assert after_image.name in output


def test_codex_output_schema_requires_codex_route(tmp_path: Path) -> None:
    schema_file = tmp_path / "answer.schema.json"
    schema_file.write_text('{"type":"object"}', encoding="utf-8")

    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-output-schema",
                str(schema_file),
            ]
        )


def test_codex_search_requires_codex_route() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-search",
            ]
        )


def test_codex_mcp_tools_requires_codex_route() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-mcp-tools",
            ]
        )


def test_codex_image_requires_codex_route(tmp_path: Path) -> None:
    image_file = tmp_path / "screenshot.png"

    with pytest.raises(SystemExit):
        main(
            [
                "--mode",
                "plan",
                "Invalid route.",
                "--provider",
                "ollama",
                "--model",
                "qwen2.5-coder:14b",
                "--codex-image",
                str(image_file),
            ]
        )


def test_codex_capability_status_reports_expected_diagnostics(monkeypatch) -> None:
    def fake_run(command, *args, **kwargs):
        joined = tuple(command)
        if joined[1:] == ("--version",):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "codex-cli 0.137.0\n", "")
        if joined[1:] == ("login", "status"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "Logged in using ChatGPT\n", "")
        if joined[1:] == ("exec", "--help"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "--json\n", "")
        if joined[1:] == ("mcp", "list"):
            return _EXAMPLE.subprocess.CompletedProcess(
                joined,
                0,
                "No MCP servers configured yet.\n",
                "",
            )
        if joined[1:] == ("plugin", "list"):
            return _EXAMPLE.subprocess.CompletedProcess(
                joined,
                0,
                "\n".join(
                    [
                        "Marketplace `openai-curated`",
                        "C:\\codex\\marketplace.json",
                        "PLUGIN                 STATUS         VERSION  PATH",
                        "linear@openai-curated  not installed           C:\\codex\\plugins\\linear",
                        "github@openai-curated  installed, enabled  1.2.3    "
                        "C:\\codex\\plugins\\github",
                    ]
                ),
                "",
            )
        raise AssertionError(joined)

    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)
    monkeypatch.delenv("CODEX_HOME", raising=False)

    status = _EXAMPLE._codex_capability_status("C:/codex/bin/codex.exe")

    assert status["version"] == "codex-cli 0.137.0"
    assert status["login_status"] == "Logged in using ChatGPT"
    assert status["exec_json_supported"] is True
    assert status["mcp_list"]["stdout"] == "No MCP servers configured yet."
    assert "linear@openai-curated" in status["plugin_list"]["stdout"]
    assert status["plugin_summary"]["marketplaces"] == ["openai-curated"]
    assert status["plugin_summary"]["available_count"] == 2
    assert status["plugin_summary"]["installed_count"] == 1
    assert status["plugin_summary"]["plugins"][0]["status"] == "not installed"
    assert status["plugin_summary"]["plugins"][1]["status"] == "installed, enabled"
    assert status["config_path"] == "C:\\codex\\config.toml"


def test_capability_report_includes_codex_authorization(monkeypatch) -> None:
    monkeypatch.setattr(
        _EXAMPLE,
        "_external_agent_status",
        lambda: {
            "codex_available": True,
            "codex_command": "codex",
            "codex": {
                "available": True,
                "command": "codex",
                "login_status": "Logged in using ChatGPT",
                "exec_json_supported": True,
                "plugin_summary": {
                    "marketplaces": ["openai-curated"],
                    "available_count": 65,
                    "installed_count": 5,
                    "plugins": [],
                },
                "mcp_list": {"ok": True, "stdout": "repo_assistant_tools", "stderr": ""},
            },
            "antigravity_available": False,
            "antigravity_command": None,
            "copilot_available": False,
            "copilot_command": None,
            "kiro_available": False,
            "kiro_command": None,
        },
    )
    snapshot = SimpleNamespace(
        system=SimpleNamespace(
            os_name="Windows",
            os_version="11",
            machine="AMD64",
            processor="x64",
            logical_cpu_count=16,
            memory=SimpleNamespace(total_bytes=32, available_bytes=16),
            gpus=[],
        ),
        ollama_available=False,
        ollama_version=None,
        models_path=None,
        installed_ollama_models=[],
        running_ollama_models=[],
    )

    report = _EXAMPLE._capability_report(snapshot)

    assert report["authorization"]["service_count"] == 1
    service = report["authorization"]["services"][0]
    assert service["service_id"] == "codex"
    assert service["state"] == "authorized"
    assert service["capability"]["write"] is True
    assert "write:codex.mcp_registration" in service["capability"]["scopes"]


def test_cli_can_install_codex_plugins_when_explicitly_executed(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []
    plugin_installed = False

    def fake_run(command, *args, **kwargs):
        nonlocal plugin_installed
        joined = tuple(command)
        calls.append(joined)
        if joined[1:] == ("plugin", "list"):
            row = (
                "github@openai-curated  installed, enabled  1.2.3    C:\\codex\\plugins\\github"
                if plugin_installed
                else "github@openai-curated  not installed           C:\\codex\\plugins\\github"
            )
            return _EXAMPLE.subprocess.CompletedProcess(
                joined,
                0,
                "\n".join(
                    [
                        "Marketplace `openai-curated`",
                        "C:\\codex\\marketplace.json",
                        "PLUGIN                 STATUS         VERSION  PATH",
                        row,
                    ]
                ),
                "",
            )
        if joined[1:] == ("plugin", "add", "github@openai-curated"):
            return _EXAMPLE.subprocess.CompletedProcess(joined, 0, "installed\n", "")
        raise AssertionError(joined)

    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.setattr(_EXAMPLE.subprocess, "run", fake_run)

    def fake_plugin_operation(command, *, action, selector, timeout_seconds=60.0):
        nonlocal plugin_installed
        plugin_command = (command, "plugin", action, selector)
        calls.append(plugin_command)
        plugin_installed = action == "add"
        return SimpleNamespace(
            ok=True,
            returncode=0,
            stdout="installed",
            stderr="",
        )

    monkeypatch.setattr(_EXAMPLE, "run_codex_plugin_operation", fake_plugin_operation)

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--codex-plugin-install",
            "github@openai-curated",
            "--execute",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert ("codex", "plugin", "add", "github@openai-curated") in calls
    assert "codex_plugin_auth_boundary: install/remove only; no OAuth" in output
    assert "codex_plugin_expected_status_json:" in output
    assert "codex_plugin_next_step: start a new Codex CLI session" in output
    assert "execution_status: completed" in output
