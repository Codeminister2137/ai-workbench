# ADR-082: Dashboard stays centralized; no per-client data split

Status: Accepted by the owner, 2026-11-05 (resolves gap-doc G6's owner
question; backup design recorded alongside, implementation queued).

## Decision and intent

Runs, inbox, chats, and the document library stay global with per-record
project refs. Nothing splits out of the centralized dashboard interface
until a clear need forces it.

Owner rationale (2026-11-05): ai-workbench is the primary way to interact
with and develop commercial projects, so as much as possible gathers in a
single place. A second real client project is the trigger to revisit.

## Alternatives considered

- Per-project data dirs (`data/projects/{id}/...`) with a switcher: hard
  isolation and per-client backup/deletion, but migration cost, switcher
  UX, and weaker cross-project views.
- Hybrid (global inbox + per-project runs/chats): single triage queue with
  isolated records, but two mental models and a still-shared inbox.

## Consequences

- Multi-project support = registry + `project_id` refs + project filters
  in views (filters still to add where missing).
- The per-record refs keep a future split mechanical; revisit on the
  second real client, not before.
- Companion decision (same day): ignored-file backup = private GitHub
  repo for documents + scheduled disk snapshot for data; implementation
  queued as repository-local follow-up work.
