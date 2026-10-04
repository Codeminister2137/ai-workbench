**Date:** 2026-09-19

Use `pdoc` as the initial generated Python API documentation tool and add
targeted PEP 257-style docstrings to high-value public surfaces. Do not enable
strict docstring linting until the public API has a clean baseline.

Detailed ADR: `docs/decisions/ADR-019-api-documentation-with-pdoc-and-targeted-docstrings.md`

## ADR-020 - Coding MVP Supports Local Requesty And OpenAI Backends
**Status:** Accepted
**Date:** 2026-09-20

The first useful provider/orchestrator coding assistant should support local
Ollama, Requesty, and OpenAI-backed execution, while preserving explicit privacy,
credential, configuration, and provider-neutral transcript boundaries.

Detailed ADR: `docs/decisions/ADR-020-coding-mvp-local-requesty-openai-backends.md`

## ADR-021 - Access Routes And Cost Policy Boundaries
**Status:** Accepted
**Date:** 2026-09-21

Use access routes, not provider/model pairs alone, as the selectable execution
unit. Enforce tiered cost-policy boundaries before fallback so the system never
silently crosses from local/free/subscription allowance usage into prepaid
credits or metered billing.

Detailed ADR: `docs/decisions/ADR-021-access-routes-and-cost-policy.md`

## ADR-022 - Subtask Profile Derivation And Local Delegation
**Status:** Accepted
**Date:** 2026-09-23

Provide neutral subtask derivation and planning in `ai_orchestrator`. Subtasks
inherit the parent's privacy class by default, default to `LOCAL_ONLY` cost
policy to prefer free local compute for subsidiary steps, and isolate model
overrides from parent tasks.

Detailed ADR: `docs/decisions/ADR-022-subtask-profile-derivation-and-local-delegation.md`

## ADR-023 - Google / Antigravity Access Routes And Live Multi-Model Delegation
**Status:** Accepted
**Date:** 2026-09-24

Support Google Gemini and Antigravity access routes with strict route provenance
in the catalog to distinguish free studio quotas, IDE subscription allowances,
and metered routes. Provide an end-to-end multi-model delegation workflow
connecting local Ollama context extraction with hosted primary models.

Detailed ADR: `docs/decisions/ADR-023-google-antigravity-routes-and-live-delegation.md`

## ADR-024 - Codex CLI Parity, Authorization, And Development Tool Policy
**Status:** Accepted
**Date:** 2026-09-27

Use model-neutral approval policy presets for CLI parity, add only
development-relevant app/tool bridges as concrete needs appear, design read and
write capabilities together even when writes are disabled by default, expand
external connectors one at a time, and keep user authorization behind one
reusable boundary.

Detailed ADR: `docs/decisions/ADR-024-codex-cli-parity-authorization-and-dev-tool-policy.md`

## ADR-025 - Local-First Auxiliary AI Work
**Status:** Accepted
**Date:** 2026-09-27

Auxiliary AI work such as response scrutiny, context extraction, summarization,
prompt refinement, and other support passes should derive their own child task
profiles and prefer local or cheaper routes by default. Escalating auxiliary
passes to Codex, hosted APIs, prepaid credits, or metered billing requires an
explicit task need and visible route/cost reporting.

Detailed ADR: `docs/decisions/ADR-025-local-first-auxiliary-ai-work.md`

## ADR-026 - Agent-Specific Delegation As Default CLI Capability
**Status:** Accepted
**Date:** 2026-09-28

Use the `ai_agent` loop as the default provider-native implementation path in
the repo assistant CLI. The primary model receives a bounded `delegate_task`
tool so it can hand suitable support work, including small code writes under
the selected approval policy, to a derived local/cheaper child route.

Detailed ADR: `docs/decisions/ADR-026-agent-specific-delegation-default.md`

## ADR-027 - GitHub Publication Keeps The Workspace Monorepo
**Status:** Accepted
**Date:** 2026-09-28

Publish the project as one cleaned-up GitHub monorepo for now. Keep strong
internal package and app boundaries, make each meaningful component independently
documented and testable, and defer physical repository extraction until stable
APIs, release cadence, privacy boundaries, or review workflow create a concrete
need.

