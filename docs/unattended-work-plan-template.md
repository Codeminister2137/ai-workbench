# Unattended session plan template

Copy this to local `docs/plans/unattended-work-plan.md` before an unattended run.
Link the active plan from `CURRENT_CONTEXT.md`; keep reusable instructions here
and run evidence in the existing artifact locations. This plan does not grant
inference, external access, dependencies, infrastructure or expanded task scope.

## Window and boundaries

- Status: NOT_STARTED / ACTIVE / CLOSED. Never resume a closed allowance implicitly.
- Actual start, owner duration/deadline, timezone and fixed UTC deadline:
- Immediate objective and its authoritative requirement/plan files:
- Wider approved goals, priority order and exact source plan files:
- Applicable instructions, existing dirty work and preservation requirements:
- Live/resource/privacy/approval limits and independently available offline work:
- Closeout reserve and work-admission cutoff; increase reserve for expected cleanup:
- Sleep: DEFAULT, ten minutes after finishing; record any explicit owner override:
- Next timed checkpoint: after each step/blocker, before long work, and no later
  than thirty minutes from the previous checkpoint during ongoing work.

## Ordered steps and candidate ledger

Break goals into actions that can be executed or investigated within the window.
Include the initial slice, independent fallback work and the mandatory closeout.
Use duration ranges or estimates with reasonable headroom; these are not per-step
timeouts. Reallocate remaining plan time when useful progress warrants it. The
session cutoff, closeout reserve and explicit call/tool/resource/pilot allowances
stay hard. Give fresh pilot bounds their headroom before launch, not by extending
active or consumed allowances.

| Order | Concrete action | Source requirement | Authority/limits | Rough duration, including checks/cleanup | Validation/completion condition | Status and next action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Inspect current state and resolve the immediate slice's actual prerequisites | | | | | |
| 2 | Execute and verify the immediate slice within its unchanged bounds | | | | | | |
| 3 | Investigate/execute a concrete independent action from wider approved goals | | | | | | |
| Final | Stop admissions; clean up; independently verify state; save handoff; schedule sleep ten minutes after finishing; verify scheduling receipt; deliver the existing report | AGENTS.md / docs/workflow.md | Default sleep unless explicitly overridden | Reserve enough time before work ends | Owned work stopped, state verified, handoff saved, sleep_scheduled receipt verified or actual failure investigated, existing report delivered | Required for every ending |

Candidate statuses: READY, NEEDS_INVESTIGATION, IN_PROGRESS, COMPLETE, BLOCKED.
For every BLOCKED row, name the exact prevented action, evidence, unlock condition,
and smaller independent work that remains possible. Missing evidence is
NEEDS_INVESTIGATION. Broad labels such as "live acceptance pending" cannot block
all investigation, preparation and implementation for that goal.

## Time and progress checkpoints

| Actual UTC time | Trigger/step result | Time left / closeout reserve | Evidence and changed estimates | Revised next action / next checkpoint |
| --- | --- | --- | --- | --- |
| | Start / completed step / blocker / long-operation admission / timed check | | | |

At each checkpoint read the clock, preserve the original deadline, and choose
work whose full envelope fits. A completed or blocked step immediately triggers
selection of the next action. Preserve first failures and investigate unknown
causes; do not replay consumed trials or bypass safeguards.
Steps are meaningful work units, not individual tool/model calls. Keep checkpoint
updates short within the existing turn, reuse current observations and batch clock
reads with normal monitoring. No separate model/reviewer invocation, repeated
passing check or full-document reread is required just to reassess the time.

## Replenishment and early-stop gate

If the whole current plan completes or stalls with useful time remaining:

1. Reopen the wider-goal files named above and inspect current implementation.
2. Identify concrete independent next actions and add them to the ordered plan.
3. Execute/investigate those actions; record actual outcomes and reassess time.
4. Repeat until the work cutoff, explicit owner stop, or evidenced exhaustion.

Before claiming early exhaustion, account for every READY and NEEDS_INVESTIGATION
action with actual work or a specific evidenced restriction. Try smaller actions
permitted by each blocker. If evidence is missing, continue investigation.
Passing checks, a documentation sweep, no obvious defect, an incomplete milestone
or the absence of permission for another full pilot do not prove exhaustion.

## Mandatory final step

Use the same closeout for deadline and early endings, regardless of task outcome.
Finish owned cleanup, independent verification and the handoff within the window.
Schedule `scripts/workstation-sleep.ps1 -Sleep -DelaySeconds 600` with fresh receipt
and cancellation paths through a hidden process. Verify its `sleep_scheduled`
receipt; a scheduling failure needs immediate investigation. An explicit owner
override or actual platform restriction must be preserved, never assumed from
silence. The timer may remain for the ten-minute delay; task workers must not.

Keep all existing reporting requirements from AGENTS.md and the canonical prompt.
This template changes planning/execution, not report format or required content.
