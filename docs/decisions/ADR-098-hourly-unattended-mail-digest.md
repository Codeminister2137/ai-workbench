# ADR-098: Hourly unattended owner notification digest

Status: Accepted, 2026-11-20. Source inbox `fa9590e797b3468ca56a8409f3e394d5`, closeout run `43af703038b3443bbfe379d14248f20f`.

## Amendment: dashboard work alerts and retained status mail (2026-11-28)

Owner selected C on inbox `c124e9a497ec4102aa0f53d3837db9c7`:
weekly digest mail and dashboard work notifications. The owner's note retains
phone-visible periodic work status without opening Tailscale/apps, and requests
an emergency path where feasible. This supersedes routine attended pages from
`716e02b3505345e09fd2a29718bc63f8` (runtime `cd75b60` / `59290c0`).
The original unattended-only decision below is preserved as history.

Routine needs-you events remain visible in the existing dashboard inbox/run
surfaces. They no longer generate attended mail pages, including individual
failed tasks and owner decisions. Existing hourly unattended status batches
remain available for phone-visible progress; the separate weekly mail digest
and its schedule are retained. Queued rows survive restart and wait while
attended. No new browser/mobile push delivery is introduced.

The existing confirmed whole-window-blocker path still sends immediately in
either supervision mode. A failed task alone does not establish an emergency.
This is a bounded emergency path, not detection of every critical failure:
SMTP, an active producer/scheduler and a running PC remain prerequisites.
No guarantee of phone push, delivery during sleep, or outage detection is made.

A (retain tiered mail) gives more immediate visibility but adds work-mail noise.
B (private mailbox) separates client mail but requires another verified recipient
and inbox. Accepted C reduces routine mail noise but requires dashboard monitoring
for individual work alerts; retained periodic status and the existing emergency
exception address the owner's stated phone-visibility uses. No mailbox migration,
recipient change, new external service, dependency or storage is introduced.

## Original decision and owner intent

The owner chose A, an hourly digest rather than a send-time throttle. Mail is only for unattended sessions. Blockers are the primary purpose and appear before routine progress. A real blocker may bypass cadence only when all work is blocked. Routine completions, sleep and final closeout have no independent immediate-mail exception.

This supersedes ADR-090's deferral of digest batching, preserving dashboard authority and owner-only SMTP. A retains intermediate updates and quiet-period delivery across restart, at the cost of durable delivery state and scheduler dependence. B would be smaller but discard suppressed mail detail and provide no quiet-period flush. The owner's stated rationale is blocker visibility while unattended; no additional rationale is inferred.

## Implementation

All live notification producers use `owner_mail.send_owner_mail`, which enqueues in the dashboard's local `owner-digest.sqlite3`. Linked worktrees resolve the common main checkout for the loop notifier. Dashboard producers explicitly use their configured data directory. Dry-run transport diagnostics do not queue.

The existing drain scheduler and redeploy supervisor ticks flush due records even without a new event, checking current supervision mode first. The first digest is due one hour after the first pending event; subsequent digests wait at least one hour after the latest successful mail. Blockers sort first. Oversize batches retain remaining records for later digests; an individually oversize entry is truncated with a dashboard reference.

The loop notifier's `--all-work-blocked` confirms whole-window blockage, and requires `BLOCKED` or `WAITING_FOR_OWNER` state to page. Individual failed runs, parked chats and redeploy incidents are blockers in the digest; they do not establish that all independent work is blocked. The explicit flag is an assertion by the supervising caller, not automatic proof from one failed task.

SQLite transactions serialize delivery across producers and ticks; successful deliveries advance progress, failures remain pending, and stable event keys deduplicate replay. No credentials are stored in the queue. It stores the same subject/body that the existing producers intended for owner mail, under ignored local dashboard data.

## Limits

Delivery requires an active existing scheduler/supervisor and configured SMTP. Attended ticks do not deliver queued unattended messages. SMTP acceptance and a local database commit cannot be atomic: a crash between them can cause a duplicate on recovery. No exactly-once delivery claim is made. No new service, hosted model call, or dependency is introduced.