Detailed ADR: `docs/decisions/ADR-027-github-publication-monorepo.md`

## ADR-028 - SQLite Run Records For Orchestrated Repo Assistant
**Status:** Accepted
**Date:** 2026-09-29

Use a small SQLite-backed storage interface in `ai_provider` for local
orchestrated repo-assistant run and stage records. The first use is foreground
CLI tracking only; it does not introduce a daemon, queue, background runner, or
external service.

Detailed ADR: `docs/decisions/ADR-028-sqlite-run-records-for-orchestrated-repo-assistant.md`

## ADR-029 - Orchestrated Repo Assistant Supervised Validation
**Status:** Accepted
**Date:** 2026-09-30

Use a multi-pass supervised workflow direction for orchestrated implementation
runs, with local/cheap delegated support, deterministic pytest validation as
the default completion gate, Ruff/Pyright through pre-commit by default, and
configurable repair-cycle limits including an unbounded cycle setting that still
respects the wall-clock budget.

Detailed ADR: `docs/decisions/ADR-029-orchestrated-repo-assistant-supervised-validation.md`

## ADR-030 - Persistent Local Chat Transcripts
**Status:** Accepted
**Date:** 2026-09-30

Use local SQLite-backed provider-neutral chat transcripts for the first
interactive repo-assistant chat slice. Persist the message content sent to and
received from providers so chats can resume locally and later support model
switching without introducing personal memory, background jobs, queues, or
external transcript storage.

Detailed ADR: `docs/decisions/ADR-030-persistent-local-chat-transcripts.md`

## ADR-031 - User Preferences And Alternate CLI Agents
**Status:** Accepted
**Date:** 2026-10-01

Separate private user preferences from shipped defaults; default tasks allow
prepaid credits while the owner's local preference allows allowances only.
Enable official Antigravity, Copilot, and Kiro execution with only `trusted_local`
mapped. Requesty remains a prepaid provider API route.

Detailed ADR: `docs/decisions/ADR-031-user-preferences-and-alternate-cli-agents.md`

## ADR-032 - Automatic Usage-Limit Fallback
**Status:** Accepted
**Date:** 2026-10-01

Default coding-run fallback stays on the same billing tier and meets task
requirements, with quality grades influencing preference. Authenticate eligible
fallback clients before execution and continue from observed partial work without
mid-run user input. Exhaustion reports failure while preserving edits.

Detailed ADR: `docs/decisions/ADR-032-automatic-usage-limit-fallback.md`

## ADR-033 - Native Research Tools And Run Evidence
**Status:** Accepted
**Date:** 2026-10-01

Use an explicit local provider-native research profile with public HTTP(S)
fetching under existing CUSTOM permissions, report-target-only writes, and
current-run fetch/write receipts in existing SQLite stage metadata. External
clients are excluded because they own their tool registries.

Detailed ADR: `docs/decisions/ADR-033-native-research-tools-and-run-evidence.md`

## ADR-034 - SearXNG Research Discovery
**Status:** Accepted; routing/default superseded by ADR-036
**Date:** 2026-10-02

Originally approved configurable public SearXNG for free-default discovery.
Queries leave to the operator/upstream engines; inference remains local.
Endpoint is approved and live tested; ADR-036 records implemented provider fallback.
ADR-033's dated amendment records the approved model, sustained-review, and
free-default cost decisions without replacing its historical fetching slice.

Detailed ADR: `docs/decisions/ADR-034-searxng-research-discovery.md`

## ADR-035 - Run Artifact Layout
**Status:** Accepted
**Date:** 2026-10-02

Group generated reports, logs, acceptance fixtures, and dedicated run databases
under ignored `artifacts/<run>/`. Move historical artifacts while preserving
original write receipts, digest-bound relocation records, and database backups.
Shared ongoing application state remains in `data/`.

Detailed ADR: `docs/decisions/ADR-035-run-artifact-layout.md`

## ADR-036 - Research Search Routing and Fallback
**Status:** Accepted
**Date:** 2026-10-02

The owner approved Tavily, Brave, and SearXNG with bounded free-only fallback.
Ordinary research uses eligible APIs; requested reduced tracking stays on SearXNG.
Full local query receipts remain approved. ADR-034's original default/no-switch
policy is superseded; source-fetch evidence and local inference remain separate.

