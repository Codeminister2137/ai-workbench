from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_orchestrator import LatencyTarget, QualityThreshold, load_model_catalog
from ai_orchestrator import PrivacyClass as OrchestratorPrivacyClass
from coding_assist import coding_task_profile, run_coding_prompt


@dataclass(frozen=True, slots=True)
class RepoContextFile:
    """One file approved for inclusion in a repo-aware prompt."""

    path: Path
    display_path: str
    content: str
    inside_repo: bool


@dataclass(frozen=True, slots=True)
class AssistantAction:
    """One proposed local action emitted by the assistant model."""

    action_type: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AssistantActionResult:
    """Result of one local assistant action."""

    action_type: str
    ok: bool
    summary: str
    output: str = ""


_ACTION_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_TOOL_SYSTEM_PROMPT = """
You are a repo-aware coding assistant. Use the provided repository context,
preserve the permission boundary, and do not claim to have edited or executed
files unless an action result proves it.

When you need local tools, emit exactly one JSON object in a fenced json block:

```json
{"actions":[{"type":"read_file","path":"relative/path.py"}]}
```

Supported action types:
- read_file: {"type":"read_file","path":"relative/path"}
- list_dir: {"type":"list_dir","path":"relative/path"}
- write_file: {"type":"write_file","path":"relative/path","content":"full file content"}
- run_command: {"type":"run_command","command":"command string","cwd":"optional/relative/path"}

Prefer the smallest useful action set. Do not invent persistent state, background
jobs, external actions, or hidden side effects.
""".strip()


def find_repo_root(start: Path) -> Path:
    """Find the nearest Git repository root at or above start."""

    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def build_default_system_prompt(extra_system_prompt: str | None = None) -> str:
    """Return the repo-aware system prompt with optional caller instructions."""

    if not extra_system_prompt:
        return _TOOL_SYSTEM_PROMPT
    return f"{_TOOL_SYSTEM_PROMPT}\n\nAdditional instruction:\n{extra_system_prompt.strip()}"


def load_prompt_context(
    repo_root: Path,
    selected_paths: Sequence[Path],
    *,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
) -> tuple[RepoContextFile, ...]:
    """Load default and user-selected context files with a repo permission boundary."""

    context_paths = [
        repo_root / "AGENTS.md",
        repo_root / "CURRENT_CONTEXT.md",
        *selected_paths,
    ]
    loaded: list[RepoContextFile] = []
    seen: set[Path] = set()
    for path in context_paths:
        resolved = _resolve_context_path(repo_root, path)
        if resolved in seen or not resolved.exists() or not resolved.is_file():
            continue
        seen.add(resolved)
        inside_repo = _is_relative_to(resolved, repo_root)
        if not inside_repo and not allow_outside_files:
            if not _confirm_outside_read(resolved, input_func=input_func):
                continue
        loaded.append(
            RepoContextFile(
                path=resolved,
                display_path=_display_path(repo_root, resolved),
                content=resolved.read_text(encoding="utf-8", errors="replace"),
                inside_repo=inside_repo,
            )
        )
    return tuple(loaded)


