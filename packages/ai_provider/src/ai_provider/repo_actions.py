from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AssistantAction:
    """One proposed local action emitted by the assistant model."""

    action_type: str
    args: dict[str, object]


@dataclass(frozen=True, slots=True)
class AssistantActionResult:
    """Result of one local assistant action."""

    action_type: str
    ok: bool
    summary: str
    output: str = ""


_ACTION_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_actions(response_text: str) -> tuple[AssistantAction, ...]:
    """Extract assistant action requests from a fenced JSON block or raw JSON."""

    payloads = [match.group(1) for match in _ACTION_BLOCK_PATTERN.finditer(response_text)]
    stripped = response_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        payloads.append(stripped)

    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        raw_actions = parsed.get("actions")
        if not isinstance(raw_actions, list):
            continue
        actions: list[AssistantAction] = []
        for raw_action in raw_actions:
            if not isinstance(raw_action, dict):
                continue
            action_type = raw_action.get("type")
            if not isinstance(action_type, str):
                continue
            args = {key: value for key, value in raw_action.items() if key != "type"}
            actions.append(AssistantAction(action_type=action_type, args=args))
        return tuple(actions)
    return ()


def execute_actions(
    actions: Sequence[AssistantAction],
    repo_root: Path,
    *,
    authorize_action: Callable[[AssistantAction], bool] | None = None,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    command_timeout_seconds: float = 60.0,
) -> tuple[AssistantActionResult, ...]:
    """Execute approved local actions proposed by the assistant."""

    return tuple(
        _execute_action(
            action,
            repo_root,
            authorize_action=authorize_action,
            input_func=input_func,
            allow_outside_files=allow_outside_files,
            command_timeout_seconds=command_timeout_seconds,
        )
        for action in actions
    )


def resolve_context_path(repo_root: Path, path: Path) -> Path:
    """Resolve a possibly relative path against the repository root."""

    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def is_relative_to(path: Path, parent: Path) -> bool:
    """Return whether path is inside parent."""

    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def display_path(repo_root: Path, path: Path) -> str:
    """Return a repo-relative display path when possible."""

    if is_relative_to(path, repo_root):
        return str(path.relative_to(repo_root))
    return str(path)


def confirm_outside_read(path: Path, *, input_func: Callable[[str], str]) -> bool:
    """Ask whether an outside-repository path may be read or modified."""

    try:
        answer = input_func(f"Read file outside repository? {path} [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def format_action_results(results: Sequence[AssistantActionResult]) -> str:
    """Format local action results for model feedback."""

    sections: list[str] = ["# Action results"]
    for index, result in enumerate(results, start=1):
        status = "ok" if result.ok else "failed"
        sections.extend(
            [
                "",
                f"## {index}. {result.action_type} ({status})",
                result.summary,
            ]
        )
        if result.output:
            sections.extend(["```text", result.output.rstrip(), "```"])
    return "\n".join(sections)


def _execute_action(
    action: AssistantAction,
    repo_root: Path,
    *,
    authorize_action: Callable[[AssistantAction], bool] | None,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
    command_timeout_seconds: float,
) -> AssistantActionResult:
    if authorize_action is not None and not authorize_action(action):
        return AssistantActionResult(
            action.action_type,
            False,
            f"Skipped by approval policy: {action.action_type}",
        )
    if action.action_type == "read_file":
        return _read_file_action(action, repo_root, input_func, allow_outside_files)
    if action.action_type == "list_dir":
        return _list_dir_action(action, repo_root, input_func, allow_outside_files)
    if action.action_type == "write_file":
        return _write_file_action(action, repo_root, input_func, allow_outside_files)
    if action.action_type == "run_command":
        return _run_command_action(
            action,
            repo_root,
            input_func,
            allow_outside_files,
            command_timeout_seconds,
        )
    return AssistantActionResult(
        action_type=action.action_type,
        ok=False,
        summary=f"Unsupported action type: {action.action_type}",
    )


def _read_file_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> AssistantActionResult:
    path = _action_path(action, repo_root)
    if path is None:
        return AssistantActionResult(action.action_type, False, "read_file requires path.")
    if not _path_allowed(path, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside path: {path}")
    if not path.is_file():
        return AssistantActionResult(action.action_type, False, f"File not found: {path}")
    content = path.read_text(encoding="utf-8", errors="replace")
    return AssistantActionResult(
        action.action_type,
        True,
        f"Read {display_path(repo_root, path)}",
        content,
    )


def _list_dir_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> AssistantActionResult:
    path = _action_path(action, repo_root) or repo_root
    if not _path_allowed(path, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside path: {path}")
    if not path.is_dir():
        return AssistantActionResult(action.action_type, False, f"Directory not found: {path}")
    names = sorted(child.name for child in path.iterdir())
    return AssistantActionResult(
        action.action_type,
        True,
        f"Listed {display_path(repo_root, path)}",
        "\n".join(names),
    )


def _write_file_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> AssistantActionResult:
    path = _action_path(action, repo_root)
    content = action.args.get("content")
    if path is None or not isinstance(content, str):
        return AssistantActionResult(
            action.action_type,
            False,
            "write_file requires path and string content.",
        )
    if not _path_allowed(path, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return AssistantActionResult(
        action.action_type,
        True,
        f"Wrote {display_path(repo_root, path)}",
    )


def _run_command_action(
    action: AssistantAction,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
    command_timeout_seconds: float,
) -> AssistantActionResult:
    command = action.args.get("command")
    if not isinstance(command, str) or not command.strip():
        return AssistantActionResult(action.action_type, False, "run_command requires command.")
    cwd_value = action.args.get("cwd")
    cwd = (
        resolve_context_path(repo_root, Path(cwd_value))
        if isinstance(cwd_value, str)
        else repo_root
    )
    if not _path_allowed(cwd, repo_root, input_func, allow_outside_files):
        return AssistantActionResult(action.action_type, False, f"Skipped outside cwd: {cwd}")
    try:
        completed = subprocess.run(
            _shell_command(command),
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=command_timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return AssistantActionResult(
            action.action_type,
            False,
            f"Command timed out after {command_timeout_seconds:g}s: {command}",
        )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    return AssistantActionResult(
        action.action_type,
        completed.returncode == 0,
        f"Command exited {completed.returncode}: {command}",
        output,
    )


def _action_path(action: AssistantAction, repo_root: Path) -> Path | None:
    path_value = action.args.get("path")
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    return resolve_context_path(repo_root, Path(path_value))


def _path_allowed(
    path: Path,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> bool:
    if is_relative_to(path.resolve(), repo_root):
        return True
    if allow_outside_files:
        return True
    return confirm_outside_read(path.resolve(), input_func=input_func)


def _shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-Command", command]
    return ["/bin/sh", "-c", command]
