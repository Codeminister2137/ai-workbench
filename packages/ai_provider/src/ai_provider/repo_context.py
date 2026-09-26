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
TOOL_SYSTEM_PROMPT = """
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


@dataclass(frozen=True, slots=True)
class RepoContextFile:
    """One file approved for inclusion in a repo-aware prompt."""

    path: Path
    display_path: str
    content: str
    inside_repo: bool


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
        return TOOL_SYSTEM_PROMPT
    return f"{TOOL_SYSTEM_PROMPT}\n\nAdditional instruction:\n{extra_system_prompt.strip()}"


def load_prompt_context(
    repo_root: Path,
    selected_paths: Sequence[Path],
    *,
    input_func: Callable[[str], str] = input,
    allow_outside_files: bool = False,
    context_budget_chars: int | None = DEFAULT_CONTEXT_BUDGET_CHARS,
    context_file_budget_chars: int = DEFAULT_CONTEXT_FILE_BUDGET_CHARS,
) -> tuple[RepoContextFile, ...]:
    """Load approved context files within deterministic size budgets."""

    if context_budget_chars is not None and context_budget_chars <= 0:
        raise ValueError("context_budget_chars must be greater than zero or None.")
    if context_file_budget_chars <= 0:
        raise ValueError("context_file_budget_chars must be greater than zero.")

    context_paths = [
        repo_root / "AGENTS.md",
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
        if not inside_repo and not allow_outside_files:
            if not confirm_outside_read(resolved, input_func=input_func):
                continue
        remaining_budget = (
            None
            if context_budget_chars is None
            else max(context_budget_chars - sum(len(item.content) for item in loaded), 0)
        )
        if remaining_budget == 0:
            continue
        content_limit = context_file_budget_chars
        if remaining_budget is not None:
            content_limit = min(content_limit, remaining_budget)
        loaded.append(
            RepoContextFile(
                path=resolved,
                display_path=display_path(repo_root, resolved),
                content=_limit_context_content(
                    resolved.read_text(encoding="utf-8", errors="replace"),
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
