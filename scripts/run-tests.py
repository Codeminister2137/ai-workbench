"""Run explicit component suites without replacing the final workspace check.

Council and job-search use legacy top-level imports and run in separate pytest
processes. Live suites retain their existing environment opt-ins.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Git exports these into hooks. Fixture commands must discover their own repos.
# https://git-scm.com/docs/githooks (foreign-repository environment boundary)
_GIT_REPOSITORY_ENV = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_OBJECT_DIRECTORY",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_GRAFT_FILE",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_REPLACE_REF_BASE",
        "GIT_PREFIX",
        "GIT_INTERNAL_SUPER_PREFIX",
        "GIT_SHALLOW_FILE",
        "GIT_COMMON_DIR",
    }
)
GROUPS = {
    "provider": (
        "tests/test_ai_provider_*.py",
        "tests/test_provider_*.py",
        "tests/test_baseten_adapter.py",
        "tests/test_ollama_*.py",
        "tests/test_openai_compatible_adapter.py",
        "tests/test_requesty_free_models.py",
        "tests/test_openrouter_free_models.py",
        "tests/test_reviewed_input.py",
        "tests/test_openrouter_usage.py",
        "tests/test_openrouter_endpoints.py",
        "tests/test_swe_bench_scores.py",
        "tests/test_aider_polyglot_scores.py",
        "tests/test_capability_bands.py",
        "tests/test_route_family_matcher.py",
        "tests/test_local_capabilities.py",
        "tests/test_local_ollama_latency_example.py",
        "tests/test_meta_responses_adapter.py",
        "tests/test_modal_runtime.py",
        "tests/test_codex_usage.py",
        "tests/test_copilot_usage.py",
        "tests/test_kiro_usage.py",
        "tests/test_turn_usage.py",
        "tests/test_source_info.py",
        "tests/test_go_source_info.py",
        "tests/test_opencode_go_adapter.py",
        "tests/test_opencode_go_protocol_adapters.py",
        "tests/test_opencode_go_route.py",
        "tests/test_wb_bounds_guard.py",
        "tests/test_wb_exec_sandbox.py",
        "tests/test_adapter_body_bounds.py",
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
        "tests/test_model_output_recovery.py",
        "tests/test_ide_bridge*.py",
        "tests/test_ide_independent_capabilities.py",
        "tests/test_foreground*.py",
        "tests/test_python_runtime_tool.py",
        "tests/test_validation_process_ownership.py",
        "tests/test_shell_process_ownership.py",
        "tests/test_pid_publication.py",
        "tests/test_shared*.py",
        "tests/test_hosted_delegation_acceptance.py",
        "tests/test_hosted_delegation_controller.py",
        "tests/test_delegation_scope.py",
        "tests/test_fanout_policy.py",
        "tests/test_semantic_refactor.py",
        "tests/test_coding_sessions.py",
        "tests/test_codex_mcp_config.py",
        "tests/test_native_admission.py",
        "tests/test_measured_prefix_admission.py",
        "tests/test_operator_bridge.py",
        "tests/test_wb_env_narrow.py",
    ),
    "cli": (
        "tests/repo_assistant/test_*.py",
        "tests/test_external_agents.py",
        "tests/test_native_diagnostic_ownership.py",
        "tests/test_gemini_cli.py",
        "tests/test_execution_fallback.py",
        "tests/test_free_provider_fallback.py",
        "tests/test_agent_readiness_ownership.py",
        "tests/test_alternate_agent_routes.py",
        "tests/test_fallback*.py",
        "tests/test_bounded_acceptance_controller.py",
        "tests/test_opencode_go_coding_chat_acceptance.py",
        "tests/test_chat_transcripts.py",
        "tests/test_user_config.py",
        "tests/test_coding_assist_example.py",
        "tests/test_codex_cli_executor_example.py",
        "tests/test_live_delegation_runner_example.py",
        "tests/test_test_suites.py",
        "tests/test_workstation_resources.py",
        "tests/test_workstation_sleep.py",
        "tests/test_sampling_controls.py",
        "tests/test_meta_develop_launcher.py",
        "tests/test_meta_supervised_develop.py",
        "tests/test_loop_notify.py",
        "tests/test_loop_status.py",
        "tests/test_sender_unify.py",
        "tests/test_mail_digest.py",
        "tests/test_loop_resume.py",
        "tests/test_baseten_receipts.py",
        "tests/test_baseten_model_resolve.py",
        "tests/test_wake_on_lan.py",
        "tests/test_day_cycle.py",
        "tests/test_l3_ladder.py",
        "tests/test_install_workbench.py",
        "tests/test_scrutiny_response_guard.py",
        "tests/test_watchdog_tasks.py",
        "tests/test_triage_apply.py",
        "tests/test_slice_develop_core.py",
    ),
    "research": (
        "tests/test_research_*.py",
        "tests/test_acceptance_jobs.py",
        "tests/test_acceptance_usage.py",
    ),
    "council": ("apps/ai_council/tests/test_*.py",),
    "dashboard": ("apps/workbench_dashboard/tests/test_*.py",),
    "job-search": ("apps/job_search/job-email/test_*.py",),
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
        for directory in (root / "tests", root / "apps", root / "packages")
        for path in directory.rglob("test_*.py")
        if not any(
            part.startswith(".") or part == "__pycache__"
            for part in path.relative_to(directory).parts
        )
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
    labels = []
    for label in ("workspace", "council", "job-search"):
        paths = sorted(
            {
                path
                for name in selected
                if (name if name in {"council", "job-search"} else "workspace") == label
                for path in groups[name]
            }
        )
        if paths:
            commands.append([sys.executable, "-m", "pytest", *paths, *extra])
            labels.append(label)
    if len(commands) > 1:
        # Separate processes must not overwrite each other's CI test report.
        for label, command in zip(labels, commands, strict=True):
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


def command_label(command: list[str]) -> str:
    """Infer the summary-table label from pytest module paths (display only)."""
    for path in command:
        normalized = path.replace("\\", "/")
        if normalized.startswith("apps/ai_council/"):
            return "council"
        if normalized.startswith("apps/job_search/"):
            return "job-search"
    return "workspace"


def test_environment() -> dict[str, str]:
    """Isolate fixture repositories while preserving ordinary test/tool settings."""
    return {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in _GIT_REPOSITORY_ENV
        and not name.upper().startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))
    }


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
        rows: list[tuple[str, int, int, float]] = []
        for command in test_commands(args.groups or ["full"], extra):
            label = command_label(command)
            modules = len(command) - 3 - len(extra)
            print(f"Running {label}: {modules} test modules", flush=True)
            started = time.monotonic()
            result = subprocess.run(command, cwd=ROOT, env=test_environment(), check=False)
            elapsed = time.monotonic() - started
            rows.append((label, modules, result.returncode, elapsed))
            if result.returncode and not status:
                status = result.returncode
        print("group      modules  result   seconds")
        for label, modules, code, elapsed in rows:
            outcome = "ok" if code == 0 else f"FAIL({code})"
            print(f"{label:<10} {modules:<7} {outcome:<8} {elapsed:.1f}")
        return status
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
