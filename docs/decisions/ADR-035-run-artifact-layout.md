# ADR-035 - Run Artifact Layout

**Status:** Accepted
**Date:** 2026-10-02

## Context

Research reports accumulated in the repository root, while acceptance workspaces
containing source fixtures and tests lived under `logs/`. The owner approved
`artifacts/<run>/` and moving existing generated files. The owner's rationale is
that the project is not in production and new structures can be established now.

## Options considered

- Group by run under `artifacts/`: keeps reports, logs, fixtures, and dedicated
  databases together; requires updating launchers and preserving historical paths.
- Separate `reports/`, `logs/`, and `data/`: distinguishes file purpose but scatters
  related evidence across directories.
- `docs/research/`: makes reports discoverable but risks presenting experimental
  or failed model drafts as authoritative documentation.

## Decision

Use ignored `artifacts/<run>/` for generated run output. Update research and
acceptance launchers and group general-launcher logs there. Keep shared ongoing
chat/run state in `data/`. Explicit custom output paths remain supported.

Move existing root research reports, dedicated research databases, acceptance
workspaces, and closed logs. Preserve source bytes and original write receipts.
Record digest-bound `report_relocations` in existing implementation-stage
metadata so deterministic receipt validation can recognize an authorized move.
The original matching write receipt is still required; relocation alone cannot
prove a write. Preserve historical log text and database backups with the move
manifest. No new database schema or service is introduced.

## Consequences

The root is clearer and all generated evidence for a run can be inspected
together. Old file links in logs may refer to pre-migration paths; the move
manifest preserves the mapping. A legacy Ollama log held open by a running
process remains in `logs/` until that process releases it. Moving that file does
not justify interrupting an independently running inference server.
