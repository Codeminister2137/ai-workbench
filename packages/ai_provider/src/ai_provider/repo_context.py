from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_provider.repo_actions import (
    confirm_outside_read,
    display_path,
    is_relative_to,
    resolve_context_path,
)

DEFAULT_CONTEXT_BUDGET_CHARS = 5_000
DEFAULT_CONTEXT_FILE_BUDGET_CHARS = 2_500
DEFAULT_INSTRUCTION_BUDGET_CHARS = 64_000
BASE_SYSTEM_PROMPT = """
You are a repo-aware coding assistant. Use the provided repository context,
preserve the permission boundary, and do not claim to have edited or executed
files unless an action result proves it.
""".strip()

ANSWER_ONLY_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + "\n\n"
    + """
Provide the best answer you can from the supplied context. Do not emit local
action JSON or ask the caller to run repository tools through this response.
If more inspection or execution is needed, state the concrete next command or
file to inspect in prose.
""".strip()
)

NATIVE_TOOL_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + "\n\n"
    + """
Use the supplied provider-native tools for needed repository inspection and
authorized actions. Submit actual native tool calls; tool requests written in
response text or fenced JSON do not execute. Use observed tool results to decide
what to do next and report what changed and which checks actually passed.
Respect denied operations and scoped approvals; do not use another tool to evade
a denial. If a needed operation is unavailable, explain the concrete limitation.
""".strip()
)

TOOL_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + "\n\n"
    + """

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
)


@dataclass(frozen=True, slots=True)
class RepoContextFile:
    """One file approved for inclusion in a repo-aware prompt."""

    path: Path
    display_path: str
    content: str
    inside_repo: bool
    required_instruction: bool = False


def find_repo_root(start: Path) -> Path:
    """Find the nearest Git repository root at or above start."""

    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


def build_default_system_prompt(
    extra_system_prompt: str | None = None,
    *,
    actions_enabled: bool = True,
) -> str:
    """Return the repo-aware system prompt with optional caller instructions."""

    system_prompt = TOOL_SYSTEM_PROMPT if actions_enabled else ANSWER_ONLY_SYSTEM_PROMPT
    if not extra_system_prompt:
        return system_prompt
    return f"{system_prompt}\n\nAdditional instruction:\n{extra_system_prompt.strip()}"


def build_native_tool_system_prompt(extra_system_prompt: str | None = None) -> str:
    """Describe actual native calls without the answer-only or legacy JSON workflow."""
    if not extra_system_prompt:
        return NATIVE_TOOL_SYSTEM_PROMPT
    return f"{NATIVE_TOOL_SYSTEM_PROMPT}\n\nAdditional instruction:\n{extra_system_prompt.strip()}"


def load_prompt_context(
    repo_root: Path,
    selected_paths: Sequence[Path],
    *,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    context_budget_chars: int | None = DEFAULT_CONTEXT_BUDGET_CHARS,
    context_file_budget_chars: int = DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
    instruction_budget_chars: int = DEFAULT_INSTRUCTION_BUDGET_CHARS,
    diagnostic: Callable[[str], None] | None = None,
) -> tuple[RepoContextFile, ...]:
    """Keep required instructions intact, budgeting optional snippets separately."""

    if context_budget_chars is not None and context_budget_chars <= 0:
        raise ValueError("context_budget_chars must be greater than zero or None.")
    if context_file_budget_chars <= 0:
        raise ValueError("context_file_budget_chars must be greater than zero.")
    if instruction_budget_chars <= 0:
        raise ValueError("instruction_budget_chars must be greater than zero.")

    repo_root = repo_root.resolve()

    nested_instructions: list[Path] = []
    for selected in selected_paths:
        resolved = resolve_context_path(repo_root, selected)
        if not is_relative_to(resolved, repo_root.resolve()):
            continue
        directory = resolved if resolved.is_dir() else resolved.parent
        ancestors: list[Path] = []
        while directory != repo_root.resolve() and is_relative_to(directory, repo_root.resolve()):
            ancestors.append(directory / "AGENTS.md")
            directory = directory.parent
        nested_instructions.extend(reversed(ancestors))
    instruction_paths = [repo_root / "AGENTS.md", *nested_instructions]
    required_paths = {path.resolve() for path in instruction_paths if path.is_file()}
    context_paths = [
        *instruction_paths,
        repo_root / "CURRENT_CONTEXT.md",
        *selected_paths,
    ]
    loaded: list[RepoContextFile] = []
    seen: set[Path] = set()
    for path in context_paths:
        resolved = resolve_context_path(repo_root, path)
        if resolved in seen or not resolved.exists() or not resolved.is_file():
            continue
        seen.add(resolved)
        inside_repo = is_relative_to(resolved, repo_root)
        required = resolved in required_paths
        if not inside_repo and not allow_outside_files:
            if not confirm_outside_read(resolved, input_func=input_func):
                if required:
                    raise ValueError("Required instructions were not approved: " + str(resolved))
                continue
        if required:
            used = sum(len(item.content) for item in loaded if item.required_instruction)
            with resolved.open(encoding="utf-8") as instruction_file:
                raw_content = instruction_file.read(instruction_budget_chars - used + 1)
            if used + len(raw_content) > instruction_budget_chars:
                raise ValueError(
                    f"Required instructions exceed instruction_budget_chars="
                    f"{instruction_budget_chars}: {display_path(repo_root, resolved)}. "
                    "Increase --instruction-budget-chars; instructions were not truncated."
                )
            loaded.append(
                RepoContextFile(
                    resolved, display_path(repo_root, resolved), raw_content, inside_repo, True
                )
            )
            continue
        remaining_budget = (
            None
            if context_budget_chars is None
            else max(
                context_budget_chars
                - sum(len(item.content) for item in loaded if not item.required_instruction),
                0,
            )
        )
        if remaining_budget == 0:
            if diagnostic is not None:
                diagnostic(f"context_budget_omitted: {display_path(repo_root, resolved)}")
            continue
        content_limit = context_file_budget_chars
        if remaining_budget is not None:
            content_limit = min(content_limit, remaining_budget)
        raw_content = resolved.read_text(encoding="utf-8", errors="replace")
        if len(raw_content) > content_limit and diagnostic is not None:
            diagnostic(
                f"context_file_truncated: {display_path(repo_root, resolved)} "
                f"original_chars={len(raw_content)} budget_chars={content_limit}"
            )
        loaded.append(
            RepoContextFile(
                path=resolved,
                display_path=display_path(repo_root, resolved),
                content=_limit_context_content(
                    raw_content,
                    content_limit,
                ),
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


def _limit_context_content(content: str, max_chars: int) -> str:
    """Keep the beginning and end of a file while marking omitted content."""

    if len(content) <= max_chars:
        return content
    marker = f"\n[context truncated; {len(content) - max_chars} chars]\n"
    available = max_chars - len(marker)
    if available <= 0:
        return marker[:max_chars]
    head_chars = (available + 1) // 2
    tail_chars = available // 2
    tail = content[-tail_chars:].lstrip() if tail_chars else ""
    return content[:head_chars].rstrip() + marker + tail
