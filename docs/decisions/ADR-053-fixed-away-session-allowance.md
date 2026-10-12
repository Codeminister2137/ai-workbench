# ADR-053 - Fixed away-session allowance

**Status:** Accepted; implemented and tested offline, live pilot deferred
**Date:** 2026-10-11

## Owner decision and rationale

The owner selected redefining `--away-minutes` as a fixed session allowance,
instead of keeping its existing per-turn meaning and adding a separate outer
allowance option. The owner's rationale is that a specific turn limit should
have a name that clearly identifies the turn, following CLI conventions.
`--turn-timeout-seconds` names that bound, consistent with the existing
`--timeout-seconds` provider-request timeout.

## Direction and consequences

Successive turns and task restarts inside the granted window must not reset
the away deadline. The effective execution bound is the earlier of the away
deadline and any separately selected turn deadline. Provider request timeout
remains a different bound. Existing documented per-turn `--away-minutes`
behavior will change; examples and help must explain the migration explicitly.

This decision does not authorize a live pilot, new inference, service startup,
or extending any expired allowance. Existing permissions/privacy/fallback and
validation requirements remain in force.

## Launch and resume scope

Saved coding-chat sessions survive process restarts. The owner selected a fresh
allowance by default for each launch explicitly supplying `--away-minutes`,
including resume. Their rationale: restart behavior depends heavily on its
reason, but a fresh allowance should be the default. The implementation does
not infer exceptions from restart reasons. Without that flag, resume does not
inherit an old allowance. No deadline persistence or renewal interface is added.

The alternative was retaining a persisted deadline across launches with explicit
renewal. That would prevent extending the original window but add storage and
renewal behavior. The selected default is simpler and allows an explicit new
launch to grant fresh time; it intentionally does not enforce a window across
process restarts. Within a launch, idle time, setup, turns, delegation, fallback
and host stages share the original deadline. Turn limits can shorten it.

## Enforcement and validation limits

### Local-only pilot clarification — 2026-10-12

The owner approved removing the call-count cap specifically for local-only
pilots. Local model calls consume local compute and elapsed time rather than
provider allowances. Retaining a six-call cap bounds repetitive generations,
but can stop useful inspection, edits and review before the time allowance ends.
Using the time bound permits more local generations within that same window.

Use the existing run-local `--no-request-cap` option while retaining the fixed
30-minute launch deadline, per-request timeout, two-file scope, frozen checks
and verified cleanup. This does not change production CLI defaults, provider
allowance controls, privacy boundaries or the validity of expired allowances.
Approval permits this configuration; offline preparation does not establish
successful live acceptance.

Provider-neutral AgentLoop deadline enforcement now prevents requests and tool
actions after an absolute deadline, including multiple tools in a response and
approvals that outlast it. Completed effects/receipts remain preserved; running
tools are not forcibly interrupted. Optional support passes cap request timeouts
and reject late responses. Fallback and stage tracking use the effective bound.
Interactive idle input expires without a new prompt answer; noninteractive
blocking input is checked when it returns. This is an admission and outcome
deadline, not process-wide hard cancellation. Offline regression checks do not
prove model quality or completion of the live edit/test/review workflow.
