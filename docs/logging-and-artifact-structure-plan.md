# Logging and artifact structure review

**Priority: High. Scope: whole repository. Status: planned; layout not yet selected.**

The owner requested this on 2026-10-12 because the current collection of logs and
files is difficult to understand and navigate. Human readability is a requirement;
an arrangement that an AI can reconstruct is insufficient. Review this alongside
the [documentation conformance plan](documentation-conformance-plan.md), starting
with CLI development sessions. Existing CLI acceptance work remains incomplete.

## Current problem

The first bounded [writer/reader inventory](logging-artifact-inventory.md) maps
current CLI/provider/scheduler/Council/job-search paths and proposes a representative
layout for owner review. It preserves existing paths and records compatibility
and retention decisions; no replacement layout or migration is approved yet.

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

## Wider error-propagation review — owner direction 2026-10-17

Review error propagation across the repository, with the CLI/agent execution paths
first. The owner needs to understand why an operation failed and which service or
component is breaking without reconstructing unrelated logs. This extends the
review beyond artifact layout; no new logging stack or public error contract is
selected by this plan.

Start investigation immediately whenever an encountered error has no established
cause. Preserve the first failure and actual effects, pause repetition of the
affected operation, and inspect the relevant evidence and boundary code. Do not
leave an unexplained error as a passive backlog note or retry until it disappears.
Existing authorization permits bounded diagnostic work; fresh inputs/bounds and
privacy, cleanup, consumed-trial and gaming-resource constraints still apply.

Review in bounded slices:

1. Trace CLI entry, agent/model loop, provider adapter/HTTP transport, local engine
   or hosted gateway/upstream, tools, foreground workers and MCP/IDE bridges. Then
   cover Orchestrator routing/fallback and application/automation consumers.
2. For each boundary, map the originating exception or service error, translation,
   exception chaining, retry/fallback decision, process exit/status, persisted
   receipt and final user-facing message. Find discarded bodies/causes, generic
   wrappers, mismatched statuses and failures hidden behind a successful closeout.
3. Distinguish the reporting component, evidenced failing service, execution stage,
   operation and underlying cause. Preserve available provider/route/runtime/version,
   request/run/worker correlation, timing and safe diagnostic details. Do not blame
   a downstream service merely because the CLI reported an error.
4. Check HTTP and streamed errors, malformed responses/tool calls, timeouts,
   cancellation, worker crashes, denied approvals, tool/validation failures and
   failed fallback. Preserve the first cause and distinguish subsequent recovery,
   cleanup and secondary failures. User messages must lead to the relevant evidence.
5. Add targeted failure-injection/contract tests across composed boundaries so a
   caller can still identify the failing stage/service and cause. Check redaction,
   bounded diagnostic reads, error-path flushing/cleanup and partial outcomes.
   Prefer deterministic local tests before a fresh bounded live diagnostic.

Required outcome: errors retain their known cause and make the failing component
easy to identify. If upstream evidence is unavailable or a prior response was
discarded, exact attribution cannot be guaranteed: explicitly mark the cause as
unknown, explain the evidence gap and start the concrete investigation needed to
close it. A status such as HTTP500 is a symptom, not a completed cause analysis.
Missing observability is itself a finding to address, not permission to invent a
root cause or silently enable raw prompt/private-thinking/secret logging.

Reuse existing exceptions, diagnostic records and run artifacts. Significant
public error/data-contract, persistence, privacy, dependency or architecture changes
require the existing owner decision process. Broader path/layout and historical
retention choices above remain unselected; this review does not authorize migration.

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
- Injected failures across the reviewed CLI/agent boundaries identify the reporting
  and failing components, known cause, stage and correlated evidence without leaking
  sensitive content. Unknown causes trigger investigation and an explicit evidence-gap
  report; successful recovery does not erase the original failure.
