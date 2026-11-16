# ADR-089: Pre-approve all agent-queue runs, with budget backstops

Status: Accepted by owner, 2026-11-16 (chat; decision C from the
delegation brief — "I approve C"). Extends ADR-088 (whose E2E rule
stands as a special case); standing principle recorded: humans are
escalation, not the norm.

## Problem

Every bridged agent task filed an "Approve agent run" decision, so
routine agent work (sweep findings, studies, follow-ups) cost the
owner a click each — 10 approvals in ~7 minutes on 2026-11-16 —
while the clicks protected nothing the existing containment did not
already cover (worktree isolation, staged review, receipts, E2E
re-test). The owner directed that agent work proceed autonomously
with humans as escalation.

## Decision

1. The inbox bridge pre-approves every agent-queue task. Provenance
   stays explicit via `approval_mode`: `owner-filed`, `e2e-followup`,
   `agent-queue`. Decisions, clarifications, orders, and plan
   approvals (supervisor_threads) still need the owner.
2. Money/config safety moves from launch clicks to budgets:
   - Time: every Mai subprocess dies on the 1800s kill (verified;
     per-run override via `mai_timeout_seconds`).
   - Paid spend: prepaid stays default-blocked with finite explicit
     grants (pre-existing model, unchanged).
   - Auto-pause: the scheduled drain skips ticks while the newest
     terminal failure is allowance/config-related with no success
     since, filing one deduped owner alert; closing it resumes, and
     a later failure re-files. Manual drains bypass the pause
     (explicit owner action).
3. Out of scope (recorded gaps, not silent): per-run Mai usage
   attribution (Mai reports session/route, not tokens/cents, so the
   ledger cannot settle per-run Mai spend); action-level shell
   sandboxing (unconfined shell remains accepted on agent obedience
   plus audit, as in interactive sessions).

## Consequences

- Agent-queue runs start on the next drain tick with no approval
  item; `approval_mode` records why each run was allowed.
- A money/config failure pauses the queue with exactly one owner
  alert instead of burning through queued runs.
- Rejected alternative A (E2E-only pre-approval): keeps the flood.
- Rejected alternative B (bare pre-approval, no backstops): no
  bound on burn or runaway; the pause gate is the difference.
