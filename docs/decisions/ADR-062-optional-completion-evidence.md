# ADR-062 — Optional completion evidence within the original turn

**Status:** Accepted and implemented offline (2026-10-19),
fresh live acceptance incomplete.

## Owner decision and context

The owner approved the recommended shared optional completion check after the
standalone frozen-review pilot omitted Git diff and returned an inaccurate report
with calls remaining. A deterministic reproduction confirmed that the shared loop
returned the candidate before the private task-completeness gate could respond.
The owner chose the recommendation to improve the actual agent rather than only
the pilot. No additional independent rationale was supplied; the existing stated
goal is ordinary bounded correction without useless loops. ADR-061's malformed
argument recovery remains separate and unchanged.

## Contract

Add optional `completion_requirements` to `AgentLoop` and the native coding task
runner. A `CompletionRequirement` has a bounded identifier and a trusted read-only
predicate over completed tool results. Callers define objective requirements in
the task; no universal mandatory tool sequence or generic prose truth grader is
introduced. Empty requirements preserve existing completion behavior. This slice
exposes a Python/task-controller contract, not a new CLI flag or persisted setting.
No automatic external-client/fallback mapping is certified by this contract.

Predicates must return bool; unknown/nonboolean results or checker exceptions
stop safely, preserving the model candidate and earlier effects without echoing
raw exception text. Nonblank candidates with missing evidence receive fixed,
explicitly host-authored user-role feedback in the same conversation. Retain the
actual candidate as assistant output and preserve exact-origin continuation,
earlier instructions and tool observations. Do not fabricate a tool result or
assistant correction. Length-limited, error-finished and empty responses retain
their existing caller handling rather than becoming this correction path;
unknown finish metadata cannot bypass objective requirements.

All requests consume the original iterations, deadlines, admission and tool
permissions. A checker executes no tools and grants no authority. Report numeric
completion failures separately from malformed-output errors; existing per-attempt
usage captures candidates and corrections, including unknown/partial fields.

## Progress and stopping

Reuse ADR-061's bounded observed-file fingerprint, at most1MiB per reported local
file, without modifying its malformed-argument counters. For completion failures,
count the combination of missing requirement identifiers and observed file state.
Two failures at a previously failed combination stop. Keep prior combinations so
no-op edits or A/B/A cycling do not renew feedback. New successful required
observations may reduce the missing set without any writes; a review is not
forced to edit. Unknown effects do not establish file progress. This is bounded
evidence over observed paths, not an OS sandbox or comprehensive file monitor.

Sixteen requirements with identifiers up to80lowercase ASCII identifier characters
are the implementation bounds; duplicate identifiers are refused. They are local
engineering bounds, not an externally prescribed agent policy.

## Alternatives and consequences

- **Shared optional check, selected:** improves the actual agent and centralizes
  correction; adds an opt-in public contract and requires compatibility and
  permission/history/resource tests. Callers still own meaningful predicates.
- **Private pilot-only feedback:** less production surface and cheaper diagnostic
  implementation; leaves the daily agent unchanged, creates private assistance
  to maintain and limits what a pilot success demonstrates.
- Current fail-and-report behavior remains the default when no requirements are
  supplied. It cannot offer correction for a caller-declared missing observation.

No provider, dependency, service, storage format, approval or privacy change.
No new inference allowance, automatic retry of uncertain effects, universal
correction count or proof of internal Codex equivalence follows.

## Acceptance

Deterministic tests cover actual tool effects, native caller composition,
candidate/history/continuation preservation, shared argument/completion budgets
and usage, unknown metadata, checker failure privacy, deadline/permission refusal,
new read evidence, repeated/no-op/cycling failures and no-checker compatibility.
A fresh sealed local diagnostic must still show model-authored missing actions
and an accurate report. Integrated baseline additionally requires correct coding
effects, both substantive true reports, independent oracle and verified cleanup.

Validation:88focused tests passed; full offline gate2,474passed/3skipped
(workspace2,352, Council38, job-search84). Full Pyright and Ruff passed.
Unknown finish metadata bypass in the initial native test was corrected and
retained as a regression. These checks establish software behavior, not model
quality or complete baseline acceptance.
