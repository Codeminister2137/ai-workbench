"""Slim supervisor instructions with per-delegation context assembly.

The dashboard chat relay invokes the supervisor (usually a local Ollama
model) on every turn. That system prompt used to be one static block
resent in full each time, so cost scaled with the handbook instead of
the delegation. This module splits the block:

- ``SUPERVISOR_CORE_INSTRUCTIONS``: small, stable, always sent. It states
  only the supervisor's identity and hard limits (the grounding contract
  the chat tests pin) and must fit ``SUPERVISOR_CORE_BUDGET_CHARS``.
- ``assemble_supervisor_prompt``: the core plus only the task-relevant
  delegation state for this invocation (receipts so far, the approval
  policy surface, paths involved). Empty state adds no sections.
- Long-form guidance lives in ``docs/supervisor-handbook.md`` (reference
  only). This module never reads that file; nothing handbook-only is
  sent to the model by default.

Credential rule (fail-closed, same refusal as the agent loop): the
assembled prompt is checked before return, and any credential value
refuses with ``ProviderError`` instead of reaching the model.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from ai_provider.credential_guard import enforce_credential_policy

from ai_agent.fanout import FanoutPolicy
from ai_agent.tools.credential_paths import is_credential_path

SUPERVISOR_CORE_BUDGET_CHARS = 600

SUPERVISOR_CORE_INSTRUCTIONS = (
    "You are the Workbench supervisor in the owner's local dashboard. "
    "Be concise and concrete. "
    "You can inspect the workspace (read, list, search, git status) but "
    "cannot edit files, execute commands, restart services, or send mail; "
    "never claim an email was or will be sent. "
    "You have no live view of services (Ollama, dashboard, scheduled "
    "tasks): send the owner to the dashboard Home status view. "
    "Development work happens only through agent runs the owner queues "
    "with the Request-run button and approves in the inbox. "
    "This PC runs Windows: never mention Linux paths, daemons, or commands."
)

MAX_DELEGATION_RECEIPTS = 8
MAX_RECEIPT_CHARS = 200
MAX_DELEGATION_PATHS = 12
MAX_PATH_CHARS = 200


def _clean_entries(values: Sequence[str], *, what: str) -> tuple[str, ...]:
    """Require a string sequence; strip entries and drop blanks."""
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise TypeError(f"{what} must be a sequence of strings")
    cleaned: list[str] = []
    for entry in values:
        if not isinstance(entry, str):
            raise TypeError(f"{what} must be a sequence of strings")
        text = entry.strip()
        if text:
            cleaned.append(text)
    return tuple(cleaned)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _receipts_section(receipts: Sequence[str]) -> str | None:
    cleaned = _clean_entries(receipts, what="receipts")
    if not cleaned:
        return None
    omitted = len(cleaned) - MAX_DELEGATION_RECEIPTS
    visible = cleaned[len(cleaned) - MAX_DELEGATION_RECEIPTS :] if omitted > 0 else cleaned
    lines = [_truncate(receipt, MAX_RECEIPT_CHARS) for receipt in visible]
    if omitted > 0:
        lines.insert(0, f"[{omitted} earlier receipt(s) omitted]")
    return "Delegation receipts so far:\n" + "\n".join(f"- {line}" for line in lines)


def _approval_section(approval_policy: FanoutPolicy | str | None) -> str | None:
    if approval_policy is None:
        return None
    policy = FanoutPolicy.coerce(approval_policy)
    spawns = "allowed" if policy.allows_spawn else "refused"
    return (
        f"Run requests from this chat inherit fan-out '{policy.value}' "
        f"(child spawns {spawns}); nothing runs until the owner approves "
        "the linked inbox decision."
    )


def _paths_section(paths: Sequence[str]) -> str | None:
    cleaned = _clean_entries(paths, what="paths")
    if not cleaned:
        return None
    for entry in cleaned:
        candidate = Path(entry)
        absolute = candidate.is_absolute() or PurePosixPath(entry).is_absolute()
        if absolute or ".." in candidate.parts:
            raise ValueError(f"Delegation path must be workspace-relative: {entry!r}")
        if is_credential_path(candidate):
            raise ValueError(f"Delegation path refused (credential file): {entry!r}")
    visible = cleaned[:MAX_DELEGATION_PATHS]
    lines = [_truncate(entry, MAX_PATH_CHARS) for entry in visible]
    if len(cleaned) > MAX_DELEGATION_PATHS:
        lines.append(f"[+{len(cleaned) - MAX_DELEGATION_PATHS} more]")
    return "Paths involved:\n" + "\n".join(f"- {line}" for line in lines)


def assemble_supervisor_prompt(
    *,
    receipts: Sequence[str] = (),
    approval_policy: FanoutPolicy | str | None = None,
    paths: Sequence[str] = (),
) -> str:
    """Assemble slim core plus only the delegation state for this turn.

    Empty receipts/paths and a missing approval policy add no sections,
    so a fresh chat turn sends just the core. Bounds are deterministic:
    receipts keep the newest entries, paths keep the first entries, and
    truncation is marked inline. Credential-bearing content refuses with
    ``ProviderError`` (fail-closed); nothing is sent to the model.
    """
    sections = [SUPERVISOR_CORE_INSTRUCTIONS]
    for section in (
        _receipts_section(receipts),
        _approval_section(approval_policy),
        _paths_section(paths),
    ):
        if section is not None:
            sections.append(section)
    assembled = "\n\n".join(sections)
    enforce_credential_policy(assembled)
    return assembled
