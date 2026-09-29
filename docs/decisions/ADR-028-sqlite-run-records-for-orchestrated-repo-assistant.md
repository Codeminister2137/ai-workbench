# ADR-028 - SQLite Run Records For Orchestrated Repo Assistant

**Status:** Accepted
**Date:** 2026-09-29

## Context

The repo coding assistant is moving from one-shot CLI execution toward a
foreground unattended workflow with prompt review, planning, auxiliary support,
implementation, validation, scrutiny, repair, and final handoff stages. The
first implementation remains CLI-first and foreground-only, but unattended work
needs durable run and stage records before executed stages begin using them.

The records must be local, private by default, simple to inspect, and reusable
by a later resume or background runner without introducing a daemon, queue, or
external service now.

## Options Considered

- SQLite database under the repository's ignored local runtime data.
- JSONL or flat files under `logs/` or `data/`.
- PostgreSQL or another service-backed store.
- No persistence until a background runner exists.

## Decision

Use a small SQLite-backed storage interface in `ai_provider` for orchestrated
repo-assistant run and stage records.

The initial schema stores one run row and ordered stage rows. The CLI writes
these records when `--orchestrated` is enabled and prints the database path and
run ID. The default database path is `data/repo-assistant-runs.sqlite3`, with
`--away-run-db PATH` available for explicit local override.

## Reason

SQLite fits the current single-developer, local-first, foreground CLI workflow.
It gives durable structured records without adding infrastructure, credentials,
network access, or a service lifecycle. A storage interface keeps the persistence
choice isolated so a future PostgreSQL or job-runner-backed store can replace it
if unattended workflows later need multi-process scheduling or remote execution.

Flat files would be simpler for one transcript, but they become awkward for
stage status updates, resume queries, and future job history. PostgreSQL or a
queue would solve problems the current workflow does not have yet.

## Consequences

- Orchestrated runs now persist local metadata even in dry-run plan mode.
- SQLite files remain ignored local runtime data and should not be committed.
- This decision does not approve background execution, daemons, queues, external
  writes, or remote service integrations.
- Future executed stages should update the same run/stage records instead of
  inventing a second tracking surface.
