"""Pinned Gemini CLI transport with invocation-local settings and owned cleanup."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import signal
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ai_provider.process_ownership import WindowsJob

if TYPE_CHECKING:
    from ai_provider.external_agents import ExternalAgentConfig, ExternalAgentEventSummary

CLI_VERSION = "0.64.0"
NODE_VERSION = "v24.21.0"
INDIVIDUAL_ACCESS_RETIRED = (
    "Gemini CLI individual Google-account access retired on 2026-06-18; "
    "the free route is unavailable. Antigravity is a separate access product."
)
AUTH_OVERRIDES = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
    "GEMINI_CLI_AUTH_OVERRIDE",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GEMINI_CLI_SYSTEM_SETTINGS_PATH",
    "GEMINI_CLI_SYSTEM_DEFAULTS_PATH",
    "GEMINI_CLI_ACTIVITY_LOG_TARGET",
)


def default_command() -> str | None:
    configured = os.getenv("GEMINI_CLI_COMMAND")
    if configured:
        return configured
    local = Path.cwd() / ".tools/gemini-cli/node_modules/@google/gemini-cli/bundle/gemini.js"
    return str(local) if local.is_file() else shutil.which("gemini")


def command_prefix(command: str) -> tuple[str, ...]:
    """Use Node directly rather than a Windows shell shim or shell quoting."""
    path = Path(command).resolve()
    if path.suffix.lower() in {".cmd", ".ps1"}:
        path = path.parent.parent / "@google/gemini-cli/bundle/gemini.js"
    if path.suffix.lower() != ".js":
        raise ValueError("Gemini requires its official JS entry point or npm command shim")
    node = os.getenv("GEMINI_NODE_COMMAND")
    if not node:
        local = next(
            (
                parent / f"node-{NODE_VERSION}-win-x64/node.exe"
                for parent in path.parents
                if parent.name == ".tools"
            ),
            None,
        )
        node = str(local) if local and local.is_file() else shutil.which("node")
    if not node:
        raise FileNotFoundError("Gemini requires project-local Node or GEMINI_NODE_COMMAND")
    if not path.is_file():
        raise FileNotFoundError("Gemini JS entry point is unavailable")
    package = json.loads((path.parent.parent / "package.json").read_text(encoding="utf-8"))
    if package.get("name") != "@google/gemini-cli" or package.get("version") != CLI_VERSION:
        raise ValueError(f"Gemini adapter requires official CLI {CLI_VERSION}")
    return node, str(path)


def auth_configuration() -> tuple[bool, str]:
    """Refuse the retired individual free route, even with a cached Google session.

    Google announced the retirement in gemini-cli discussion #28017. Enterprise
    and API-key access are different billing routes and are not mapped here.
    """
    if any(os.getenv(name) for name in AUTH_OVERRIDES):
        return False, "Gemini API/Vertex/auth override conflicts with Google-account access"
    return False, INDIVIDUAL_ACCESS_RETIRED


def build_command(config: ExternalAgentConfig) -> tuple[str, ...]:
    """Require shared tools; native tools and broad permission flags are excluded."""
    if config.shared_tool_profile not in {"inspection", "coding"}:
        raise NotImplementedError("Gemini CLI requires the shared inspection or coding profile")
    if config.sandbox != "read-only":
        raise ValueError("Gemini shared tools require the read-only native-tool contract")
    if config.shared_tool_profile == "inspection" and config.approval_policy != "read_only":
        raise ValueError("Gemini inspection requires read_only")
    if (
        config.resume
        or config.output_last_message_path
        or config.output_schema_path
        or config.web_search
        or config.image_paths
        or config.codex_mcp_tools
    ):
        raise NotImplementedError("Codex-specific options are not mapped for Gemini CLI")
    if not config.json_output or config.model == "auto":
        raise ValueError("Gemini requires stream JSON and an explicit model")
    return (
        *command_prefix(config.command),
        "--model",
        config.model,
        "--output-format",
        "stream-json",
        "--approval-mode",
        "default",
        "--extensions",
        "none",
        "--allowed-mcp-server-names",
        "repo_shared",
        "--skip-trust",
        "--prompt",
        "Follow the complete task and history supplied on stdin.",
    )


def shared_settings(config: ExternalAgentConfig) -> dict[str, Any]:
    from ai_provider.external_agents import _shared_run_context
    from ai_provider.shared_client_tools import inspection_server, run_tool_names

    run = _shared_run_context(config)
    server = {
        **inspection_server(config.cwd, run),
        "trust": True,
        "includeTools": list(run_tool_names(run, config.cwd)),
    }
    if run and run.host_url and run.token_env:
        server["env"] = {run.token_env: "${" + run.token_env + "}"}
    return {
        "mcpServers": {"repo_shared": server},
        "mcp": {"allowed": ["repo_shared"], "serverCommand": ""},
        "tools": {"core": [], "discoveryCommand": "", "callCommand": ""},
        "security": {"auth": {"selectedType": "oauth-personal", "enforcedType": "oauth-personal"}},
        "general": {"enableAutoUpdate": False, "enableAutoUpdateNotification": False},
        "advanced": {"ignoreLocalEnv": True},
        "hooksConfig": {"enabled": False},
        "skills": {"enabled": False},
        "telemetry": {"enabled": False, "logPrompts": False},
        "ide": {"enabled": False},
        "experimental": {"autoMemory": False},
    }


@contextmanager
def invocation(config: ExternalAgentConfig) -> Iterator[ExternalAgentConfig]:
    """Create exclusive project settings; never overwrite a native configuration.

    Gemini 0.64.0 rejects user-owned Windows system settings. Use ordinary project
    settings and preflight the effective merge instead of weakening its ACL check.
    """
    build_command(config)
    environment = dict(
        config.shared_child_env if config.shared_child_env is not None else os.environ
    )
    if any(environment.get(name) for name in AUTH_OVERRIDES):
        raise ValueError("Gemini API/Vertex/auth override conflicts with Google-account access")
    directory = config.cwd / ".gemini"
    if not directory.resolve().is_relative_to(config.cwd.resolve()):
        raise ValueError("Gemini project settings leave the workspace")
    existed = directory.exists()
    directory.mkdir(exist_ok=True)
    path = directory / "settings.json"
    content = json.dumps(shared_settings(config))
    created = False
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(content)
        created = True
        environment.update({"GEMINI_CLI_NO_RELAUNCH": "1", "GEMINI_CLI_TRUST_WORKSPACE": "true"})
        yield replace(config, shared_child_env=environment)
    finally:
        if created and path.is_file() and path.read_text(encoding="utf-8") == content:
            path.unlink()
        if not existed:
            try:
                directory.rmdir()
            except OSError:
                pass


def verify_effective_settings(config: ExternalAgentConfig) -> None:
    """Ask the pinned client's loader to confirm restrictions without auth/inference."""
    node, entry = command_prefix(config.command)
    # The bundle import is pinned along with CLI_VERSION. The loader reads settings,
    # not credential contents; emit booleans only and never raw configuration.
    probe = """
import {pathToFileURL} from 'node:url';
import {dirname, resolve} from 'node:path';
const {loadSettings} = await import(pathToFileURL(resolve(dirname(process.argv[1]),
  'chunk-QCHFD56F.js')));
const loaded = loadSettings(process.cwd());
const s = loaded.merged;
const server = s.mcpServers?.repo_shared;
const expected = JSON.parse(process.env.AI_PROJECTS_GEMINI_SETTINGS);
const expectedServer = expected.mcpServers.repo_shared;
if (expectedServer.env) {
  for (const [name, value] of Object.entries(expectedServer.env)) {
    expectedServer.env[name] = value.replace(/\\$\\{([^}]+)\\}/g,
      (_, key) => process.env[key] ?? '');
  }
}
const equal = (a,b) => JSON.stringify(a) === JSON.stringify(b);
const ok = equal(s.tools?.core, []) && !s.tools?.discoveryCommand && !s.tools?.callCommand
  && s.hooksConfig?.enabled === false && s.skills?.enabled === false
  && s.advanced?.ignoreLocalEnv === true && s.general?.enableAutoUpdate === false
  && s.security?.auth?.selectedType === 'oauth-personal'
  && s.security?.auth?.enforcedType === 'oauth-personal'
  && s.telemetry?.enabled === false && s.telemetry?.logPrompts === false
  && s.ide?.enabled === false
  && (!expected.model || s.model?.maxSessionTurns === expected.model.maxSessionTurns)
  && server?.command === expectedServer.command && equal(server?.args, expectedServer.args)
  && equal(server?.includeTools, expectedServer.includeTools) && server?.trust === true
  && equal(server?.env ?? {}, expectedServer.env ?? {})
  && !loaded.errors.some(e => e.severity === 'error');
process.stdout.write(JSON.stringify({safe:ok}));
process.exitCode = ok ? 0 : 1;
"""
    environment = dict(config.shared_child_env or os.environ)
    environment["AI_PROJECTS_GEMINI_SETTINGS"] = json.dumps(shared_settings(config))
    version = _owned_diagnostic((node, "--version"), config, min(5, config.timeout_seconds))
    if version.returncode or version.stdout.strip() != NODE_VERSION:
        raise ValueError(f"Gemini adapter requires Node {NODE_VERSION}")
    result = _owned_diagnostic(
        (node, "--input-type=module", "-e", probe, entry),
        replace(config, shared_child_env=environment),
        min(10, config.timeout_seconds),
    )
    if result.returncode or result.stdout.strip() != '{"safe":true}':
        raise ValueError("Gemini effective settings do not satisfy the shared-tool/auth contract")


