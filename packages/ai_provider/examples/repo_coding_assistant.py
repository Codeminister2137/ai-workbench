from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

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


def find_repo_root(start: Path) -> Path:
    """Find the nearest Git repository root at or above start."""

    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


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
        help="Explicitly allow selected files outside the repository without prompting.",
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
        default=(
            "You are a repo-aware coding assistant. Use the provided repository "
            "context, preserve the permission boundary, and do not claim to have "
            "edited or executed files unless explicitly given evidence."
        ),
        help="Provider-neutral system instruction sent before the user prompt.",
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
        system_prompt=args.system,
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
    elif result.orchestration.failure_reason:
        print(f"failure_reason: {result.orchestration.failure_reason}")
    elif result.orchestration.prompt_judge and result.orchestration.prompt_judge.should_refine:
        for issue in result.orchestration.prompt_judge.issues:
            print(f"prompt_issue: {issue.severity.value} {issue.code}: {issue.message}")
        if result.orchestration.prompt_judge.refined_prompt:
            print(f"suggested_prompt: {result.orchestration.prompt_judge.refined_prompt}")
    return 0


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


if __name__ == "__main__":
    sys.exit(main())