Detailed ADR: `docs/decisions/ADR-036-research-search-routing-and-fallback.md`

## ADR-037 - Source Evidence for Research Review
**Status:** Accepted; implemented
**Date:** 2026-10-02

The owner approved bounded in-memory fetched excerpts for local research review
after report/receipt-only reviews missed unsupported claims. Implementation
resumed on 2026-10-03 under the owner's unattended-work instruction. The owner also
approved bounded coverage across sources, advisory findings plus evaluation, an
optional enforced source limit unset by default, and counting distinct successfully
fetched final URLs. A blocking grounding gate requires a later decision after
evaluation. Implemented excerpts and source limits preserve existing completion
checks; the paired synthetic evaluation found substantial reviewer errors and
does not establish factual reliability. The ADR preserves policy trade-offs.

Detailed ADR: `docs/decisions/ADR-037-source-evidence-for-research-review.md`

## ADR-038 - Quality-First Research Review Presets
**Status:** Accepted; representative audit complete; opt-in policy; sustained acceptance incomplete
**Date:** 2026-10-03

Approve explainable capability-aware research reviewer/mode presets, bounded
2048-8192-token tuning, a larger final-review reserve, representative public-source
evaluation with local evaluation-only excerpt retention, and conditional research
activation after quality/software gates. Quality comes first; no charged calls
are authorized. The resumed implementation window was at most two hours, followed
by an explicitly allotted 90-minute continuation; longer testing remains planned
until selected and explicitly started with sufficient time. The 24-case corpus
and local experiment runner were executed in a subsequent explicitly authorized
three-hour local-compute session. All 72 cells were attempted and audited; direct
made a critical false approval, so D4 keeps opt-in. Isolated full-size tokenizer
capacity calls completed, but production admission remains conservative and the
fully allocated sustained acceptance stopped before refinement on that bound.
The owner subsequently approved optional explicit local-file configuration. Guarded
Qwen counting is implemented with conservative fallback; live integrated acceptance
is deferred while the owner needs PC capacity. See ADR-038 for supported scope.

Detailed ADR: `docs/decisions/ADR-038-quality-first-research-review-presets.md`

## ADR-039 - User-Started Budgeted Task Scheduling
**Status:** Accepted; SQLite, strict ordering and supervised research scope resolved
**Date:** 2026-10-03

Scheduled tasks remain planned until an explicit user command selects a sequential
execution window. Each task declares required time and is admitted only if it fits
the remaining allowance. No daemon/service is approved. The owner accepted existing
application SQLite storage, stopping at the first non-fitting task and initial
reuse of supervised research workers. Generic executor cancellation is deferred.

Pure task/time-admission contracts are implemented in `ai_orchestrator.scheduling`.
They do not start jobs or persist/mutate task state. The application-owned
`ai_provider.task_scheduler` implements durable definitions and explicit foreground
execution with a handoff reserve, atomic per-task claims and no automatic restart.
The owner-approved 2026-10-04 extension adds typed persisted reviewer/tokenizer and
repair settings plus a fixed supervised acceptance adapter with shared postchecks.
The additive task migration preserves existing definitions and lifecycle states.

Detailed ADR: `docs/decisions/ADR-039-user-started-budgeted-task-scheduling.md`

## ADR-040 - Shared Agent Tools And CLI Development Foundation
**Status:** Accepted direction and scope; implementation incomplete
**Date:** 2026-10-04

Share project-owned tools through MCP/native adapters while retaining official
allowance clients. Approve repository/Git tools, portable skills/instructions,
Python validation, documentation/public research, semantic code tools and
process/session continuity. PyCharm may host tools temporarily; eventually it
should only be the human editor/viewer. Preserve existing cost/privacy/approval
boundaries. Concrete persistence, process-host and dependency choices remain open;
optional capabilities and live execution are not included in this approval.

Detailed ADR: [ADR-040](decisions/ADR-040-shared-agent-tools-and-cli-development-foundation.md)
Milestones: [CLI development roadmap](repo-assistant/development-roadmap.md)

