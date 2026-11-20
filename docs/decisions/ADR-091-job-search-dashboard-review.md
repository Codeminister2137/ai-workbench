# ADR-091: Job-search application review belongs in the dashboard

Status: Accepted by owner, 2026-11-18 (option A, inbox
`0e5a06e2573a44408e327730417b7680`; closeout run
`e190798ca6ed40078883e3dfa465ecaa`).

## Decision

M3's primary per-application review surface is a page in the existing
Workbench dashboard. A richer terminal interface is not the M3 delivery
target. Existing CLI tools remain available.

The page must present the vacancy, evidence-backed match report, proposed
material changes and warnings together, with per-item edit, approve and
reject actions before the existing application approval gate. Reuse the
job-search domain's matching, preparation, approval and guarded sender;
dashboard inbox/run approvals do not substitute for application approval.

Editing approved materials must revoke approval. Delivery must remain bound
to the reviewed recipient, message, CV variant and exact attachment bytes;
unapproved or changed materials must fail the existing sender guard.
Retain the sent-material snapshot/receipt acceptance requirement from M3.

## Context and alternatives

The source brief asks where the next M3 slices live, following the
deterministic M2 match report. Dashboard review fits the centralized product
direction, keeps review beside existing owner interactions and is visible
without a terminal. Its cost is web rendering, integration and UI tests.
A richer CLI would be quicker and scriptable, but would split review across
the terminal and dashboard. The brief recommended the dashboard; the owner
selected A without an additional rationale. No further owner rationale is
inferred here.

## Implementation status and boundaries

This records the surface decision; it does not claim the M3 page exists.
M3 implementation and its end-to-end acceptance remain incomplete. Next:
build a dashboard review slice that exposes vacancy + match + material diffs
+ warnings and exercises edit/approve/reject through existing domain gates.
Completion requires a reachable page, sent-material snapshot evidence and
passing unapproved-send and changed-material rejection checks.

This choice does not authorize automatic sending, a second service, a new
storage format or broader candidate-data transmission. Storage/outcome and
profile decisions retain their separate scope. See the private
`docs/plans/job-search-execution-plan.md` M3/D3 and
[job-search project](../projects/job-search.md).
