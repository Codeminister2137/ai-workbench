"""Opt-in synthetic Codex-limit simulation followed by a real whole-set fallback.

The initial ``simulated-codex`` route is failed synthetically so no real initial
quota is spent. Every configured fallback route then runs for real, in the given
order, until one completes. The harness records the session's ready set and the
exact attempt sequence, so a run proves both that the whole candidate set was
held and that the walk followed the configured order.
"""

import argparse
import ast
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ai_agent import repo_coding_assistant as cli
from ai_agent.contracts import ToolCall
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.shared_approvals import scoped_registry
from ai_agent.tool_profiles import shared_tool_registry
from ai_agent.tools import ToolContext
from ai_orchestrator import AccessMethod
from ai_provider import execution_fallback
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.coding_sessions import ACTIVE_SESSION
from ai_provider.external_agents import ExternalAgentResult, parse_external_agent_jsonl

SIMULATED_INITIAL = {
    "route_id": "simulated-codex",
    "provider": "openai",
    "product": "codex",
    "model": "test",
    "access_method": "codex_cli",
    "auth_method": "chatgpt_sign_in",
    "billing_source": "chatgpt_subscription_allowance",
    "cost_policy_tier": "allowances_allowed",
    "quality": "standard",
}

# Real fallback sources, ordered by the caller. The free route is first-class:
# a cheaper tier is admissible from an allowance initial, and a free route with
# a capable model and enough allowance is preferred because it spends nothing.
FALLBACK_ROUTES = {
    "requesty-free": {
        "route_id": "requesty/free-google/gemma-4-31b-it",
        "provider": "requesty",
        "product": "requesty_free",
        "model": "google/gemma-4-31b-it",
        "access_method": "provider_api",
        "auth_method": "api_key",
        "billing_source": "requesty_billing",
        "cost_policy_tier": "free_only",
        "quality": "standard",
    },
    "openrouter-free": {
        "route_id": "openrouter/free-google/gemma-4-31b-it:free",
        "provider": "openrouter",
        "product": "openrouter_free",
        "model": "google/gemma-4-31b-it:free",
        "access_method": "provider_api",
        "auth_method": "api_key",
        "billing_source": "openrouter_free",
        "cost_policy_tier": "free_only",
        "quality": "standard",
    },
    "opencode-go": {
        "route_id": "opencode-go/go-kimi-k2.7-code",
        "provider": "opencode_go",
        "product": "go",
        "model": "kimi-k2.7-code",
        "access_method": "provider_api",
        "auth_method": "api_key",
        "billing_source": "opencode_go_subscription_allowance",
        "cost_policy_tier": "allowances_allowed",
        "quality": "high",
    },
    "kiro": {
        "route_id": "kiro/auto",
        "provider": "kiro",
        "product": "kiro",
        "model": "auto",
        "access_method": "kiro_cli",
        "auth_method": "kiro_sign_in",
        "billing_source": "kiro_subscription_allowance",
        "cost_policy_tier": "allowances_allowed",
        "quality": "standard",
    },
    "copilot": {
        "route_id": "github/copilot-cli-auto",
        "provider": "github",
        "product": "github_copilot",
        "model": "auto",
        "access_method": "copilot_cli",
        "auth_method": "github_account_sign_in",
        "billing_source": "github_copilot_subscription_allowance",
        "cost_policy_tier": "allowances_allowed",
        "quality": "standard",
    },
}


# Only external-client routes can carry a synthetic limit, because the harness
# intercepts their process result. Provider-API routes have no such seam, so they
# always run for real.
SIMULATABLE_LIMITS = {
    "kiro": AccessMethod.KIRO_CLI,
    "copilot": AccessMethod.COPILOT_CLI,
}


def route_block(spec: dict[str, str]) -> str:
    """Render one catalog entry with the capabilities the fixture requires."""
    values = {"location": "external", **spec}
    return (
        "[[models]]\n"
        + "".join(f'{key} = "{value}"\n' for key, value in values.items())
        + "[models.capabilities]\nchat = true\ntools = true\n"
    )


