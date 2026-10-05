"""Opt-in synthetic Codex-limit simulation followed by a real client continuation."""

import argparse
import ast
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from ai_agent.contracts import ToolCall
from ai_agent.permissions import PermissionManager, PermissionPolicy
from ai_agent.shared_approvals import scoped_registry
from ai_agent.tool_profiles import shared_tool_registry
from ai_agent.tools import ToolContext
from ai_orchestrator import AccessMethod
from ai_provider import execution_fallback
from ai_provider import repo_coding_assistant as cli
from ai_provider.agent_readiness import AgentReadiness
from ai_provider.coding_sessions import ACTIVE_SESSION
from ai_provider.external_agents import ExternalAgentResult, parse_external_agent_jsonl


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
    parser.add_argument("--fallback-client", choices=("copilot", "kiro"), default="copilot")
    args = parser.parse_args()
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
    catalog.write_text(
        """[[models]]
route_id = "simulated-codex"
provider = "openai"
product = "codex"
model = "test"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "standard"
[models.capabilities]
chat = true
tools = true
[[models]]
route_id = "github-copilot-cli-default"
provider = "github"
product = "github_copilot"
model = "auto"
location = "external"
access_method = "copilot_cli"
auth_method = "github_account_sign_in"
billing_source = "github_copilot_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "standard"
[models.capabilities]
chat = true
tools = true
""",
        encoding="utf-8",
    )
    if args.fallback_client == "kiro":
        catalog.write_text(
            catalog.read_text(encoding="utf-8")
            .replace('route_id = "github-copilot-cli-default"', 'route_id = "kiro-cli-default"')
            .replace('provider = "github"', 'provider = "kiro"')
            .replace('product = "github_copilot"', 'product = "kiro"')
            .replace('access_method = "copilot_cli"', 'access_method = "kiro_cli"')
            .replace('auth_method = "github_account_sign_in"', 'auth_method = "kiro_sign_in"')
            .replace(
                'billing_source = "github_copilot_subscription_allowance"',
                'billing_source = "kiro_subscription_allowance"',
            ),
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

    def execute(prompt, config, **kwargs):
        attempts.append(config.access_method.value)
        if config.access_method is AccessMethod.CODEX_CLI:
            partial = "# Partial work before simulated quota exhaustion\nvalue = 1\n"
            if args.shared_coding:
                session = ACTIVE_SESSION.get()
                assert session is not None
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
                + "Do not edit the test or other fixture files.",
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
                "3",
                "--skip-prompt-review",
                "--execute",
                "--timeout-seconds",
                "90",
                "--log-file",
                str(artifact / "assistant.log"),
            ]
        )
    finally:
        cli._run_external_agent = real_execute
        execution_fallback.check_agent_readiness = real_auth
    # Validate the tiny assignment without executing model-authored Python.
    source_valid = valid_source(source.read_text(encoding="utf-8"))
    completed_edits = []
    if args.shared_coding:
        with sqlite3.connect(artifact / "session.sqlite3") as connection:
            completed_edits = [
                row[0]
                for row in connection.execute(
                    "SELECT operation FROM coding_receipts "
                    "WHERE status='completed' AND operation LIKE 'shared:%:edit_file:%'"
                )
            ]
    edit_runs = [operation.split(":")[2] for operation in completed_edits]
    protected_unchanged = all(
        (artifact / name).read_bytes() == content for name, content in protected_content.items()
    )
    passed = (
        exit_code == 0
        and source_valid
        and (not args.shared_coding or len(edit_runs) == len(set(edit_runs)) == 2)
        and tests.read_text(encoding="utf-8") == original_tests
        and protected_unchanged
        and "Partial work" in source.read_text(encoding="utf-8")
        and attempts == ["codex_cli", args.fallback_client + "_cli"]
    )
    result = {
        "passed": passed,
        "simulated_initial_quota": True,
        "real_fallback": args.fallback_client,
        "attempts": attempts,
        "exit_code": exit_code,
        "source_validation_passed": source_valid,
        "completed_shared_edits": len(completed_edits),
        "shared_edit_runs": edit_runs,
        "shared_coding": args.shared_coding,
        "protected_files_unchanged": protected_unchanged,
    }
    (artifact / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("fallback_acceptance: " + json.dumps(result))
    print(f"acceptance_artifacts: {artifact}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