## ADR-041 - CLI Foundation Contracts And Local Supervision
**Status:** Accepted; implementation in progress
**Date:** 2026-10-04

Approve built-in common profiles/project-local skills, complete instructions with
a separate 64,000-character limit, scoped terminal mutation approval, temporary
project-owned IDE wrappers and optional official MCP SDK, foreground continuity
with existing SQLite storage, and verified native coding route preference.
Investigate bounded local interpretation of live results; deterministic process
waiting needs no model. Antigravity tool fallback stays excluded pending scoped
access. No daemon, global grant changes or generic scheduler are approved.

Detailed ADR: [ADR-041](decisions/ADR-041-cli-foundation-contracts-and-local-supervision.md)

### Owner return selections — 2026-10-04

The owner accepted the recommended local PyCharm HTTP-stream connection with
unrestricted execution disabled and initial read-only wrappers, and investigation
of the existing SearXNG search path. The concrete IDE connection configuration
remains unavailable. The owner additionally prioritizes model-overload recovery
and prevention/diagnosis of context-budget failures. This does not grant control
over the hosted PyCharm assistant or approve a new search operator/service.
Detailed checkpoint and remaining behavior choice:
[return checkpoint](repo-assistant/return-checkpoint-20261004.md).

## ADR-042 — Overload fallback and configurable continuation quality

**Status:** Accepted
**Date:** 2026-10-04

The owner requires overload and usage fallback while preserving work quality.
Default `preserve_quality` refuses weaker or ungraded continuation; explicit
`task_minimum` retains the previous policy. Overload disables a route rather than
its billing bucket; same-tier/privacy/tool limits remain. No suitable route produces
a local handoff without invoking a weaker model. ADR-032 is partially superseded.

Detailed ADR: [ADR-042](decisions/ADR-042-overload-fallback-and-configurable-continuation-quality.md)

## Research Review Execution Preference
**Status:** Accepted conditional authorization; current execution unchanged
**Date:** 2026-10-02

The owner permits CPU research reviews only if controlled retesting shows a
substantial performance advantage without reducing review quality. Quality takes
priority over speed. Retain the existing local reviewer/model and evidence
capacity while that condition is unproven. Contended measurements, such as tests
run alongside a game, do not justify switching execution. Notify the owner before
performance tests, as described in `docs/workflow.md`.

CPU execution avoids direct GPU contention but has slower cold prompt processing
and consumes CPU/RAM. GPU execution has faster measured cold review completion
in the owner's game-closed comparison, but competing workloads can affect it.
This preference does not approve smaller evidence windows or reduced output
capacity as a quality trade-off, and does not assert CPU/GPU quality equivalence.

## User execution defaults — accepted 2026-10-04

Owner approved exposing task quality, optional context/instruction limits,
request/validation timeouts and repair caps in the existing private `[defaults]`
configuration to avoid repeatedly specifying personal execution preferences.
Explicit CLI values win; shipped values and scheduler safety checks are preserved.
An explicit config timeout wins over away-mode automatic request sizing; an absent
key retains that sizing. Privacy and approval choices still require specific owner
selections. No new settings service or persistence mechanism is introduced.

## Session handoff selections — accepted 2026-10-04

Owner approved D1-D3 recommendations in the
[next-session brief](repo-assistant/next-session-decisions.md): configurable
privacy/approval defaults retaining `local_only`/`interactive`, investigation of
replacement SearXNG operators before specific operator selection, and design of
a bounded typed acceptance-job scheduler extension before concrete contract
approval. No broader shipped authority, operator switch, arbitrary-command queue,
new service or immediate live inference was approved.
D1 is implemented in `f86aca5`; the brief preserves alternatives and technical
rationale. D2 fresh operator probes remain deferred under the offline constraint.
D3's [concrete acceptance-job proposal](repo-assistant/acceptance-job-proposal.md)
is ready for contract review and is not an accepted ADR or implemented scheduler.

## Template
```text
## ADR-NNN — Short Name
**Status:** Proposed / Accepted / Superseded / Rejected
**Date:** YYYY-MM-DD

**Context**
What problem required a decision?

**Options considered**
- Option A
- Option B

**Decision**
What was chosen?

**Reason**
Why?

**Consequences**
```
