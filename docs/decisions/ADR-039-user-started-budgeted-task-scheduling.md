# ADR-039 - User-Started Budgeted Task Scheduling

**Status:** Accepted; storage, ordering and initial execution scope resolved
**Date:** 2026-10-03

## Context and owner intent

The owner wants occasional long live tests, research and other tasks to remain
planned until an explicit command starts sequential execution. Every scheduled
task needs a required time allocation so execution can compare it with the time
the owner has made available. This avoids spending an entire absence on a long
test when other useful work can fit the available window.

The four-hour work/testing package is approved in general, but the immediate next
session has approximately two hours. Planning the larger package must not start it.

## Accepted behavior

- Planned tasks do not run automatically, on a timer, or merely because a session
  starts. An explicit user command starts a selected sequence and supplies the
  overall available time. CLI spelling is not yet decided.
- Every executable scheduled task declares a positive required time allocation.
  An unspecified duration is not zero and does not permit execution.
- Execute sequentially. Recheck remaining time before each task and admit it only
  when its required allocation fits. Waiting tasks retain their planned status
  when they are not started. Do not silently shorten a task to force admission.
- Preserve task privacy/cost/approval constraints. Under the currently approved
  work window, charged execution is prohibited regardless of credential presence.
- Keep time-admission policy neutral in ai_orchestrator and concrete execution
  in the existing application/executor layer. Use a small foreground component;
  no daemon, calendar service, distributed queue or new external integration is
  approved. Existing deadline supervision remains applicable to supported jobs.
- Planning, running, completion, failure and deferral must be distinguished. An
  allocated duration is a budget, not proof a model will finish successfully.

## Original deferred decisions (resolved below)

Do not silently choose these materially different implementations:

| Boundary | Options and trade-offs | Recommended investigation |
|---|---|---|
| Durable executable task definitions/state | Existing SQLite run store provides tracked state but may need schema changes; a local file is simpler but introduces a persisted contract | Inspect existing stores/configuration; decide ownership and format before adding persistence |
| A selected task cannot fit | Stop preserves strict sequence/dependencies; skip to another independent fitting task improves utilization but changes ordering | Define dependency/order behavior explicitly; do not infer permission to reorder |
| Deadline overruns and task adapters | Existing supervised jobs support hard boundaries; generic callables/CLI jobs may have only cooperative cancellation | Start with already supervised job types; do not promise hard cancellation for unsupported executors |

Pure task/time-admission contracts and deterministic tests can proceed without
resolving durable storage. The private plan holds the initial backlog meanwhile;
it is not an implemented executable scheduler. Defer disputed persistence/order
work and continue approved review implementation/evaluation instead of stopping
the whole session.

## Alternatives and consequences

Immediate launch is simple but contradicts the owner's explicit start boundary.
A background scheduler would add lifecycle and persistence complexity without a
current requirement. User-started sequential admission meets the approved need
and allows incremental reuse of existing execution supervision.

ADR-028/ADR-030 statements that their initial storage/chat slices introduce no
queue remain historically accurate. This new scheduling direction is separately
authorized and does not implicitly change their schemas.

## Implementation checkpoint (2026-10-03)

`ai_orchestrator.scheduling` now supplies immutable task/status and time-admission
contracts. Admission requires explicit start, planned status, caller-validated
execution constraints and a positive finite allocation that fits remaining time.
The caller supplies monotonic timestamps and reserves handoff time first. The
policy returns a task deadline without starting/mutating anything or shortening
allocations. Focused tests cover exact fit, elapsed-time rechecks and refusal.
No scheduler CLI, executable sequence, persisted task definition or cancellation
adapter is implemented; the three listed decision boundaries remain deferred.

The local research-review experiment has a task-specific explicit execution flag
and uses this admission contract for its fixed 90-minute allocation and serial
bounded calls. Planning invokes no models; preparation and handoff reduce actual
remaining time. This does not adopt a generic scheduler start CLI or executable
queue. Inspection confirms the existing application store tracks runs/stages,
not independent executable-task definitions; its schema is unchanged. The existing
research supervisor can stop its owned worker tree, but an independent Ollama
server remains running, so it is not a guarantee of cancelling server-side work.
Storage ownership, non-fitting-task sequence policy and generic cancellation
remain deferred for the owner's return.

## Owner resolution and implementation (2026-10-03)

The owner replied "All recommendations" to the bulk decision brief and accepted:

- Extend the existing application-owned SQLite database with executable task
  definitions and lifecycle state, avoiding a second persisted task file.
- Stop at the first selected task that cannot fit, preserving the selected order
  and keeping all unstarted definitions planned.
- Initially support existing supervised research workers. Generic executor and
  cancellation adapters remain outside this scope.

The brief explained the trade-offs: SQLite reuses existing ownership but adds a
schema; strict stopping preserves order at the cost of utilization; supervised
workers reuse established process boundaries without promising independent
Ollama server cancellation. The owner accepted these recommendations without
supplying additional rationale. The historical pending sections above preserve
the earlier checkpoint and are superseded by this resolution.

`ai_provider.task_scheduler` now owns a foreground plan/list/run/defer/recovery
CLI. An additive, separately versioned `scheduled_research_tasks` table retains
immutable local prompts, repository roots, model identifiers and allocations;
existing run/stage data and their schema versions are preserved. Full prompts
are necessary to execute definitions and remain local; list output omits them.
Atomic planned-to-running transitions prevent duplicate claims of a definition.
Failed, deferred and stale running tasks never automatically restart; create a
new definition for another attempt. Explicit recovery marks an already stopped
running worker failed and does not terminate or resume it.

Execution requires selected IDs, explicit start, compute availability and a time
window with a handoff reserve. The adapter fixes research/trusted_local,
Ollama/local_only/free_only flags and uses the existing supervisor; it does not
start an Ollama service. This is a per-definition claim, not a global mutex across
independent foreground invocations. Worker failure or interruption stops the
sequence and preserves waiting tasks. Completion denotes software execution,
not independently certified research quality. No task was started while the
owner's local-model prohibition was active.
