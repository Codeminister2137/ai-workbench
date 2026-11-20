# ADR-097: Investor offline journal in Council SQLite

Status: Accepted, 2026-11-20.

## Decision and authority

Owner answer A: Offline slice using Council SQLite, source inbox
`713fe10d90de4e20abf32e175006c234`, implemented by run
`91fdc01e62e444d8a5172f54f3d6e4e6`. No additional rationale was supplied;
the storage choice is explicit and no further owner motivation is inferred.
This extends ADR-093 without changing its paid/live-execution boundaries.

## Alternatives and consequences

A (chosen and technically recommended) reuses Council local SQLite and
transactional integrity, avoiding a parallel persistence mechanism. It changes
Council schema additively and couples journal lifecycle to that database.
B, separate append-only JSONL, isolates Investor records and simplifies export,
but needs separate integrity, replay and lifecycle handling.

## Implementation

Council migration creates additive decision/outcome tables, leaving conversation
history intact. Insert-only records and database triggers preserve originals;
later assessments reference original IDs. This does not protect against direct
file tampering or database loss. Backups must include the journal with Council.

Offline recording requires explicit versions and timestamps, filters future
observations before invoking injected deliberation, and captures accepted, held,
rejected and failed decisions. Replay reads original snapshots and allocations,
never assessments or deliberation. Empty proposals hold existing allocations;
accepted targets close omitted fixture positions. Fixtures must include the held
symbol universe. Simulated fills use fractional shares at fixture prices without
fees or slippage. This establishes deterministic software behavior, not model
quality, learning, broker readiness or an approved execution universe.

There are no new dependencies or services. Connected trials and a live judge
remain separate work under existing privacy, inference and paper-only guards.
