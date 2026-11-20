# ADR-090: Dashboard-native Mai supervision with pause/kill/page authority

Status: Accepted by owner, 2026-11-18 (chat; accepted the recommendation
from the supervision brief, inbox db16e0bd).

## Problem

The drain executes queued runs while the owner is away, but supervision
was scattered: the dashboard supervisor tick, the supervision probe,
owner mail notify, and boot reconciliation each owned a piece, with no
single authority for pause/kill/page. The Mai-switch bar (same-or-higher
capability plus reliable wiring) needs one doctrine before the switch.

## Decision

1. Supervision lives in the dashboard (option A). Mai stays an
   execution engine; the dashboard owns unattended authority.
2. Full authority: pause (drain auto-pause on allowance/config failure),
   kill (run cancellation), page (owner mail + inbox escalation).
3. Mail-noise rules, first cut: the same terminal outcome is mailed
   at most once (receipt-keyed dedupe in `notify_plan`). Routing
   completions to inbox-only stays a follow-up decision with its own
   brief — not silently bundled here.

## Consequences

- New supervision behavior goes in dashboard modules, never Mai-side.
- `notify_plan` gains a `dedupe_key` receipt field; repeats return
  `deduped` without sending.
- Digest-batching of success mail stays a future option, not a promise.

## Notification digest (owner decision, 2026-11-20)

This supersedes the earlier deferral of digest batching. [ADR-098](ADR-098-hourly-unattended-mail-digest.md) records the accepted hourly unattended-only digest and whole-window blocker exception. Terminal outcome deduplication remains in force; routine outcomes now enter the shared durable digest rather than sending immediately.
