"""Dispatch account observations to supported native subscription adapters."""

from typing import Any

from ai_orchestrator import AccessMethod, BillingSource, ExecutionTarget

from ai_provider import codex_usage, copilot_usage, kiro_usage


def read_execution_allowance(target: ExecutionTarget) -> dict[str, Any] | None:
    """Read the selected subscription source without inferring API or credit spend."""
    timeout = min(15, target.timeout_seconds)
    if (
        target.access_method is AccessMethod.CODEX_CLI
        and target.billing_source is BillingSource.CHATGPT_SUBSCRIPTION_ALLOWANCE
    ):
        return codex_usage.read_codex_allowance(timeout_seconds=timeout)
    if (
        target.access_method is AccessMethod.COPILOT_CLI
        and target.billing_source is BillingSource.GITHUB_COPILOT_SUBSCRIPTION_ALLOWANCE
    ):
        return copilot_usage.read_copilot_allowance(timeout_seconds=timeout)
    if (
        target.access_method is AccessMethod.KIRO_CLI
        and target.billing_source is BillingSource.KIRO_SUBSCRIPTION_ALLOWANCE
    ):
        return kiro_usage.read_kiro_allowance(timeout_seconds=timeout)
    return None