def valid_source(text: str) -> bool:
    """Check the fixed assignment without executing candidate code."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    return (
        len(tree.body) == 1
        and isinstance(tree.body[0], ast.Assign)
        and len(tree.body[0].targets) == 1
        and isinstance(tree.body[0].targets[0], ast.Name)
        and tree.body[0].targets[0].id == "value"
        and isinstance(tree.body[0].value, ast.Constant)
        and type(tree.body[0].value.value) is int
        and tree.body[0].value.value == 2
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-coding", action="store_true")
    parser.add_argument("--shared-process", action="store_true")
    parser.add_argument(
        "--fallback-route",
        action="append",
        choices=tuple(FALLBACK_ROUTES),
        help=(
            "Real fallback source to try, in the order given; repeat the flag for the "
            "whole ordered set. Every listed route runs for real until one completes."
        ),
    )
    parser.add_argument(
        "--fallback-client",
        action="append",
        choices=("copilot", "kiro"),
        help="Deprecated alias for --fallback-route limited to CLI clients.",
    )
    parser.add_argument(
        "--simulate-limit-on",
        action="append",
        choices=tuple(SIMULATABLE_LIMITS),
        default=[],
        help=(
            "Return a synthetic usage-limit result for this fallback route so the walk "
            "must continue to the next configured candidate. Every other route still "
            "runs for real; the simulated route is recorded in the result."
        ),
    )
    args = parser.parse_args()
    args.fallback_route = tuple(args.fallback_route or args.fallback_client or ("copilot",))
    unlisted = [name for name in args.simulate_limit_on if name not in args.fallback_route]
    if unlisted:
        parser.error(
            "--simulate-limit-on requires the route in --fallback-route: " + ", ".join(unlisted)
        )
    if args.shared_process:
        args.shared_coding = True
    root = Path(__file__).resolve().parents[1]
    artifact = (
        root / "artifacts" / ("fallback-acceptance-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))
    )
    artifact.mkdir(parents=True)
    source = artifact / "source.py"
    source.write_text("value = 0\n", encoding="utf-8")
    tests = artifact / "test_source.py"
    original_tests = "from source import value\nassert value == 2, value\n"
    tests.write_text(original_tests, encoding="utf-8")
    (artifact / "AGENTS.md").write_text(
        "Synthetic acceptance fixture. Edit only source.py; preserve other files. "
        "No network, external services, delegation, or files outside this directory.\n",
        encoding="utf-8",
    )
    catalog = artifact / "catalog.toml"
    chosen = [FALLBACK_ROUTES[name] for name in args.fallback_route]
    catalog.write_text(
        route_block(SIMULATED_INITIAL) + "".join(route_block(spec) for spec in chosen),
        encoding="utf-8",
    )
    protected_content = {
        name: (artifact / name).read_bytes()
        for name in ("AGENTS.md", "test_source.py", "catalog.toml")
    }
    local_copilot = root / ".tools" / "copilot" / "copilot.exe"
    if local_copilot.exists():
        os.environ.setdefault("GITHUB_COPILOT_COMMAND", str(local_copilot))
    # Only command construction uses this; the simulated Codex route never spawns it.
    os.environ.setdefault("CODEX_COMMAND", "codex-simulated")
    baseline = subprocess.run((sys.executable, str(tests)), cwd=artifact, capture_output=True)
    assert baseline.returncode != 0
    real_execute = cli._run_external_agent
    real_auth = execution_fallback.check_agent_readiness
    attempts = []
    owned_session = None
    process_handle = None
    owned_foreground = None
    recorded_sessions = []
    real_session = cli.FallbackSession

    class RecordingSession(real_session):
        """Keep the finished session so its ready set and attempts can be asserted."""

        def __init__(self, *session_args, **session_kwargs):
            super().__init__(*session_args, **session_kwargs)
            recorded_sessions.append(self)

    cli.FallbackSession = RecordingSession
    simulated_limit_methods = {SIMULATABLE_LIMITS[name] for name in args.simulate_limit_on}

    def execute(prompt, config, **kwargs):
        nonlocal owned_session, process_handle, owned_foreground
        attempts.append(config.access_method.value)
        if config.access_method is AccessMethod.CODEX_CLI:
            partial = "# Partial work before simulated quota exhaustion\nvalue = 1\n"
            if args.shared_coding:
                session = ACTIVE_SESSION.get()
                assert session is not None
                if args.shared_process:
                    from ai_provider.foreground_tools import ACTIVE_FOREGROUND

                    owned_foreground = ACTIVE_FOREGROUND.get()
                    owned_session = session
                    # Host-controlled fixture setup is separate from agent shell authority.
                    process_handle = session.supervisor.start(
                        [
                            sys.executable,
                            "-u",
                            "-c",
                            "import time; print('continuation-child', flush=True); time.sleep(180)",
                        ]
                    )
                    session.observe_process(session.supervisor.status(process_handle))
                registry = scoped_registry(
                    shared_tool_registry("coding"),
                    PermissionManager(PermissionPolicy.from_approval_preset("workspace_write")),
                    artifact,
                    session.session_id,
                    config.shared_run_id,
                )
                registry = session.observe_registry(
                    registry,
                    operation_prefix=f"shared:{session.session_id}:{config.shared_run_id}:",
                )
                assert not registry.execute(
                    ToolCall("read_file", {"path": "source.py"}), ToolContext(artifact)
                ).is_error
                assert not registry.execute(
                    ToolCall("edit_file", {"path": "source.py", "new_text": partial}),
                    ToolContext(artifact),
                ).is_error
            else:
                source.write_text(partial, encoding="utf-8")
            event = json.dumps({"type": "error", "message": "You've hit your usage limit"})
            return ExternalAgentResult(
                ("simulated-codex",), 1, event + "\n", "", events=parse_external_agent_jsonl(event)
            )
        assert "Route-failure continuation" in prompt
        assert "value = 1" in source.read_text(encoding="utf-8")
        if config.access_method in simulated_limit_methods:
            # Declared synthetic limit on a *fallback* route: the walk must continue
            # to the next configured candidate, which then runs for real.
            event = json.dumps({"type": "error", "message": "You've hit your usage limit"})
            return ExternalAgentResult(
                (config.command,), 1, event + "\n", "", events=parse_external_agent_jsonl(event)
            )
        return real_execute(prompt, config, **kwargs)

    cli._run_external_agent = execute
    execution_fallback.check_agent_readiness = lambda method: (
        AgentReadiness(True, "simulated initial account")
        if method is AccessMethod.CODEX_CLI
        else real_auth(method)
    )
    try:
        exit_code = cli.main(
            [
                "--mode",
                "implement",
                "Set value to 2 in source.py. Preserve existing comments. "
                + (
                    "Do not run commands; the host will validate. "
                    if args.shared_coding
                    else "Run test_source.py to verify. "
                )
                + "Do not edit the test or other fixture files. "
                + (
                    "If a running process is recorded in the coding-session handoff, "
                    "call process_status on that exact handle and confirm its running state. "
                    "Do not start a replacement process or stop it; the host will clean up."
                    if args.shared_process
                    else ""
                ),
                "--repo-root",
                str(artifact),
                "--catalog",
                str(catalog),
                "--route-id",
                "simulated-codex",
                "--privacy",
                "public_or_low_risk",
                "--cost-policy",
                "allowances_allowed",
                "--fallback-quality-policy",
                "task_minimum",
                *[item for spec in chosen for item in ("--fallback-priority", spec["route_id"])],
                "--approval-policy",
                "workspace_write" if args.shared_coding else "trusted_local",
                *(
                    [
                        "--shared-tools",
                        "coding",
                        "--coding-session",
                        "new",
                        "--coding-session-db",
                        str(artifact / "session.sqlite3"),
                    ]
                    if args.shared_coding
                    else []
                ),
                "--away-minutes",
                "5",
                "--skip-prompt-review",
                "--execute",
                # The default of 3 action rounds is enough for a strong model but
                # not for a weak free route, which can spend all three on listing,
                # reading and editing before it can run the test. Keep the bound
                # finite and small, but large enough to measure the route rather
                # than the round limit.
                "--max-action-rounds",
                "6",
                "--timeout-seconds",
                "180",
                "--log-file",
                str(artifact / "assistant.log"),
            ]
        )
    finally:
        cli._run_external_agent = real_execute
        cli.FallbackSession = real_session
        execution_fallback.check_agent_readiness = real_auth
    # Validate the tiny assignment without executing model-authored Python.
    source_valid = valid_source(source.read_text(encoding="utf-8"))
    completed_edits = []
    completed_process_polls = []
    if args.shared_coding:
        with sqlite3.connect(artifact / "session.sqlite3") as connection:
            completed_edits = [
                row[0]
                for row in connection.execute(
                    "SELECT operation FROM coding_receipts "
                    "WHERE status='completed' AND operation LIKE 'shared:%:edit_file:%'"
                )
            ]
            completed_process_polls = [
                row[0]
                for row in connection.execute(
                    "SELECT operation FROM coding_receipts "
                    "WHERE status='completed' AND operation LIKE 'shared:%:process_status:%'"
                )
            ]
    child_cleaned = (
        owned_session is not None
        and process_handle is not None
        and owned_session.supervisor.status(process_handle)["returncode"] is not None
    )
    edit_runs = [operation.split(":")[2] for operation in completed_edits]
    protected_unchanged = all(
        (artifact / name).read_bytes() == content for name, content in protected_content.items()
    )
    configured_order = ["simulated-codex", *[spec["route_id"] for spec in chosen]]
    finished = recorded_sessions[-1] if recorded_sessions else None
    ready_routes = list(finished.ready) if finished is not None else []
    unavailable_routes = dict(finished.unavailable) if finished is not None else {}
    session_attempts = list(finished.attempts) if finished is not None else []
    attempt_routes = [attempt["route_id"] for attempt in session_attempts]
    # The session must enumerate the whole configured set: every configured route
    # is either held in the ready set or explicitly recorded as unavailable with a
    # reason. A route that is neither was silently dropped, which is the defect
    # this harness exists to catch.
    unaccounted_routes = [
        route_id
        for route_id in configured_order[1:]
        if route_id not in ready_routes and route_id not in unavailable_routes
    ]
    whole_set_held = bool(configured_order[1:]) and not unaccounted_routes
    # Only routes the session actually held can be walked; an unconfigured client
    # is correctly absent from the ready set rather than silently skipped.
    available_order = [
        route_id
        for route_id in configured_order
        if route_id == "simulated-codex" or route_id in ready_routes
    ]
    walked_configured_order = attempt_routes == available_order[: len(attempt_routes)]
    fallback_hops = max(len(session_attempts) - 1, 0)
    walked_whole_set = (
        walked_configured_order
        and whole_set_held
        and fallback_hops >= 1
        and bool(session_attempts)
        and session_attempts[-1]["status"] == "finished"
    )
    passed = (
        exit_code == 0
        and source_valid
        and (not args.shared_coding or len(edit_runs) == len(set(edit_runs)) == 2)
        and tests.read_text(encoding="utf-8") == original_tests
        and protected_unchanged
        and "Partial work" in source.read_text(encoding="utf-8")
        and walked_whole_set
        and (not args.shared_process or (completed_process_polls and child_cleaned))
    )
    result = {
        "passed": passed,
        "simulated_initial_quota": True,
        "configured_fallback_order": configured_order,
        "simulated_usage_limit_routes": [
            FALLBACK_ROUTES[name]["route_id"] for name in args.simulate_limit_on
        ],
        "ready_routes": ready_routes,
        "unavailable_routes": unavailable_routes,
        "unaccounted_routes": unaccounted_routes,
        "session_attempts": session_attempts,
        "walked_configured_order": walked_configured_order,
        "whole_set_held": whole_set_held,
        "fallback_hops": fallback_hops,
        "attempts": attempts,
        "exit_code": exit_code,
        "source_validation_passed": source_valid,
        "completed_shared_edits": len(completed_edits),
        "shared_edit_runs": edit_runs,
        "shared_coding": args.shared_coding,
        "shared_process": args.shared_process,
        "completed_process_polls": completed_process_polls,
        "child_cleaned": child_cleaned if args.shared_process else None,
        "foreground_http_statuses": (
            list(owned_foreground.host.request_statuses)
            if owned_foreground and owned_foreground.host
            else []
        ),
        "protected_files_unchanged": protected_unchanged,
    }
    (artifact / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("fallback_acceptance: " + json.dumps(result))
    print(f"acceptance_artifacts: {artifact}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
