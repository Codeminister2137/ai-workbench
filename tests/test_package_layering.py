"""Package layering ratchet: orchestrator stays decoupled, provider drift frozen.

Measured 2026-11-10: ai_orchestrator imports nothing outside itself (neutral
contracts + decisions; callers inject implementations). ai_provider runtime-imports
ai_orchestrator/ai_agent from the modules pinned below (hosted/agent machinery
grew inside the provider package). ai_agent may wire all three. The pin is a
ratchet: shrinking the provider set is welcome, growing it fails loudly.
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMPORT_RE = re.compile(r"^from (ai_provider|ai_orchestrator|ai_agent)\b", re.M)

# ai_provider modules with runtime up-imports (2026-11-10 survey).
# allowance_windows.py added 2026-11-17: brief-B models import neutral
# orchestrator contracts (AccessMethod/BillingSource/ExecutionTarget),
# the same precedent as codex_usage.py; landed in 0b8371e.
# acceptance_storage.py added 2026-11-20: owner gate ed066ac7 answer A
# approves this narrow importer exception (Family-3 S2). It imports only
# the frozen neutral vocabulary (access method, catalog loading,
# scheduling status) for the cycle-free storage boundary; no
# orchestration behavior (routing, selection, judging). Growing the set
# further still needs a new owner decision.
# fallback_executor.py added 2026-11-25: scope C single fallback executor,
# owner-accepted 2026-11-23 (ADR fallback-verdict-pipeline-B-then-C, inbox
# b58f8502: "major restructuring is acceptable if needed"), GO recorded
# 25.11. Same frozen vocabulary as execution_fallback.py (targets, catalog,
# fallback candidates); no routing outcomes consumed. Temporary growth:
# C4 deletes FallbackSession, net-shrinking the set.
PROVIDER_UP_IMPORTERS = frozenset(
    {
        "acceptance_harness.py",
        "acceptance_jobs.py",
        "acceptance_storage.py",
        "account_usage.py",
        "agent_readiness.py",
        "allowance_windows.py",
        "codex_usage.py",
        "coding_assist.py",
        "coding_sessions.py",
        "copilot_usage.py",
        "execution_fallback.py",
        "external_agents.py",
        "fallback_diagnostics.py",
        "fallback_executor.py",
        "foreground_tools.py",
        "kiro_usage.py",
        "research_execution.py",
        "research_refinement.py",
        "research_review.py",
        "research_task_settings.py",
        "shared_client_tools.py",
        "task_scheduler.py",
        "user_config.py",
    }
)


def _package_imports(package: str) -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    for path in (ROOT / "packages" / package / "src").rglob("*.py"):
        targets = set(IMPORT_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
        if targets:
            hits[path.name] = targets
    return hits


def test_orchestrator_imports_only_itself() -> None:
    hits = _package_imports("ai_orchestrator")
    outward = {name: targets - {"ai_orchestrator"} for name, targets in hits.items()}
    outward = {name: targets for name, targets in outward.items() if targets}
    assert outward == {}, f"orchestrator gained outward imports: {outward}"


def test_agent_wires_expected_packages() -> None:
    hits = _package_imports("ai_agent")
    outward = {target for targets in hits.values() for target in targets} - {"ai_agent"}
    assert outward <= {"ai_provider", "ai_orchestrator"}, outward


def test_provider_up_imports_do_not_grow() -> None:
    hits = _package_imports("ai_provider")
    current = {name for name, targets in hits.items() if targets & {"ai_orchestrator", "ai_agent"}}
    assert current <= PROVIDER_UP_IMPORTERS, (
        f"new up-importers: {sorted(current - PROVIDER_UP_IMPORTERS)}"
    )


def test_fallback_executor_imports_only_frozen_vocabulary() -> None:
    path = ROOT / "packages/ai_provider/src/ai_provider/fallback_executor.py"
    approved = {
        ("ai_orchestrator", "ExecutionTarget"),
        ("ai_orchestrator", "ModelCatalogEntry"),
        ("ai_orchestrator", "TaskProfile"),
        ("ai_orchestrator", "prepare_execution"),
        ("ai_orchestrator.fallback", "FallbackQualityPolicy"),
        ("ai_orchestrator.fallback", "fallback_candidates"),
        ("ai_orchestrator.fallback", "fallback_profile"),
    }
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"ai_orchestrator", "ai_agent"}:
                assert {(node.module, name.name) for name in node.names} <= approved
        elif isinstance(node, ast.Import):
            assert not any(
                name.name.split(".")[0] in {"ai_orchestrator", "ai_agent"} for name in node.names
            ), "Use the approved explicit neutral-contract imports"


def test_acceptance_storage_imports_only_approved_neutral_contracts() -> None:
    path = ROOT / "packages/ai_provider/src/ai_provider/acceptance_storage.py"
    approved = {
        ("ai_orchestrator", "AccessMethod"),
        ("ai_orchestrator", "load_model_catalog"),
        ("ai_orchestrator.scheduling", "ScheduledTaskStatus"),
    }
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in {"ai_orchestrator", "ai_agent"}:
                assert {(node.module, name.name) for name in node.names} <= approved
        elif isinstance(node, ast.Import):
            assert not any(
                name.name.split(".")[0] in {"ai_orchestrator", "ai_agent"} for name in node.names
            ), "Use the approved explicit neutral-contract imports"
