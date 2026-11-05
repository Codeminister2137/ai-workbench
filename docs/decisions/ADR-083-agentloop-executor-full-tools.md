# ADR-083: AgentLoop executor with owner-approved full tools and one-level delegation

Status: Accepted by the owner, 2026-11-05 (full-tools vote; staged-writes
convention and delegation design as implemented).

## Decision and intent

Drained runs execute through `AgentLoop` (`apps/workbench_dashboard/agent_executor.py`)
with the full coding toolset: read/list/search/git/shell/python/navigate/preview,
`stage_file` writes, one-level `delegate_task` subagents, and `request_owner_task`
human tasks. Permissions are `TRUSTED_LOCAL`; the run's fan-out policy flows to
the loop and gates child spawns. Shell and Python run unconfined: per-run owner
approval is the only gate, with no per-command check.

Owner rationale (2026-11-05): maximum autonomous capability; the owner accepted
that an approved run is equivalent to arbitrary code execution as themselves.

## Safety posture (explicit)

- File writes stage by CONVENTION, not enforcement: the system prompt and the
  `stage_file` tool route project changes into `run["staged"]` for owner
  review/apply, but a shell command can write directly. Direct `Create`/`Edit`/
  `RenameApply` tools are excluded from the registry so the designed path
  stages; bypass remains possible and accepted.
- Delegation is exactly one level: `child_registry()` drops the delegate tool,
  so children cannot spawn grandchildren. Child staged files carry back into
  the parent receipt via result metadata.
- Human tasks file into the inbox as `task` items; a run that files tasks
  without a wired inbox fails closed. The run completes with tasks filed;
  pause/resume on owner answers is a later integration.
- `apply_staged` supports writes only: no staged deletes or renames yet, so
  renames go through shell `git mv` or not at all.

## Consequences

- The supervised loop is end-to-end capable in code, but no production drain
  driver exists (deferred by the owner 2026-11-05), so execution currently
  happens only when the drain is invoked directly.
- Follow-ups: staged delete/rename, owner-task pause/resume (`waiting_on_owner`),
  drain driver selection, child budget/depth configurability.
