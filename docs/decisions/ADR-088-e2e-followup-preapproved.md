# ADR-088: E2E follow-up runs skip owner approval

Status: Accepted by owner, 2026-11-16 (chat; explicit direction on top of
the earlier E2E-follow-up approval requirement). Scope extended the
same day by [ADR-089](ADR-089-agent-queue-preapproval.md) (all
agent-queue runs pre-approved); this record stands for the E2E rule
and rationale.

## Problem

Every E2E follow-up filed an "Approve agent run" decision to the owner,
so a testing wave that found N issues produced N approval interruptions
before any fix work could start. The owner judged this backwards: for
follow-up execution, human tests and decisions are escalation, not the
norm. Per-approval of routine agent work repeats the theater ADR-087
removed for merges: approvals clicked through without reading protect
nothing and train the owner to ignore the inbox.

## Decision

Inbox items with `metadata.kind == "e2e-followup"` (filed only by the
E2E submit flow for failed or noted items) bridge to queued runs as
pre-approved (`approval_mode: "e2e-followup"`), with no approval inbox
item. The agent acts on the failing report and notes; the owner
re-tests the behavior in the re-issued E2E checklist — that verdict is
the human gate, unchanged.

Scope is deliberately narrow: only E2E follow-ups skip the gate, keyed
on the marker the submit flow sets (not on title text). Owner-filed
tasks stay pre-approved as before; all other supervisor/agent-filed
tasks keep the Approve/Reject gate. A general auto-execution policy for
agent runs was NOT approved here.

## Consequences

- Follow-up runs start on the next drain tick after submit, with the
  failing report and owner notes as the work brief.
- The restrictions view counts fewer approval items; e2e-followup runs
  are identifiable by `approval_mode`.
- Abuse surface: anything that can file an inbox task with
  `metadata.kind == "e2e-followup"` bypasses approval. Task filing
  already requires local supervisor access (and the supervisor token
  when configured), the same trust that files the follow-ups today;
  no new principal gains execution rights.
- Rejected alternative: keep per-run approval for follow-ups (proven
  noise; owner explicitly revoked it for this class).
- Rejected alternative: agent pre-review gate instead of pre-approval
  (a second agent verdict before execution); the owner accepted
  direct pre-approval with re-test as the check.
