# ADR-098: Hourly unattended owner notification digest

Status: Accepted, 2026-11-20. Source inbox `fa9590e797b3468ca56a8409f3e394d5`, closeout run `43af703038b3443bbfe379d14248f20f`.

## Decision and owner intent

The owner chose A, an hourly digest rather than a send-time throttle. Mail is only for unattended sessions. Blockers are the primary purpose and appear before routine progress. A real blocker may bypass cadence only when all work is blocked. Routine completions, sleep and final closeout have no independent immediate-mail exception.

This supersedes ADR-090's deferral of digest batching, preserving dashboard authority and owner-only SMTP. A retains intermediate updates and quiet-period delivery across restart, at the cost of durable delivery state and scheduler dependence. B would be smaller but discard suppressed mail detail and provide no quiet-period flush. The owner's stated rationale is blocker visibility while unattended; no additional rationale is inferred.

## Implementation

All live notification producers use `owner_mail.send_owner_mail`, which enqueues in the dashboard's local `owner-digest.sqlite3`. Linked worktrees resolve the common main checkout for the loop notifier. Dashboard producers explicitly use their configured data directory. Dry-run transport diagnostics do not queue.

The existing drain scheduler and redeploy supervisor ticks flush due records even without a new event, checking current supervision mode first. The first digest is due one hour after the first pending event; subsequent digests wait at least one hour after the latest successful mail. Blockers sort first. Oversize batches retain remaining records for later digests; an individually oversize entry is truncated with a dashboard reference.

The loop notifier's `--all-work-blocked` confirms whole-window blockage, and requires `BLOCKED` or `WAITING_FOR_OWNER` state to page. Individual failed runs, parked chats and redeploy incidents are blockers in the digest; they do not establish that all independent work is blocked. The explicit flag is an assertion by the supervising caller, not automatic proof from one failed task.

SQLite transactions serialize delivery across producers and ticks; successful deliveries advance progress, failures remain pending, and stable event keys deduplicate replay. No credentials are stored in the queue. It stores the same subject/body that the existing producers intended for owner mail, under ignored local dashboard data.

## Limits

Delivery requires an active existing scheduler/supervisor and configured SMTP. Attended ticks do not deliver queued unattended messages. SMTP acceptance and a local database commit cannot be atomic: a crash between them can cause a duplicate on recovery. No exactly-once delivery claim is made. No new service, hosted model call, or dependency is introduced.
