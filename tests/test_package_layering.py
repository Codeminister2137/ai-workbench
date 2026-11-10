"""Package layering ratchet: orchestrator stays decoupled, provider drift frozen.

Measured 2026-11-10: ai_orchestrator imports nothing outside itself (neutral
contracts + decisions; callers inject implementations). ai_provider runtime-imports
ai_orchestrator/ai_agent from the modules pinned below (hosted/agent machinery
grew inside the provider package). ai_agent may wire all three. The pin is a
ratchet: shrinking the provider set is welcome, growing it fails loudly.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
IMPORT_RE = re.compile(r"^from (ai_provider|ai_orchestrator|ai_agent)\b", re.M)

# ai_provider modules with runtime up-imports (2026-11-10 survey).
PROVIDER_UP_IMPORTERS = frozenset(
    {
        "acceptance_harness.py",
        "acceptance_jobs.py",
        "account_usage.py",
        "agent_readiness.py",
        "codex_usage.py",
        "coding_assist.py",
        "coding_sessions.py",
        "copilot_usage.py",
        "execution_fallback.py",
        "external_agents.py",
        "fallback_diagnostics.py",
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