def _owned_diagnostic(
    command: tuple[str, ...],
    config: ExternalAgentConfig,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    with owned_processes(subprocess.Popen) as start:
        process = start(
            command,
            cwd=config.cwd,
            env=config.shared_child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


@contextmanager
def owned_processes(factory: Any) -> Iterator[Any]:
    """Assign the child to the existing OS job/group before it can spawn tools."""
    children: list[tuple[Any, WindowsJob | None]] = []

    def start(*args: Any, **kwargs: Any) -> Any:
        kwargs.update(
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x4)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
        process = factory(*args, **kwargs)
        job = None
        children.append((process, None))
        if os.name == "nt":
            from ctypes import wintypes

            job = WindowsJob(process)
            children[-1] = (process, job)
            native = ctypes.WinDLL("ntdll")
            native.NtResumeProcess.argtypes = [wintypes.HANDLE]
            native.NtResumeProcess.restype = ctypes.c_long
            if native.NtResumeProcess(cast(Any, process)._handle) != 0:
                raise OSError("Unable to resume owned Gemini child")
        return process

    try:
        yield start
    finally:
        verified = True
        for process, job in children:
            if job:
                verified = job.stop(2) and verified
            elif os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
        if not verified:
            raise OSError("Gemini owned process-tree cleanup could not be verified")


def parse_events(text: str) -> ExternalAgentEventSummary:
    """Normalize Gemini stream events without treating tool text as a route failure."""
    from ai_provider.external_agents import ExternalAgentEventSummary

    chunks: list[str] = []
    tools: list[dict[str, Any]] = []
    errors: list[str] = []
    failure = None
    usage = None
    completed = False
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("event must be an object")
        except ValueError:
            errors.append("Invalid Gemini JSON event")
            continue
        kind = event.get("type")
        if kind == "message" and event.get("role") == "assistant":
            content = event.get("content")
            if isinstance(content, str):
                if event.get("delta") is not True:
                    chunks.clear()
                chunks.append(content)
        elif kind in {"tool_use", "tool_result"}:
            tools.append(event)
            if kind == "tool_use":
                chunks.clear()
        elif kind == "error" and event.get("severity") != "warning":
            failure = str(event.get("message") or "Gemini reported an error")
        elif kind == "result":
            completed = True
            if event.get("status") != "success":
                error = event.get("error")
                failure = str(
                    error.get("message")
                    if isinstance(error, dict)
                    else error or "Gemini reported an unsuccessful result"
                )
            stats = event.get("stats")
            if isinstance(stats, dict):
                usage = {"source": "gemini_cli", "scope": "session", "native_stats": stats}
                for source, target in (
                    ("input_tokens", "input_tokens"),
                    ("output_tokens", "output_tokens"),
                    ("total_tokens", "total_tokens"),
                    ("cached", "cached_input_tokens"),
                ):
                    value = stats.get(source)
                    if type(value) is int and value >= 0:
                        usage[target] = value
    if not completed or errors:
        failure = failure or "Gemini stream incomplete or invalid"
    return ExternalAgentEventSummary(
        "".join(chunks).strip() or None, (), tuple(tools), (), (), usage, failure, tuple(errors)
    )


def redact_user_echoes(text: str) -> str:
    """Keep native diagnostic events without duplicating the full model input in logs."""
    lines = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            lines.append(line)
            continue
        if (
            isinstance(event, dict)
            and event.get("type") == "message"
            and event.get("role") == "user"
        ):
            event["content"] = "[user input omitted]"
            line = json.dumps(event)
        lines.append(line)
    return "\n".join(lines)
