from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ai_orchestrator import AccessMethod, OrchestrationResult


@dataclass(frozen=True)
class ExternalAgentConfig:
    """Runtime configuration for an external coding-agent CLI."""

    access_method: AccessMethod
    command: str
    model: str
    cwd: Path
    timeout_seconds: float
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    ephemeral: bool = True
    json_output: bool = True
    resume: str | None = None
    output_last_message_path: Path | None = None
    output_schema_path: Path | None = None
    web_search: bool = False
    image_paths: tuple[Path, ...] = ()
    codex_mcp_tools: bool = False
    shared_tool_profile: str | None = None
    shared_agent_name: str | None = None
    shared_task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    shared_run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    shared_terminal_approvals: bool = False
    shared_session_database: Path | None = None
    shared_session_id: str | None = None


@dataclass(frozen=True)
class ExternalAgentEventSummary:
    """Structured summary parsed from an external agent JSONL event stream."""

    final_answer: str | None
    command_events: tuple[dict[str, Any], ...]
    tool_events: tuple[dict[str, Any], ...]
    web_search_events: tuple[dict[str, Any], ...]
    file_change_events: tuple[dict[str, Any], ...]
    usage: dict[str, Any] | None
    failure_reason: str | None
    parse_errors: tuple[str, ...]


@dataclass(frozen=True)
class ExternalAgentResult:
    """Completed external coding-agent process result."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    last_message: str | None = None
    events: ExternalAgentEventSummary | None = None


@dataclass(frozen=True)
class CodexPluginInfo:
    """One plugin listed by the Codex plugin marketplace command."""

    name: str
    status: str
    version: str | None
    path: str | None


@dataclass(frozen=True)
class CodexPluginListSummary:
    """Structured summary of `codex plugin list` output."""

    marketplaces: tuple[str, ...]
    plugins: tuple[CodexPluginInfo, ...]

    @property
    def installed_count(self) -> int:
        """Return how many listed plugins are currently installed."""

        return sum(1 for plugin in self.plugins if plugin.status.startswith("installed"))

    @property
    def available_count(self) -> int:
        """Return how many plugins were listed in configured marketplaces."""

        return len(self.plugins)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""

        return {
            "marketplaces": list(self.marketplaces),
            "available_count": self.available_count,
            "installed_count": self.installed_count,
            "plugins": [
                {
                    "name": plugin.name,
                    "status": plugin.status,
                    "version": plugin.version,
                    "path": plugin.path,
                }
                for plugin in self.plugins
            ],
        }


@dataclass(frozen=True)
class CodexPluginOperationResult:
    """Result of one explicit Codex plugin install or removal command."""

    selector: str
    action: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """Return whether the Codex plugin command completed successfully."""

        return self.returncode == 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""

        return {
            "selector": self.selector,
            "action": self.action,
            "command": list(self.command),
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def is_external_agent_access_method(access_method: AccessMethod) -> bool:
    """Return whether an access method uses an external coding-agent client."""

    return access_method in {
        AccessMethod.CODEX_CLI,
        AccessMethod.ANTIGRAVITY_CLI,
        AccessMethod.COPILOT_CLI,
        AccessMethod.KIRO_CLI,
    }


def default_codex_command() -> str | None:
    """Return Codex CLI from env, PATH, or the PyCharm bundled install."""

    configured = os.environ.get("CODEX_COMMAND")
    if configured:
        return configured

    command = shutil.which("codex")
    if command:
        return command

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    bundled = (
        Path(local_app_data)
        / "JetBrains"
        / "PyCharm2025.3"
        / "aia"
        / "codex"
        / "bin"
        / "codex-x86_64-pc-windows-msvc.exe"
    )
    return str(bundled) if bundled.exists() else None


def external_agent_command(access_method: AccessMethod) -> str | None:
    """Return the configured command for a supported external coding-agent route."""

    if access_method is AccessMethod.CODEX_CLI:
        return default_codex_command()
    if access_method is AccessMethod.ANTIGRAVITY_CLI:
        return (
            os.environ.get("ANTIGRAVITY_COMMAND")
            or shutil.which("agy")
            or shutil.which("antigravity")
        )
    if access_method is AccessMethod.COPILOT_CLI:
        return os.environ.get("GITHUB_COPILOT_COMMAND") or shutil.which("copilot")
    if access_method is AccessMethod.KIRO_CLI:
        command = os.environ.get("KIRO_COMMAND") or shutil.which("kiro-cli") or shutil.which("kiro")
        if command:
            return command
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            installed = Path(local_app_data) / "Kiro-Cli" / "kiro-cli.exe"
            if installed.is_file():
                return str(installed)
    return None


def external_agent_status() -> dict[str, Any]:
    """Return local discovery status for configured external coding-agent clients."""

    codex_command = external_agent_command(AccessMethod.CODEX_CLI)
    antigravity_command = external_agent_command(AccessMethod.ANTIGRAVITY_CLI)
    copilot_command = external_agent_command(AccessMethod.COPILOT_CLI)
    kiro_command = external_agent_command(AccessMethod.KIRO_CLI)
    return {
        "codex_available": codex_command is not None,
        "codex_command": codex_command,
        "codex": codex_capability_status(codex_command),
        "antigravity_available": antigravity_command is not None,
        "antigravity_command": antigravity_command,
        "antigravity": external_agent_capability_status(
            antigravity_command,
            help_args=("--help",),
            expected_flags=("-p", "--prompt", "--output-format", "--model"),
        ),
        "copilot_available": copilot_command is not None,
        "copilot_command": copilot_command,
        "copilot": external_agent_capability_status(
            copilot_command,
            help_args=("--help",),
            expected_flags=("-p", "--prompt", "--output-format", "--allow-tool"),
        ),
        "kiro_available": kiro_command is not None,
        "kiro_command": kiro_command,
        "kiro": external_agent_capability_status(
            kiro_command,
            help_args=("chat", "--help"),
            expected_flags=("--no-interactive", "--output-format", "--trust-tools"),
        ),
    }


def run_diagnostic_command(
    command: str,
    *args: str,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Run a read-only local diagnostic command and return redacted process metadata."""

    try:
        completed = subprocess.run(
            (command, *args),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def codex_config_path(command: str | None = None) -> str:
    """Return the Codex config path without reading config contents."""

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return str(Path(codex_home) / "config.toml")
    if command:
        command_path = Path(command)
        if command_path.parent.name == "bin":
            return str(command_path.parent.parent / "config.toml")
    return str(Path.home() / ".codex" / "config.toml")


def codex_capability_status(command: str | None) -> dict[str, Any]:
    """Return best-effort Codex CLI diagnostics without exposing secrets."""

    if command is None:
        return {
            "available": False,
            "command": None,
            "version": None,
            "login_status": "unavailable",
            "exec_json_supported": False,
            "config_path": codex_config_path(command),
            "mcp_list": None,
            "plugin_list": None,
            "plugin_summary": None,
        }

    version = run_diagnostic_command(command, "--version")
    login = run_diagnostic_command(command, "login", "status")
    exec_help = run_diagnostic_command(command, "exec", "--help")
    mcp_list = run_diagnostic_command(command, "mcp", "list")
    plugin_list = run_diagnostic_command(command, "plugin", "list")
    return {
        "available": True,
        "command": command,
        "version": version["stdout"] or version["stderr"] or None,
        "login_status": login["stdout"] or login["stderr"] or None,
        "exec_json_supported": "--json" in str(exec_help["stdout"]),
        "config_path": codex_config_path(command),
        "mcp_list": diagnostic_text_result(mcp_list),
        "plugin_list": diagnostic_text_result(plugin_list),
        "plugin_summary": parse_codex_plugin_list(plugin_list["stdout"]).to_dict()
        if plugin_list["ok"]
        else None,
    }


def diagnostic_text_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize a diagnostic command result for JSON reporting."""

    return {
        "ok": result["ok"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def external_agent_capability_status(
    command: str | None,
    *,
    help_args: tuple[str, ...],
    expected_flags: tuple[str, ...],
    version_args: tuple[str, ...] = ("--version",),
) -> dict[str, Any]:
    """Return secret-free diagnostics for a non-Codex external agent command."""

    if command is None:
        return {
            "available": False,
            "command": None,
            "version": None,
            "help": None,
            "expected_flags_supported": {flag: False for flag in expected_flags},
        }

    version = run_diagnostic_command(command, *version_args)
    help_result = run_diagnostic_command(command, *help_args)
    help_text = f"{help_result['stdout']}\n{help_result['stderr']}"
    return {
        "available": True,
        "command": command,
        "version": version["stdout"] or version["stderr"] or None,
        "help": diagnostic_text_result(help_result),
        "expected_flags_supported": {flag: flag in help_text for flag in expected_flags},
    }


def validate_codex_plugin_selector(selector: str) -> None:
    """Validate the exact PLUGIN@MARKETPLACE selector expected by Codex CLI."""

    if not selector or selector.strip() != selector:
        raise ValueError("plugin selector must be non-empty and contain no surrounding space")
    if selector.count("@") != 1:
        raise ValueError("plugin selector must use the exact PLUGIN@MARKETPLACE form")
    plugin, marketplace = selector.split("@", maxsplit=1)
    if not plugin or not marketplace:
        raise ValueError("plugin selector must include both plugin and marketplace")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
    if any(char not in allowed for char in plugin) or any(
        char not in allowed for char in marketplace
    ):
        raise ValueError(
            "plugin selector may contain only lowercase letters, digits, hyphen, underscore, or dot"
        )


def build_codex_plugin_command(command: str, action: str, selector: str) -> tuple[str, ...]:
    """Build a Codex plugin add/remove command for an exact selector."""

    validate_codex_plugin_selector(selector)
    if action not in {"add", "remove"}:
        raise ValueError("plugin action must be 'add' or 'remove'")
    return (command, "plugin", action, selector)


def run_codex_plugin_operation(
    command: str,
    *,
    action: str,
    selector: str,
    timeout_seconds: float = 60.0,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CodexPluginOperationResult:
    """Run one explicit Codex plugin add/remove command."""

    plugin_command = build_codex_plugin_command(command, action, selector)
    completed = runner(
        plugin_command,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )
    return CodexPluginOperationResult(
        selector=selector,
        action=action,
        command=plugin_command,
        returncode=completed.returncode,
        stdout=(completed.stdout or "").strip(),
        stderr=(completed.stderr or "").strip(),
    )


def parse_codex_plugin_list(text: str) -> CodexPluginListSummary:
    """Parse the table-like output from `codex plugin list`."""

    marketplaces: list[str] = []
    plugins: list[CodexPluginInfo] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Marketplace `") and line.endswith("`"):
            marketplaces.append(line.removeprefix("Marketplace `").removesuffix("`"))
            continue
        if (
            line.startswith("PLUGIN ")
            or line.startswith("PATH")
            or line.endswith("marketplace.json")
        ):
            continue
        if "@" not in line:
            continue
        plugin = _parse_codex_plugin_row(line)
        if plugin is not None:
            plugins.append(plugin)
    return CodexPluginListSummary(marketplaces=tuple(marketplaces), plugins=tuple(plugins))


def codex_plugin_status_by_name(
    summary: CodexPluginListSummary,
    selectors: tuple[str, ...],
) -> dict[str, dict[str, str | None]]:
    """Return status details for requested plugin selectors from a parsed list."""

    by_name = {plugin.name: plugin for plugin in summary.plugins}
    result: dict[str, dict[str, str | None]] = {}
    for selector in selectors:
        plugin = by_name.get(selector)
        result[selector] = (
            {
                "status": plugin.status,
                "version": plugin.version,
                "path": plugin.path,
            }
            if plugin is not None
            else {
                "status": "missing_from_plugin_list",
                "version": None,
                "path": None,
            }
        )
    return result


def _parse_codex_plugin_row(line: str) -> CodexPluginInfo | None:
    parts = line.split()
    if len(parts) < 3 or "@" not in parts[0]:
        return None
    name = parts[0]
    if parts[1] == "not" and len(parts) >= 4 and parts[2] == "installed":
        status = "not installed"
        version = None
        path = " ".join(parts[3:]) or None
        return CodexPluginInfo(name=name, status=status, version=version, path=path)
    if parts[1].startswith("installed") and len(parts) >= 5 and parts[2] == "enabled":
        status = "installed, enabled"
        version = parts[3] if parts[3] != "-" else None
        path = " ".join(parts[4:]) or None
        return CodexPluginInfo(name=name, status=status, version=version, path=path)

    status = parts[1]
    version = parts[2] if len(parts) >= 3 and parts[2] != "-" else None
    path = " ".join(parts[3:]) if len(parts) > 3 else None
    return CodexPluginInfo(name=name, status=status, version=version, path=path)


def external_agent_config_from_orchestration(
    orchestration: OrchestrationResult,
    *,
    repo_root: Path,
    timeout_seconds: float,
    sandbox: str = "workspace-write",
    approval_policy: str = "never",
    codex_persist_session: bool = False,
    codex_resume: str | None = None,
    output_last_message_path: Path | None = None,
    output_schema_path: Path | None = None,
    web_search: bool = False,
    image_paths: tuple[Path, ...] = (),
    codex_mcp_tools: bool = False,
    shared_tool_profile: str | None = None,
) -> ExternalAgentConfig:
    """Adapt a ready orchestration result to an external-agent runtime config."""

    assert orchestration.execution_plan is not None
    target = orchestration.execution_plan.target
    if target.access_method is not AccessMethod.CODEX_CLI and codex_persist_session:
        raise NotImplementedError("Codex session persistence is not mapped for alternate clients")
    if not is_external_agent_access_method(target.access_method):
        raise NotImplementedError(
            f"{target.access_method.value} execution is not implemented yet. "
            "Configure the official command first, then add an executor adapter."
        )
    command = external_agent_command(target.access_method)
    if command is None:
        raise FileNotFoundError(
            f"Could not find {target.access_method.value}. Install the official client "
            "or configure its command environment variable."
        )
    return ExternalAgentConfig(
        access_method=target.access_method,
        command=command,
        model=target.model,
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
        sandbox="read-only" if shared_tool_profile else sandbox,
        approval_policy=approval_policy,
        ephemeral=(
            target.access_method is AccessMethod.CODEX_CLI
            and not codex_persist_session
            and codex_resume is None
        ),
        resume=codex_resume,
        output_last_message_path=output_last_message_path,
        output_schema_path=output_schema_path,
        web_search=web_search,
        image_paths=image_paths,
        codex_mcp_tools=codex_mcp_tools,
        shared_tool_profile=shared_tool_profile,
        shared_terminal_approvals=shared_tool_profile == "coding" and sys.stdin.isatty(),
    )


def parse_external_agent_jsonl(text: str) -> ExternalAgentEventSummary:
    """Normalize Codex, Antigravity, Copilot, and Kiro JSONL output."""

    final_answer = None
    command_events: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    web_search_events: list[dict[str, Any]] = []
    file_change_events: list[dict[str, Any]] = []
    usage = None
    failure_reason = None
    answer_chunks: list[str] = []
    parse_errors: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {line_number}: {exc.msg}")
            continue
        if not isinstance(event, dict):
            parse_errors.append(f"line {line_number}: expected JSON object")
            continue
        event_type = _event_type(event)
        data = event.get("data")
        if isinstance(data, dict):
            event = {**event, **data}
            update = data.get("update")
            if isinstance(update, dict):
                if update.get("sessionUpdate") == "agent_message_chunk":
                    chunk = _find_text_payload(update.get("content"))
                    if chunk:
                        answer_chunks.append(chunk)
                elif update.get("sessionUpdate") in {"tool_call", "tool_call_update"}:
                    tool_events.append(event)
            if event_type == "runfinished":
                final_text = data.get("finalText")
                if isinstance(final_text, str) and final_text.strip():
                    final_answer = final_text.strip()
                elif answer_chunks:
                    final_answer = "".join(answer_chunks)
                if data.get("status") not in {"success", "completed"}:
                    failure_reason = str(data.get("stopReason") or data.get("status"))
            metering = data.get("meteringUsage")
            if isinstance(metering, list):
                usage = {"metering_usage": metering}
        nested_result = event.get("result")
        if isinstance(nested_result, dict):
            event = {**event, **nested_result}
        if _is_command_event(event, event_type):
            command_events.append(event)
        if _is_tool_event(event, event_type):
            tool_events.append(event)
        if _is_web_search_event(event, event_type):
            web_search_events.append(event)
        if _is_file_change_event(event, event_type):
            file_change_events.append(event)
        event_usage = _find_usage(event)
        if event_usage is not None:
            usage = event_usage
        event_failure = _find_failure_reason(event, event_type)
        if event_failure is not None:
            failure_reason = event_failure
        event_answer = _find_final_answer(event, event_type)
        if event_answer:
            final_answer = event_answer
    return ExternalAgentEventSummary(
        final_answer=final_answer,
        command_events=tuple(command_events),
        tool_events=tuple(tool_events),
        web_search_events=tuple(web_search_events),
        file_change_events=tuple(file_change_events),
        usage=usage,
        failure_reason=failure_reason,
        parse_errors=tuple(parse_errors),
    )


def build_external_agent_command(
    config: ExternalAgentConfig,
    *,
    prompt: str | None = None,
) -> tuple[str, ...]:
    """Build the noninteractive command for an external coding-agent client."""

    if config.access_method is not AccessMethod.CODEX_CLI:
        return _build_alternate_agent_command(config, prompt=prompt)

    command = [config.command]
    if config.web_search:
        command.append("--search")
    if config.codex_mcp_tools:
        command.extend(_codex_mcp_config_overrides(config.cwd))
    if config.shared_tool_profile:
        if config.shared_tool_profile not in {"inspection", "coding"} or config.codex_mcp_tools:
            raise ValueError("Shared inspection cannot be combined with legacy Codex MCP tools")
        if config.sandbox != "read-only":
            raise ValueError("Shared inspection requires a read-only sandbox")
        from ai_provider.shared_client_tools import codex_inspection_overrides

        command.extend(codex_inspection_overrides(config.cwd, _shared_run_context(config)))
    if config.approval_policy:
        command.extend(
            [
                "--ask-for-approval",
                "never"
                if config.shared_tool_profile
                else _codex_approval_policy(config.approval_policy),
            ]
        )
    if config.resume is not None:
        command.extend(
            [
                "exec",
                "--cd",
                str(config.cwd),
                "--model",
                config.model,
                "--sandbox",
                config.sandbox,
                "resume",
            ]
        )
        if config.json_output:
            command.append("--json")
        if config.output_last_message_path is not None:
            command.extend(["--output-last-message", str(config.output_last_message_path)])
        if config.output_schema_path is not None:
            command.extend(["--output-schema", str(config.output_schema_path)])
        for image_path in config.image_paths:
            command.extend(["--image", str(image_path)])
        if config.resume == "last":
            command.append("--last")
        else:
            command.append(config.resume)
        command.append("-")
        return tuple(command)

    command.extend(
        [
            "exec",
            "--cd",
            str(config.cwd),
            "--model",
            config.model,
            "--sandbox",
            config.sandbox,
        ]
    )
    if config.ephemeral:
        command.append("--ephemeral")
    if config.json_output:
        command.append("--json")
    if config.output_last_message_path is not None:
        command.extend(["--output-last-message", str(config.output_last_message_path)])
    if config.output_schema_path is not None:
        command.extend(["--output-schema", str(config.output_schema_path)])
    for image_path in config.image_paths:
        command.extend(["--image", str(image_path)])
    command.append("-")
    return tuple(command)


def _build_alternate_agent_command(
    config: ExternalAgentConfig,
    *,
    prompt: str | None,
) -> tuple[str, ...]:
    """Map only the approved trusted-local preset; reject unsupported options."""

    if config.shared_tool_profile:
        return _build_shared_inspection_command(config, prompt=prompt)
    if config.approval_policy != "trusted_local":
        raise NotImplementedError(
            f"{config.access_method.value}: only trusted_local is mapped; "
            "other approval modes are not mapped yet."
        )
    if config.sandbox != "danger-full-access":
        raise ValueError("trusted_local requires danger-full-access for alternate clients")
    if (
        config.resume is not None
        or config.output_last_message_path is not None
        or config.output_schema_path is not None
        or config.web_search
        or config.image_paths
        or config.codex_mcp_tools
    ):
        raise NotImplementedError("Codex-specific options are not mapped for alternate clients")
    if config.access_method is AccessMethod.ANTIGRAVITY_CLI:
        if not config.json_output:
            raise ValueError("Antigravity stream input requires JSON output")
        return (
            config.command,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--model",
            config.model,
            "--dangerously-skip-permissions",
        )
    if config.access_method is AccessMethod.KIRO_CLI:
        command = [config.command, "chat", "--no-interactive", "--trust-all-tools"]
        if config.model != "auto":
            command.extend(["--model", config.model])
        if config.json_output:
            command.extend(["--output-format", "stream-json"])
        return tuple(command)
    if config.access_method is AccessMethod.COPILOT_CLI:
        command = [
            config.command,
            "--allow-all",
            "--no-ask-user",
            "--model",
            config.model,
            "-p",
            prompt if prompt is not None else "<prompt supplied at execution>",
        ]
        if config.json_output:
            command.append("--output-format=json")
        return tuple(command)
    raise NotImplementedError(f"{config.access_method.value} execution is not implemented")


def _build_shared_inspection_command(
    config: ExternalAgentConfig, *, prompt: str | None
) -> tuple[str, ...]:
    from ai_provider.shared_client_tools import copilot_inspection_options

    if config.shared_tool_profile not in {"inspection", "coding"} or (
        config.shared_tool_profile == "inspection" and config.approval_policy != "read_only"
    ):
        raise ValueError("Common inspection requires the read_only preset")
    if config.sandbox != "read-only":
        raise ValueError("Common inspection requires a read-only sandbox")
    if (
        config.resume
        or config.output_last_message_path
        or config.output_schema_path
        or config.web_search
        or config.image_paths
        or config.codex_mcp_tools
    ):
        raise NotImplementedError("Codex-specific options are not mapped for common inspection")
    if config.access_method is AccessMethod.ANTIGRAVITY_CLI:
        raise NotImplementedError("Antigravity scoped shared-tool permissions are not verified")
    if config.access_method is AccessMethod.COPILOT_CLI:
        command = [
            config.command,
            *copilot_inspection_options(config.cwd, _shared_run_context(config)),
            "--no-ask-user",
            "--model",
            config.model,
            "-p",
            prompt if prompt is not None else "<prompt supplied at execution>",
        ]
        if config.json_output:
            command.append("--output-format=json")
        return tuple(command)
    if config.access_method is AccessMethod.KIRO_CLI:
        command = [
            config.command,
            "chat",
            "--agent",
            config.shared_agent_name or "repo-shared-inspection",
            "--no-interactive",
            "--require-mcp-startup",
        ]
        if config.model != "auto":
            command.extend(["--model", config.model])
        if config.json_output:
            command.extend(["--output-format", "stream-json"])
        command.append(prompt if prompt is not None else "<prompt supplied at execution>")
        return tuple(command)
    raise NotImplementedError(f"Shared inspection is not mapped for {config.access_method.value}")


def _shared_run_context(config: ExternalAgentConfig):
    from ai_provider.shared_client_tools import SharedToolRun

    if config.shared_tool_profile != "coding":
        return None
    return SharedToolRun(
        config.shared_task_id,
        config.shared_run_id,
        config.approval_policy,
        config.shared_terminal_approvals,
        config.shared_session_database,
        config.shared_session_id,
    )


def _codex_mcp_config_overrides(repo_root: Path) -> list[str]:
    """Return top-level Codex config overrides for project-local MCP tools."""

    repo_root = repo_root.resolve()
    return [
        "-c",
        f"mcp_servers.repo_assistant_tools.command={_codex_config_string(sys.executable)}",
        "-c",
        "mcp_servers.repo_assistant_tools.args="
        + _codex_config_array(
            (
                "-m",
                "ai_agent.mcp_server",
                "--workspace-root",
                str(repo_root),
            )
        ),
        "-c",
        f"mcp_servers.repo_assistant_tools.cwd={_codex_config_string(str(repo_root))}",
        "-c",
        "mcp_servers.repo_assistant_tools.enabled=true",
        "-c",
        "mcp_servers.repo_assistant_tools.required=false",
        "-c",
        "mcp_servers.repo_assistant_tools.default_tools_approval_mode='auto'",
        "-c",
        "mcp_servers.repo_assistant_tools.startup_timeout_sec=10",
        "-c",
        "mcp_servers.repo_assistant_tools.tool_timeout_sec=60",
        "-c",
        "mcp_servers.repo_assistant_tools.enabled_tools="
        + _codex_config_array(
            ("read_file", "list_dir", "find_files", "grep_search", "delegate_task")
        ),
    ]


def _codex_config_array(values: tuple[str, ...]) -> str:
    return "[" + ",".join(_codex_config_string(value) for value in values) + "]"


def _codex_config_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _codex_approval_policy(approval_policy: str) -> str:
    """Map repo-assistant approval presets to Codex CLI approval policies."""

    if approval_policy == "interactive":
        return "on-request"
    return "never"


def run_external_agent(
    prompt: str,
    config: ExternalAgentConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    progress_callback: Callable[[str], None] | None = None,
    progress_interval_seconds: float = 15.0,
) -> ExternalAgentResult:
    """Run an official coding client using its native prompt transport."""
    from ai_provider.coding_sessions import ACTIVE_SESSION

    session = ACTIVE_SESSION.get()
    if config.shared_tool_profile == "coding":
        config = replace(
            config,
            shared_run_id=uuid.uuid4().hex,
            shared_task_id=session.session_id if session else config.shared_task_id,
            shared_session_database=session.database if session else None,
            shared_session_id=session.session_id if session else None,
        )
    receipt = session.begin("external_client:" + config.access_method.value) if session else None
    try:
        result = _run_external_agent_owned(
            prompt,
            config,
            runner=runner,
            popen_factory=popen_factory,
            progress_callback=progress_callback,
            progress_interval_seconds=progress_interval_seconds,
        )
    except BaseException:
        if session and receipt:
            session.finish(receipt, status="interrupted")
        raise
    if session and receipt:
        events = result.events
        session.finish(
            receipt,
            status="completed"
            if result.returncode == 0 and not (events and events.failure_reason)
            else "failed",
            output=json.dumps(
                {
                    "returncode": result.returncode,
                    "tool_events": len(events.tool_events) if events else None,
                    "file_change_events": len(events.file_change_events) if events else None,
                }
            ),
        )
    return result


def _run_external_agent_owned(
    prompt: str,
    config: ExternalAgentConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    popen_factory: Callable[..., subprocess.Popen[str]],
    progress_callback: Callable[[str], None] | None,
    progress_interval_seconds: float,
) -> ExternalAgentResult:
    if config.shared_tool_profile and config.access_method is AccessMethod.KIRO_CLI:
        from ai_provider.shared_client_tools import kiro_inspection_agent

        name = "repo-shared-" + uuid.uuid4().hex
        directory = config.cwd / ".kiro" / "agents"
        if not directory.resolve().is_relative_to(config.cwd.resolve()):
            raise ValueError("Kiro project agent directory leaves the workspace")
        directory_existed = directory.exists()
        parent_existed = directory.parent.exists()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (name + ".json")
        content = json.dumps(kiro_inspection_agent(config.cwd, name, _shared_run_context(config)))
        created = False
        try:
            with path.open("x", encoding="utf-8") as file:
                file.write(content)
            created = True
            return _run_external_agent_process(
                prompt,
                replace(config, shared_agent_name=name),
                runner=runner,
                popen_factory=popen_factory,
                progress_callback=progress_callback,
                progress_interval_seconds=progress_interval_seconds,
            )
        finally:
            # Delete only our unchanged generated file, never client/user edits.
            if created and path.is_file() and path.read_text(encoding="utf-8") == content:
                path.unlink()
            for candidate, existed in (
                (directory, directory_existed),
                (directory.parent, parent_existed),
            ):
                if not existed:
                    try:
                        candidate.rmdir()
                    except OSError:
                        pass
    return _run_external_agent_process(
        prompt,
        config,
        runner=runner,
        popen_factory=popen_factory,
        progress_callback=progress_callback,
        progress_interval_seconds=progress_interval_seconds,
    )


def _run_external_agent_process(
    prompt: str,
    config: ExternalAgentConfig,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    popen_factory: Callable[..., subprocess.Popen[str]],
    progress_callback: Callable[[str], None] | None,
    progress_interval_seconds: float,
) -> ExternalAgentResult:
    command = build_external_agent_command(config, prompt=prompt)
    process_input = prompt
    if config.access_method is AccessMethod.ANTIGRAVITY_CLI:
        process_input = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
    elif config.access_method is AccessMethod.COPILOT_CLI:
        process_input = ""
    elif config.access_method is AccessMethod.KIRO_CLI and config.shared_tool_profile:
        process_input = ""
    if config.output_last_message_path is not None:
        config.output_last_message_path.parent.mkdir(parents=True, exist_ok=True)
    if runner is not subprocess.run:
        completed = runner(
            command,
            input=process_input,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=config.timeout_seconds,
            cwd=config.cwd,
        )
        return _external_agent_result_from_completed_process(command, config, completed)

    process = popen_factory(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=config.cwd,
        bufsize=1,
    )
    output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    readers: list[threading.Thread] = []
    for label, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        if stream is None:
            continue
        reader = threading.Thread(
            target=_read_process_stream,
            args=(label, stream, output_queue),
            daemon=True,
        )
        reader.start()
        readers.append(reader)

    try:
        if process.stdin is not None:
            process.stdin.write(process_input)
            process.stdin.close()
    except (BrokenPipeError, OSError):
        pass

    started = time.monotonic()
    last_activity = started
    last_progress = started
    while process.poll() is None or not output_queue.empty():
        now = time.monotonic()
        try:
            label, line = output_queue.get(timeout=0.2)
        except queue.Empty:
            if (
                progress_callback is not None
                and progress_interval_seconds > 0
                and now - last_progress >= progress_interval_seconds
            ):
                progress_callback(
                    "external_agent_status: running "
                    f"elapsed_seconds={now - started:.1f} "
                    f"last_output_age_seconds={now - last_activity:.1f}"
                )
                last_progress = now
            if config.timeout_seconds > 0 and now - last_activity > config.timeout_seconds:
                process.kill()
                _drain_process_output(output_queue, stdout_lines, stderr_lines)
                for reader in readers:
                    reader.join(timeout=1.0)
                raise subprocess.TimeoutExpired(
                    command,
                    timeout=config.timeout_seconds,
                    output="".join(stdout_lines),
                    stderr="".join(stderr_lines),
                ) from None
            continue

        last_activity = now
        if label == "stdout":
            stdout_lines.append(line)
            if progress_callback is not None:
                progress = _external_agent_progress_line(line)
                if progress is not None:
                    progress_callback(progress)
                    last_progress = now
        else:
            stderr_lines.append(line)
            if progress_callback is not None:
                progress = _external_agent_stderr_progress_line(line)
                if progress is not None:
                    progress_callback(progress)
                    last_progress = now

    for reader in readers:
        reader.join(timeout=1.0)
    _drain_process_output(output_queue, stdout_lines, stderr_lines)
    returncode = process.returncode if process.returncode is not None else 1
    completed = subprocess.CompletedProcess(
        command,
        returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
    )
    return _external_agent_result_from_completed_process(command, config, completed)


def _external_agent_result_from_completed_process(
    command: tuple[str, ...],
    config: ExternalAgentConfig,
    completed: subprocess.CompletedProcess[str],
) -> ExternalAgentResult:
    """Build a stable external-agent result from captured process output."""

    stdout = completed.stdout or ""
    events = parse_external_agent_jsonl(stdout) if config.json_output and stdout else None
    last_message = None
    if config.output_last_message_path is not None and config.output_last_message_path.exists():
        last_message = config.output_last_message_path.read_text(encoding="utf-8", errors="replace")
    stderr = completed.stderr or ""
    if (
        config.access_method == AccessMethod.ANTIGRAVITY_CLI
        and completed.returncode == 0
        and not last_message
        and not (events and events.final_answer)
        and "jetski: no output produced" in stderr
        and "auto-denied" in stderr
        and "headless mode" in stderr
    ):
        # This client reports a headless permission refusal with a successful exit.
        # Preserve the process status and receipts, but do not claim task completion.
        events = events or parse_external_agent_jsonl(stdout)
        if events.failure_reason is None:
            events = replace(
                events,
                failure_reason=(
                    "Antigravity produced no answer because headless tool permission was denied. "
                    "Configure permission for the required tools or use an interactive session."
                ),
            )
    return ExternalAgentResult(
        command=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        last_message=last_message,
        events=events,
    )


def _read_process_stream(
    label: str,
    stream: Any,
    output_queue: queue.Queue[tuple[str, str]],
) -> None:
    """Read one process stream into a queue line by line."""

    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            output_queue.put((label, line))
    finally:
        stream.close()


def _drain_process_output(
    output_queue: queue.Queue[tuple[str, str]],
    stdout_lines: list[str],
    stderr_lines: list[str],
) -> None:
    """Drain queued process output into captured stdout and stderr buffers."""

    while True:
        try:
            label, line = output_queue.get_nowait()
        except queue.Empty:
            return
        if label == "stdout":
            stdout_lines.append(line)
        else:
            stderr_lines.append(line)


def _external_agent_progress_line(line: str) -> str | None:
    """Return a bounded progress line for one external-agent output event."""

    stripped = line.strip()
    if not stripped:
        return None
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError:
        return "external_agent_activity: stdout"
    if not isinstance(event, dict):
        return "external_agent_activity: stdout"
    event_type = _event_type(event) or "json_event"
    if "reasoning" in event_type or event_type.endswith(("_delta", ".delta")):
        # Retain raw events in the result, but don't print every streamed fragment.
        # Process activity/deadlines still advance when a fragment is received.
        return None

    command = _find_string_payload(event, ("command",))
    if command:
        command_event_type = event_type
        nested = event.get("item")
        if isinstance(nested, dict):
            command_event_type = _event_type(nested) or command_event_type
        status = _find_string_payload(event, ("status",))
        status_detail = f" {status}" if status else ""
        return (
            f"external_agent_activity: {command_event_type}{status_detail} - command: "
            f"{_bounded_preview(command)}"
        )

    final_answer = _find_explicit_final_answer(event, event_type)
    if final_answer:
        return f"external_agent_activity: final_answer - {_bounded_preview(final_answer)}"

    failure_reason = _find_failure_reason(event, event_type)
    if failure_reason:
        return f"external_agent_activity: failure - {_bounded_preview(failure_reason)}"

    usage = _find_usage(event)
    if usage is not None:
        return f"external_agent_activity: usage - {_bounded_json(usage)}"

    query = _find_string_payload(event, ("query", "search_query"))
    if query:
        return f"external_agent_activity: {event_type} - query: {_bounded_preview(query)}"

    text = _find_text_payload(event)
    if text and "reasoning" not in event_type:
        return f"external_agent_activity: {event_type} - {_bounded_preview(text)}"

    return f"external_agent_activity: {event_type}"


def _external_agent_stderr_progress_line(line: str) -> str | None:
    """Return a bounded external-agent stderr activity line."""

    if _is_noisy_codex_model_refresh_stderr(line):
        return None
    preview = _bounded_preview(line)
    if not preview:
        return "external_agent_activity: stderr"
    return f"external_agent_activity: stderr - {preview}"


def _is_noisy_codex_model_refresh_stderr(line: str) -> bool:
    """Return whether a Codex stderr line is known noisy model metadata refresh output."""

    return (
        "codex_models_manager::manager" in line
        and "failed to refresh available models" in line
        and "unknown variant `max`" in line
    )


def _bounded_preview(value: str, *, limit: int = 360) -> str:
    """Return a single-line preview without exposing unbounded event payloads."""

    preview = " ".join(value.strip().split())
    if len(preview) <= limit:
        return preview
    return preview[: max(0, limit - 15)].rstrip() + " ...[truncated]"


def _bounded_json(value: dict[str, Any], *, limit: int = 180) -> str:
    """Return a compact bounded JSON object preview."""

    text = json.dumps(value, sort_keys=True)
    return _bounded_preview(text, limit=limit)


def _find_explicit_final_answer(event: dict[str, Any], event_type: str) -> str | None:
    """Find only event shapes that explicitly represent the final answer."""

    explicit = event.get("final_answer")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if event_type == "final_answer" or event_type.endswith(".final_answer"):
        return _find_text_payload(event)
    nested = event.get("item")
    if isinstance(nested, dict):
        nested_type = _event_type(nested)
        if nested_type == "final_answer" or nested_type.endswith(".final_answer"):
            return _find_text_payload(nested)
    return None


def _find_string_payload(value: Any, keys: tuple[str, ...]) -> str | None:
    """Find a string payload for any of the supplied keys."""

    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        for nested in value.values():
            found = _find_string_payload(nested, keys)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_string_payload(item, keys)
            if found:
                return found
    return None


def _event_type(event: dict[str, Any]) -> str:
    """Return the best-effort type label for a JSONL event."""

    for key in ("type", "event", "kind", "name"):
        value = event.get(key)
        if isinstance(value, str):
            return value.lower()
    nested = event.get("item")
    if isinstance(nested, dict):
        return _event_type(nested)
    return ""


def _is_command_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe shell command activity."""

    haystack = _event_haystack(event, event_type)
    return any(token in haystack for token in ("command", "shell", "exec", "terminal"))


def _is_tool_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe a tool call."""

    if event_type == "session.tools_updated":
        return False
    haystack = _event_haystack(event, event_type)
    return "tool" in haystack or "function_call" in haystack


def _is_web_search_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe Codex web search activity."""

    haystack = _event_haystack(event, event_type)
    return "web_search" in haystack


def _is_file_change_event(event: dict[str, Any], event_type: str) -> bool:
    """Return whether an event appears to describe a file modification."""

    haystack = _event_haystack(event, event_type)
    return any(token in haystack for token in ("file_change", "patch", "diff", "edit", "write"))


def _event_haystack(event: dict[str, Any], event_type: str) -> str:
    """Build a shallow searchable label string for classifying event families."""

    labels = [event_type]
    for key in ("type", "event", "kind", "name", "subtype", "status"):
        value = event.get(key)
        if isinstance(value, str):
            labels.append(value.lower())
    nested = event.get("item")
    if isinstance(nested, dict):
        labels.append(_event_haystack(nested, _event_type(nested)))
    return " ".join(labels)


def _find_usage(value: Any) -> dict[str, Any] | None:
    """Find the first nested usage/token payload in an event."""

    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = key.lower()
            if key_lower == "usage" and isinstance(nested, dict):
                return nested
            if "token" in key_lower and isinstance(nested, dict):
                return nested
            found = _find_usage(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_usage(item)
            if found is not None:
                return found
    return None


def _find_failure_reason(event: dict[str, Any], event_type: str) -> str | None:
    """Find a failure or error reason in an event."""

    if not _has_failure_marker(event, event_type):
        return None
    for key in ("error", "failure", "details"):
        value = event.get(key)
        if isinstance(value, dict):
            for nested_key in ("message", "error", "failure_reason", "reason", "detail"):
                nested_value = value.get(nested_key)
                if isinstance(nested_value, str) and nested_value.strip():
                    return nested_value.strip()
            nested = _find_failure_reason(value, _event_type(value) or key)
            if nested is not None:
                return nested
    for key in ("message", "error", "failure_reason", "reason", "detail"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = event.get("item")
    if isinstance(nested, dict):
        nested_failure = _find_failure_reason(nested, _event_type(nested))
        if nested_failure is not None:
            return nested_failure
    return event_type or "external agent reported failure"


def _has_failure_marker(event: dict[str, Any], event_type: str) -> bool:
    """Return whether event labels explicitly report a failure."""

    if event_type in {"task_complete", "turn.completed"} and event.get("error"):
        return True

    labels = [event_type]
    for key in ("type", "event", "kind", "name", "subtype", "status"):
        value = event.get(key)
        if isinstance(value, str):
            labels.append(value.lower())
    nested = event.get("item")
    if isinstance(nested, dict):
        labels.append(_event_type(nested))
        status = nested.get("status")
        if isinstance(status, str):
            labels.append(status.lower())
    return any(
        label in {"error", "failed", "failure"}
        or label.endswith(".failed")
        or label.endswith("_failed")
        or label.endswith(".error")
        or label.endswith("_error")
        for label in labels
    )


def _find_final_answer(event: dict[str, Any], event_type: str) -> str | None:
    """Find a final assistant answer in a Codex JSONL event."""

    explicit = event.get("final_answer")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if event_type == "result":
        response = event.get("response")
        if isinstance(response, str) and response.strip():
            return response.strip()
    if "final" in event_type or event.get("role") == "assistant":
        text = _find_text_payload(event)
        if text:
            return text
    if event_type in {
        "assistant_message",
        "assistant.message",
        "agent_message",
        "message",
        "response",
    }:
        text = _find_text_payload(event)
        if text:
            return text
    nested = event.get("item")
    if isinstance(nested, dict):
        return _find_final_answer(nested, _event_type(nested))
    return None


def _find_text_payload(value: Any) -> str | None:
    """Find a human-readable text payload inside common event shapes."""

    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("text", "content", "message", "answer", "output", "response"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        for key in ("content", "message", "delta", "item"):
            nested = value.get(key)
            found = _find_text_payload(nested)
            if found:
                return found
    if isinstance(value, list):
        parts = [_find_text_payload(item) for item in value]
        text = "\n".join(part for part in parts if part)
        return text or None
    return None
