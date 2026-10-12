# Logging and artifact structure review

**Priority: High. Scope: whole repository. Status: planned; layout not yet selected.**

The owner requested this on 2026-10-12 because the current collection of logs and
files is difficult to understand and navigate. Human readability is a requirement;
an arrangement that an AI can reconstruct is insufficient. Review this alongside
the [documentation conformance plan](documentation-conformance-plan.md), starting
with CLI development sessions. Existing CLI acceptance work remains incomplete.

## Current problem

The CLI pilot directory mixes reports, raw logs, scripts, configuration, patches,
snapshots and databases, with several overlapping handoffs and status summaries.
A next-session prompt was also placed there, obscuring the intended handoff entry
point. Generated evidence and active development instructions need clear ownership.

`CURRENT_CONTEXT.md` is the local immediate handoff, including the copy-paste
next-session prompt at its bottom. `docs/prompt-library.md` owns reusable prompts.
Run artifacts provide supporting evidence; they should not be required to locate
the active handoff. Earlier artifact prompts remain historical references.

## Review and implementation slices

1. Inventory writers/readers across providers, Orchestrator, agent/CLI, Council,
   job search and automation. Map actual uses of `logs/`, `artifacts/`, `data/`,
   configured paths, session databases and sidecar files. Identify duplicates,
   misleading names and files without a clear purpose; do not infer from suffixes
   alone or print sensitive contents during the inventory.
2. Propose a coherent directory and naming convention, with a concrete example
   session the owner can browse. Compare keeping existing roots and introducing
   a common run layout against migration of existing locations. Explain reader,
   configuration and historical-link compatibility before choosing a layout.
3. Define one obvious human entry point for each session/run and a way to find
   the latest one. It should explain the task, actual changes, outcome, checks,
   failures, limits and next action, linking to detailed evidence only as needed.
   Separate readable results from raw diagnostics, fixtures/scripts/configuration
   and snapshots. Display understandable labels alongside correlation identifiers.
4. Align producers and readers in bounded slices. Distinguish model claims from
   host observations; make incomplete, failed and interrupted outcomes clear.
   Preserve provider/route, version, timing and cleanup evidence needed for review,
   without exposing credentials, private reasoning or raw prompts by default.
5. Plan historical migration, retention and cleanup explicitly. Preserve stable
   references, existing databases/receipts and user work. No automatic deletion or
   wholesale move is authorized by this review request. Get owner decisions for
   material path/configuration/data-format, persistence, privacy or retention changes.

Prefer existing files, standard logging and small helpers. Do not add a service,
logging stack, dashboard or parallel status database without demonstrated need.
Proposed folder names and output formats are review results, not accepted decisions.

## Acceptance

- The owner can find the latest session and understand its result by opening one
  clear entry point, without knowing internal filenames or reconstructing chronology.
- From that summary, the owner can reach relevant errors, actual tests and effect
  evidence, and distinguish successful software checks from model-quality acceptance.
- Each file has an explained purpose and location; active handoff, reusable prompts
  and historical evidence have unambiguous owners and no conflicting current copies.
- Producer/reader compatibility, configuration, privacy and preservation are checked;
  approved conventions are reflected in project maps and guides.
- The owner reviews a representative layout before broader rollout. Repository-wide
  completion requires covering all projects, not merely cleaning one pilot folder.
