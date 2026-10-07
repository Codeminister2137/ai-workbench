"""Run explicit component suites without replacing the final workspace check.

Council has a legacy top-level ``tests`` package and runs in a separate pytest
process. Live suites retain their existing environment opt-ins.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "provider": (
        "tests/test_ai_provider_*.py",
        "tests/test_ollama_*.py",
        "tests/test_openai_compatible_adapter.py",
        "tests/test_requesty_free_models.py",
        "tests/test_local_capabilities.py",
        "tests/test_local_ollama_latency_example.py",
    ),
    "orchestrator": (
        "tests/test_orchestrator_*.py",
        "tests/test_review_policy.py",
        "tests/test_task_admission.py",
        "tests/test_task_scheduler*.py",
        "tests/test_repair_progress.py",
    ),
    "agent": (
        "tests/test_ai_agent_*.py",
        "tests/test_ide_bridge*.py",
        "tests/test_foreground*.py",
        "tests/test_python_runtime_tool.py",
        "tests/test_shared*.py",
        "tests/test_semantic_refactor.py",
        "tests/test_coding_sessions.py",
        "tests/test_codex_mcp_config.py",
        "tests/test_native_admission.py",
    ),
    "cli": (
        "tests/repo_assistant/test_*.py",
        "tests/test_external_agents.py",
        "tests/test_execution_fallback.py",
        "tests/test_alternate_agent_routes.py",
        "tests/test_fallback*.py",
        "tests/test_chat_transcripts.py",
        "tests/test_user_config.py",
        "tests/test_coding_assist_example.py",
        "tests/test_codex_cli_executor_example.py",
        "tests/test_live_delegation_runner_example.py",
        "tests/test_test_suites.py",
    ),
    "research": (
        "tests/test_research_*.py",
        "tests/test_acceptance_jobs.py",
        "tests/test_acceptance_usage.py",
    ),
    "council": ("apps/ai_council/tests/test_*.py",),
    "live": ("tests/integration/test_*.py",),
}


def suite_files(root: Path = ROOT) -> dict[str, tuple[str, ...]]:
    """Fail visibly when a test is missing from or duplicated across groups."""
    groups = {
        name: tuple(
            sorted(
                {path.relative_to(root).as_posix() for glob in globs for path in root.glob(glob)}
            )
        )
        for name, globs in GROUPS.items()
    }
    owners: dict[str, list[str]] = {}
    for name, paths in groups.items():
        if not paths:
            raise ValueError(f"Empty test group: {name}")
        for path in paths:
            owners.setdefault(path, []).append(name)
    discovered = {
        path.relative_to(root).as_posix()
        for directory in (root / "tests", root / "apps/ai_council/tests")
        for path in directory.rglob("test_*.py")
    }
    missing = sorted(discovered - owners.keys())
    duplicate = sorted(path for path, names in owners.items() if len(names) > 1)
    if missing or duplicate:
        raise ValueError(f"Update GROUPS: unassigned={missing}; multiple groups={duplicate}")
    return groups


def test_commands(names: list[str], extra: list[str], *, root: Path = ROOT) -> list[list[str]]:
    groups = suite_files(root)
    selected = set(names)
    if "full" in selected:
        selected |= set(groups) - {"live"}
        selected.remove("full")
    commands = []
    for isolated_council in (False, True):
        paths = sorted(
            {
                path
                for name in selected
                if (name == "council") == isolated_council
                for path in groups[name]
            }
        )
        if paths:
            commands.append([sys.executable, "-m", "pytest", *paths, *extra])
    if len(commands) > 1:
        # Separate processes must not overwrite each other's CI test report.
        for label, command in zip(("workspace", "council"), commands, strict=True):
            for index, value in enumerate(command):
                option, separator, path = value.partition("=")
                if option not in {"--junitxml", "--junit-xml"}:
                    continue
                destination_index = index if separator else index + 1
                report = Path(path if separator else command[destination_index])
                destination = str(report.with_name(f"{report.stem}-{label}{report.suffix}"))
                command[destination_index] = (
                    option + "=" + destination if separator else destination
                )
    return commands


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    separator = arguments.index("--") if "--" in arguments else len(arguments)
    extra = arguments[separator + 1 :]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("groups", nargs="*", choices=["full", *GROUPS])
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(arguments[:separator])
    try:
        if args.list:
            for name, paths in suite_files().items():
                print(f"{name}: {len(paths)} modules")
            return 0
        status = 0
        for command in test_commands(args.groups or ["full"], extra):
            print(f"Running {len(command) - 3 - len(extra)} test modules", flush=True)
            result = subprocess.run(command, cwd=ROOT, check=False)
            if result.returncode and not status:
                status = result.returncode
        return status
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