def build_repo_prompt(user_prompt: str, context_files: Sequence[RepoContextFile]) -> str:
    """Combine the user's request and approved repository context into one prompt."""

    sections = [
        "# User request",
        user_prompt.strip(),
        "",
        "# Repository context",
    ]
    if not context_files:
        sections.append("No repository context files were loaded.")
    for context_file in context_files:
        boundary = "inside-repo" if context_file.inside_repo else "outside-repo-approved"
        sections.extend(
            [
                "",
                f"## {context_file.display_path} ({boundary})",
                "```text",
                context_file.content.rstrip(),
                "```",
            ]
        )
    return "\n".join(sections).strip()


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
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    command_timeout_seconds: float = 60.0,
) -> tuple[AssistantActionResult, ...]:
    """Execute approved local actions proposed by the assistant."""

    return tuple(
        _execute_action(
            action,
            repo_root,
            input_func=input_func,
            allow_outside_files=allow_outside_files,
            command_timeout_seconds=command_timeout_seconds,
        )
        for action in actions
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a minimal repo-aware coding assistant request."
    )
    parser.add_argument("prompt", help="Coding prompt to prepare or execute.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="Repository root. Defaults to the nearest parent containing .git.",
    )
    parser.add_argument(
        "--file",
        action="append",
        type=Path,
        default=[],
        help="Repo file to include in the prompt. May be passed more than once.",
    )
    parser.add_argument(
        "--allow-outside-files",
        action="store_true",
        help=(
            "Explicitly allow selected files and action paths outside the repository "
            "without prompting."
        ),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("packages/ai_orchestrator/examples/model_catalog.toml"),
        help="Path to a TOML model catalog.",
    )
    parser.add_argument(
        "--privacy",
        choices=[item.value for item in OrchestratorPrivacyClass],
        default=OrchestratorPrivacyClass.LOCAL_ONLY.value,
        help="Privacy class for the request.",
    )
    parser.add_argument(
        "--quality",
        choices=[item.value for item in QualityThreshold],
        default=QualityThreshold.STANDARD.value,
        help="Minimum quality threshold.",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama", "openai", "requesty"],
        help="Hard provider override.",
    )
    parser.add_argument("--model", help="Hard model override.")
    parser.add_argument(
        "--system",
        help="Additional provider-neutral system instruction appended to the tool prompt.",
    )
    parser.add_argument("--max-latency-seconds", type=float, help="Hard latency constraint.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0, help="Provider timeout.")
    parser.add_argument(
        "--start-ollama",
        action="store_true",
        help="Start `ollama serve` before executing a local Ollama request.",
    )
    parser.add_argument(
        "--ollama-command",
        default="ollama",
        help="Ollama executable used with --start-ollama.",
    )
    parser.add_argument(
        "--ollama-startup-timeout-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait for Ollama to become reachable after starting it.",
    )
    parser.add_argument(
        "--skip-prompt-review",
        action="store_true",
        help="Bypass deterministic prompt review.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the provider request. Without this, only print the prepared plan.",
    )
    parser.add_argument(
        "--apply-actions",
        action="store_true",
        help="Execute assistant-proposed local actions after a provider response.",
    )
    parser.add_argument(
        "--max-action-rounds",
        type=int,
        default=3,
        help="Maximum provider/action follow-up rounds when --apply-actions is set.",
    )
    parser.add_argument(
        "--command-timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout for assistant-proposed local commands.",
    )
    args = parser.parse_args(argv)

    repo_root = (args.repo_root or find_repo_root(Path.cwd())).resolve()
    context_files = load_prompt_context(
        repo_root,
        args.file,
        allow_outside_files=args.allow_outside_files,
    )
    prompt = build_repo_prompt(args.prompt, context_files)
    catalog = load_model_catalog(args.catalog)
    profile = coding_task_profile(
        privacy_class=OrchestratorPrivacyClass(args.privacy),
        quality_threshold=QualityThreshold(args.quality),
        latency_target=LatencyTarget.INTERACTIVE,
        max_expected_latency_seconds=args.max_latency_seconds,
        provider_override=args.provider,
        model_override=args.model,
    )
    result = run_coding_prompt(
        prompt,
        profile,
        catalog,
        review_prompt=not args.skip_prompt_review,
        timeout_seconds=args.timeout_seconds,
        execute=args.execute,
        system_prompt=build_default_system_prompt(args.system),
        start_ollama=args.start_ollama,
        ollama_command=args.ollama_command,
        ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
    )

    print(f"repo_root: {repo_root}")
    for context_file in context_files:
        print(f"context: {context_file.display_path}")
    print(f"status: {result.orchestration.status.value}")
    if result.config is not None:
        print(f"provider: {result.config.provider.value}")
        print(f"model: {result.config.model}")
    if result.response is not None:
        print(result.response.message.content)
        if args.apply_actions:
            _run_action_loop(
                result.response.message.content,
                prompt,
                profile,
                catalog,
                args,
                repo_root,
            )
    elif result.orchestration.failure_reason:
        print(f"failure_reason: {result.orchestration.failure_reason}")
    elif result.orchestration.prompt_judge and result.orchestration.prompt_judge.should_refine:
        for issue in result.orchestration.prompt_judge.issues:
            print(f"prompt_issue: {issue.severity.value} {issue.code}: {issue.message}")
        if result.orchestration.prompt_judge.refined_prompt:
            print(f"suggested_prompt: {result.orchestration.prompt_judge.refined_prompt}")
    return 0


def _run_action_loop(
    response_text: str,
    original_prompt: str,
    profile: Any,
    catalog: Any,
    args: argparse.Namespace,
    repo_root: Path,
) -> None:
    round_index = 0
    current_response = response_text
    while round_index < args.max_action_rounds:
        actions = extract_actions(current_response)
        if not actions:
            return
        round_index += 1
        results = execute_actions(
            actions,
            repo_root,
            allow_outside_files=args.allow_outside_files,
            command_timeout_seconds=args.command_timeout_seconds,
        )
        print(_format_action_results(results))
        follow_up_prompt = (
            f"{original_prompt}\n\n# Local action results round {round_index}\n"
            f"{_format_action_results(results)}\n\n"
            "Continue from these results. If more local actions are required, emit "
            "another actions JSON block. Otherwise provide the final answer."
        )
        result = run_coding_prompt(
            follow_up_prompt,
            profile,
            catalog,
            review_prompt=not args.skip_prompt_review,
            timeout_seconds=args.timeout_seconds,
            execute=True,
            system_prompt=build_default_system_prompt(args.system),
            start_ollama=args.start_ollama,
            ollama_command=args.ollama_command,
            ollama_startup_timeout_seconds=args.ollama_startup_timeout_seconds,
        )
        if result.response is None:
            if result.orchestration.failure_reason:
                print(f"failure_reason: {result.orchestration.failure_reason}")
            return
        current_response = result.response.message.content
        print(current_response)


def _resolve_context_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _display_path(repo_root: Path, path: Path) -> str:
    if _is_relative_to(path, repo_root):
        return str(path.relative_to(repo_root))
    return str(path)


def _confirm_outside_read(path: Path, *, input_func: Callable[[str], str]) -> bool:
    try:
        answer = input_func(f"Read file outside repository? {path} [y/N]: ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _execute_action(
    action: AssistantAction,
    repo_root: Path,
    *,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
    command_timeout_seconds: float,
) -> AssistantActionResult:
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
        f"Read {_display_path(repo_root, path)}",
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
        f"Listed {_display_path(repo_root, path)}",
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
        f"Wrote {_display_path(repo_root, path)}",
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
        _resolve_context_path(repo_root, Path(cwd_value))
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
    return _resolve_context_path(repo_root, Path(path_value))


def _path_allowed(
    path: Path,
    repo_root: Path,
    input_func: Callable[[str], str],
    allow_outside_files: bool,
) -> bool:
    if _is_relative_to(path.resolve(), repo_root):
        return True
    if allow_outside_files:
        return True
    return _confirm_outside_read(path.resolve(), input_func=input_func)


def _shell_command(command: str) -> list[str]:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-Command", command]
    return ["/bin/sh", "-c", command]


def _format_action_results(results: Sequence[AssistantActionResult]) -> str:
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


if __name__ == "__main__":
    sys.exit(main())
