## ADR-077 - File state bound to remote Operator approvals

**Status:** Owner-approved and implemented, 2026-10-29.

Remote file mutations bind declared target state across the approval wait;
concurrent changes require fresh approval. Metadata-only privacy remains;
command-input protection is separate, and writes are not made atomic. See
[ADR-077](decisions/ADR-077-file-state-bound-operator-approval.md).

## ADR-076 - Host credential guards before storage migration

**Status:** Owner-approved sequence; first slice implemented, 2026-10-28.

Credential-file, known-credential tool-output and model-input guards come first.
Credential-store migration remains a complementary later design, not an exclusive
alternative. Existing storage is retained; this is not full privacy protection or
an OS sandbox. See
[ADR-076](decisions/ADR-076-host-credential-guards-before-storage-migration.md).

## ADR-075 - Metadata-only Operator approval descriptions

**Status:** Accepted and implemented, 2026-10-28.

Owner-approved bridge descriptions contain tool/category, workspace fingerprint
and argument types/sizes. Private argument names/values and workspace paths are
omitted; exact-action digest binding remains. Phone review needs a separate
authorized content-review channel. See
[ADR-075](decisions/ADR-075-metadata-only-operator-approval-descriptions.md).

## ADR-074 - Delegation inherits supervisor authority

**Status:** Accepted owner direction, implemented 2026-10-28.

Implementation workers inherit actual host-bound supervisor tools/permissions or
receive narrower grants. Descendants share finite reply/tool/deadline limits and
funded children retain the exact approved client. This is tool enforcement, not
OS isolation. See [ADR-074](decisions/ADR-074-delegation-inherits-supervisor-authority.md).

## ADR-073 - Shared Responses tools and stateless continuation

**Status:** Accepted and implemented; live C6 acceptance open
**Date:** 2026-10-28

The owner selected shared Responses tool serialization/parsing and stateless,
origin-bound continuation through the existing neutral contracts. Meta keeps
`store:false` and Contributor refusal. No server-managed history or approval-policy
change. Detailed ADR:
[ADR-073](decisions/ADR-073-shared-responses-tools-and-stateless-continuation.md).

## ADR-072 - Modal runtime provider route

**Status:** Accepted
**Date:** 2026-10-28

Add `AccessMethod.MODAL_RUNTIME`, `ProviderKind.MODAL`, and two
Modal billing sources (`MODAL_TOKEN_BILLING` for per-token Shared Endpoints /
Model API, `MODAL_RUNTIME_BILLING` for per-second serverless GPU/CPU) so
Modal-hosted OpenAI-compatible inference endpoints can be selected by the
orchestrator.
The first catalog route is `modal/qwen/qwen2.5-coder-7b-instruct` using
`Qwen/Qwen2.5-Coder-7B-Instruct`. Modal's per-second GPU billing is tracked as
a runtime source; hackathon vs monthly credit tags stay outside the app.

Detailed ADR: `docs/decisions/ADR-072-modal-runtime-provider-route.md`

## ADR-071 - Dedicated Meta Model API provider route

**Status:** Accepted
**Date:** 2026-10-27

Add `ProviderKind.META` and a dedicated `MetaResponsesChatClient` that inherits
the generic Responses adapter, defaults to `https://api.meta.ai/v1`, refuses
Contributor variants and non-`muse-` models, and forces `store: false`. The
catalog route `meta/muse-spark-1.3` is `prepaid_credits_allowed` while prepaid
credit remains; the owner's own Meta account keeps the route available after the
event.

Detailed ADR: `docs/decisions/ADR-071-meta-model-api-provider-route.md`

## ADR-070 - Host observations and scoped agent reports

**Status:** Accepted
**Date:** 2026-10-25

The owner approved explicit host adapter/validation observations alongside raw agent
reports scoped to repository/tool actions, preserved prospectively in conversation
history. Unknown effects remain unknown; consumed trials are unchanged.

Detailed ADR: `docs/decisions/ADR-070-host-observations-and-scoped-agent-reports.md`

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

**Status:** Accepted; default and weaker-model authority partially superseded by ADR-052
**Date:** 2026-10-04

The owner requires overload and usage fallback while preserving work quality.
Default `preserve_quality` refuses weaker or ungraded continuation; explicit
`task_minimum` retains the previous policy. Overload disables a route rather than
its billing bucket; same-tier/privacy/tool limits remain. No suitable route produces
a local handoff without invoking a weaker model. ADR-032 is partially superseded.

Detailed ADR: [ADR-042](decisions/ADR-042-overload-fallback-and-configurable-continuation-quality.md)

## ADR-052 - Configurable emergency preservation and quality-preferred fallback

**Status:** Accepted; offline validation, live acceptance pending
**Date:** 2026-10-11

The owner approved both policies so the Orchestrator selects replacements without
manual model selection. Default `emergency_preserve` keeps implementation quality,
saves a deterministic handoff, then permits weaker read-only reporting. Explicit
`prefer_quality` tries stronger routes first and permits weaker implementation.
Privacy, billing tier, scoped approvals and deadlines remain enforced; downgrades
are reported. Legacy policies remain selectable.

2026-10-21: the owner selected existing `task_minimum` with a `standard` task
floor for private daily use, permitting Kiro/Copilot coding continuation below
Codex's declared grade. The shipped default is unchanged. Native capabilities
may be added with verified equivalent permissions and observable effects;
shared approval enforcement remains required. See the ADR's dated selection.

Detailed ADR: [ADR-052](decisions/ADR-052-emergency-preservation-and-quality-preferred-fallback.md)

## ADR-053 - Fixed away-session allowance

**Status:** Accepted; implemented and tested offline, live pilot deferred
**Date:** 2026-10-11

The owner selected a fixed `--away-minutes` session allowance and wants separate
turn limits named explicitly for turns (`--turn-timeout-seconds`). Each launch
explicitly supplying the away option grants fresh time, including saved-session
resume; turns within that launch cannot reset it. No deadline persistence or
restart-reason exceptions are added.
See [ADR-053](decisions/ADR-053-fixed-away-session-allowance.md).

## ADR-054 - External sign-in for coding-chat

**Status:** Accepted; implemented offline, live acceptance pending
**Date:** 2026-10-11

The owner selected sign-in outside continuous coding-chat to avoid competing
terminal readers. Missing primary readiness refuses execution, including with
fallback disabled; unauthenticated optional routes are excluded. Standalone
requests retain existing interactive preflight. See
[ADR-054](decisions/ADR-054-external-sign-in-for-coding-chat.md).

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
D3's [concrete acceptance-job contract](repo-assistant/acceptance-job-proposal.md)
was subsequently accepted; its offline implementation is recorded in ADR-043.

## ADR-043 — Fixed local native acceptance jobs

**Status:** Accepted; offline implementation complete; live acceptance deferred
**Date:** 2026-10-04

Add one versioned, immutable local coding fixture job to existing SQLite storage.
Reuse explicit sequential time admission, require actual read/edit effects and
fixed host validation, and retain Windows process-tree ownership through cleanup.
Preserve research contracts; defer hosted and arbitrary-command jobs. Contract
approval does not authorize live inference or select a compute window.

Detailed ADR: [ADR-043](decisions/ADR-043-fixed-local-native-acceptance-jobs.md)

## ADR-044 — Authenticated foreground loopback MCP host

**Status:** Accepted; foreground host and read-only IDE bridge acceptance passed
**Date:** 2026-10-05

The owner selected authenticated loopback MCP for shared foreground process access,
because authentication, connection/session lifecycle and shutdown behavior should
be implemented now rather than deferred. Existing supervision, permissions,
receipts and restart reconciliation remain in force. PyCharm configuration is
imported per machine into ignored local storage.

Detailed ADR: [ADR-044](decisions/ADR-044-authenticated-foreground-mcp-host.md)

## ADR-045 — IDE-Independent Semantic Rename
**Status:** Accepted; bounded native/shared MCP acceptance passed; installed-client acceptance pending
**Date:** 2026-10-06

Add an optional standalone Jedi-based Python rename preview/apply pair to advance
IDE independence. PyCharm may continue hosting tools during the transition.
Disposable native/shared MCP acceptance passed; installed-client acceptance and
the broader IDE-independence milestone remain separate.

Detailed ADR: [ADR-045](decisions/ADR-045-ide-independent-semantic-rename.md)

## ADR-046 — Explicit Interpreter for Default Validation
**Status:** Accepted
**Date:** 2026-10-06

Add an explicit `--validation-python` override for the built-in pytest command.
Keep the repo-assistant executable as the default and never rewrite explicit
`--validation-command` values. The owner chose this for predictable selection
without silent environment guessing and to advance IDE independence.

Detailed ADR: [ADR-046](decisions/ADR-046-explicit-validation-interpreter.md)

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

## ADR-047 - Fail-Closed Execution Boundaries

**Status:** Accepted (2026-10-08); CLI ownership resolved by ADR-048.
The legacy email entry point now uses preview and explicit guarded delivery.

Refuse authenticated provider redirects, validate tool arguments before approval,
contain recursive search, bound Council/public HTTP reads, bind application
approval to exact materials, and test real package execution boundaries.
See [ADR-047](decisions/ADR-047-fail-closed-execution-boundaries.md).

## ADR-048 - Agent-Owned Repository Assistant CLI

**Status:** Accepted (2026-10-08).

The owner approved moving the command, CLI implementation, argument parsing and
execution settings to `ai_agent`. Provider/client adapters remain in `ai_provider`;
old CLI module imports delegate for compatibility without a reverse dependency.
This supersedes their historical provider placement, leaving wider helper
migration outside scope. See [ADR-048](decisions/ADR-048-agent-owned-assistant-cli.md).

## ADR-049 - Continuous Coding Chat

**Status:** Accepted direction (2026-10-09); migration acceptance incomplete.

The owner selected a distinct continuous coding-chat mode with a reusable
foreground controller and existing local SQLite records. Preserve scoped tools,
instructions, decisions and recovery boundaries across turns. Migration requires
comparable development quality and measured delegation economics, not merely
passing tool fixtures. The owner also accepted deterministic local history
reduction: preserve owner messages/host outcomes, shorten older assistant reports
visibly, retain originals and refuse mandatory-context overflow.
Owner clarification (2026-10-12): tools remain enabled for development and review;
disable only for specific explicitly selected narrow cases. A general report-only
phase is not the remedy for repeated reads or weak tests. Existing scope and
approvals remain applicable.
See [ADR-049](decisions/ADR-049-continuous-coding-chat.md).

## ADR-050 - Usage Measurement and Automatic Integration

**Status:** Accepted direction (2026-10-10); Codex/Copilot observations and Kiro native estimates integrated.

Measure external allowance/API spend and local total tokens plus elapsed time.
Consider time without a hard median-completion-time rejection gate. Grow automatic
provider usage integration incrementally, including provider-specific adapters.
The owner selected Codex first because it is their main source. Its bounded native
reader now automatically reports quota windows before execution, retaining source
and observation time in memory; Copilot's native quota types and request counters
are also supported, with verified installed-client reads. Pinned Kiro 2.24.0 V2
sessions add isolated native credit estimates with unknown remaining balance;
Antigravity startup isolation remains unproved. Routing is unchanged. The owner
adopted a 20% measurable external savings target; below-target results require
case-by-case review rather than automatic rejection. Strict quality remains required.
See [ADR-050](decisions/ADR-050-usage-measurement-and-automatic-integration.md).

## Owner product priorities - 2026-10-10

The owner selected CLI, job search, business, then Council, reflecting their real
needs. This supersedes earlier Council-first planning guidance. Prerequisites
support the selected track; ordering does not authorize unresolved implementation
contracts, integrations or privacy changes. See the current priority rules in
[workflow](workflow.md#current-product-priorities).

## ADR-051 - Openings API Integration

**Status:** Accepted direction (2026-10-10); offline bridge implemented, deployment unvalidated.

The owner approved a reviewed upstream mirror fix plus an external API bridge,
keeping preparation code independent of Openings internals at the cost of patch
maintenance. Intake explicitly uses `new`; tracking never grants delivery consent.
No deployment or candidate-profile transmission is approved by this choice.
See [ADR-051](decisions/ADR-051-openings-api-integration.md).

## ADR-056 - Measured-prefix native admission prototype

**Status:** Accepted prototype and explicit experimental CLI opt-in; broader validation incomplete.
The owner approved investigating provider-reported prefix counts with strict
identity checks, conservative appended estimates and absolute-gate fallback.
The owner subsequently approved `--experimental-measured-prefix` for native
Ollama coding. Production default, complete instructions/history and acceptance
gates remain unchanged; the choice does not establish coding-quality readiness.
See [ADR-056](decisions/ADR-056-measured-prefix-admission-prototype.md).

## ADR-055 - Explicit provider continuation metadata

**Status:** Accepted and implemented (2026-10-11); coding-workflow acceptance incomplete.

Carry transient adapter-owned state on AIMessage, tagged by provider/model/endpoint.
Replay only to that target; keep it out of answers, normal representations and
durable conversations. Include its size in input admission. The owner chose this
over hidden adapter caches and prioritized official-documentation conformance.
See [ADR-055](decisions/ADR-055-explicit-provider-continuation-metadata.md) and
the [high-priority repo-wide plan](documentation-conformance-plan.md).

## ADR-057 - Free Gemini CLI And OpenRouter Access Direction

**Status:** Accepted direction (2026-10-13); OpenRouter free-first prioritized and implemented offline (2026-10-14); Gemini individual-access pilot blocked
by verified service retirement (2026-10-14). Offline integration is preserved;
Owner subsequently selected the already requested OpenRouter free-only integration;
no paid billing route or transfer of the unused Gemini inference grant is approved.

Owner approved Gemini CLI and requested OpenRouter connection, preferring another
free source before an explicitly deferred $10 deposit. Keep product/auth/billing
provenance separate. Personal Requesty deposit avoidance does not remove paid
product support. Cerebras and Zed/Delta promotions are deferred. No defaults,
quality promotion, purchase or paid fallback approved. Owner selected project-scoped
environment changes; Python `.venv` and external runtimes remain separate. OpenCode
Console is deferred. See installation guidance for the project-local setup direction.
See [ADR-057](decisions/ADR-057-free-gemini-cli-and-openrouter-direction.md).

Provider-contract clarification accepted (2026-10-16): the owner approved using
the existing sanitized root-error categories for OpenRouter choice-level errors
(option A), with non-retryable classification for an error finish lacking usable
details. This preserves provider distinctions over the alternative of stopping
every such error as non-retryable. Newly recognized quota/rate-limit errors enter
only existing eligible fallback; privacy, billing sources, quality floors and
context-headroom policy are unchanged. This is an adapter conformance fix, not
general CLI/model-quality acceptance or permission for a new inference source.

## ADR-058 — Opt-in task sampling controls

**Status:** Accepted (2026-10-15); implemented offline, live acceptance incomplete.

Owner accepted opt-in per-run temperature/top_p controls with existing defaults
preserved. Forward explicit values through task API/native loops and compatible
fallback; refuse external clients without a verified mapping. No automatic model
preset, template override, persisted default or fresh live grant is implied.
See [ADR-058](decisions/ADR-058-opt-in-task-sampling-controls.md).

## ADR-059 - Context-aware observable fallback history

**Status:** Accepted (2026-10-15); implemented offline, live acceptance incomplete.

Owner selected full observable history for eligible native coding fallback only
when input, tools, output and framing leave at least 20% destination headroom.
Otherwise retain the bounded handoff, including unknown effective capacity.
Provider-private reasoning, weaker preservation prompts and saved handoffs remain
excluded. Rationale: replacement models have different context limits.
See [ADR-059](decisions/ADR-059-context-aware-observable-fallback-history.md).

## ADR-060 — Structured CLI error attribution

**Status:** Accepted (2026-10-18).

Owner approved optional structured error metadata and readable terminal
attribution, with a bounded safe fallback-handoff projection. Reuse ProviderError
and existing transcript JSON metadata; no SQL migration or raw-cause logging.
Missing attribution remains unknown, and effective route is separate from the
error's reporting provider. Existing fallback/privacy/approval policies remain.
See [ADR-060](decisions/ADR-060-structured-cli-error-attribution.md).

## ADR-061 — Shared model-output correction

**Status:** Accepted and implemented offline (2026-10-18); live acceptance incomplete.

Owner chose shared-agent recovery guided by expert feedback/effect-check/resource-
bound principles. Known pre-tool argument failures use a neutral error signal and
safe correction feedback; repeated failures without observed progress stop with
an actionable handoff. No universal one-correction-per-turn cap, tool replay,
transport retry, new service or approval weakening. See
[ADR-061](decisions/ADR-061-shared-model-output-recovery.md).

## ADR-062 — Optional task-completion evidence

**Status:** Accepted and implemented offline (2026-10-19),
live acceptance incomplete.

Owner selected optional shared-agent completion evidence over private pilot-only
feedback. Caller-declared objective checks may return fixed host feedback before
final completion, retaining model candidates, history and original limits.
Repeated missing evidence at the same observed state stops; no permissions,
generic prose grading, storage or default policy change. See
[ADR-062](decisions/ADR-062-optional-completion-evidence.md).

## ADR-063 — Explicit public-input privacy exception

**Status:** Accepted and implemented offline (2026-10-21); live access unverified.

Owner permits possible retention/training only for explicitly public/synthetic
requests. OpenRouter requires the low-risk privacy class and a request-local exact
boolean attestation; private/default requests retain their guard. Price/quota and
requested privacy filters remain. See
[ADR-063](decisions/ADR-063-explicit-public-input-privacy-exception.md).

## ADR-064 — Visible warning for unresolved MCP recovery

**Status:** Accepted and implemented offline (2026-10-22); live behaviour
unverified.

Owner approved reporting an MCP failure that call identity cannot resolve as a
visible warning beside a completed result, for both unresolved call identity
and a same-tool retry under a new call id. A run that independently proves
completion is no longer reported as failed; fatal, incomplete and unfinished
runs still fail. The unresolved reasons are retained. See
[ADR-064](decisions/ADR-064-visible-warning-for-unresolved-mcp-recovery.md).

## ADR-065 - Route-id naming convention: `provider/product-model`

**Status:** Accepted

**Date:** 2026-10-22

All access-route ids use `provider/product-model`, with the product omitted
when it only repeats the provider and model ids keeping their native punctuation
(`:`, `.`, `/`). `product` stays in the label so ADR-021 billing boundaries stay
visible at a glance; route ids remain opaque keys and are never parsed. The
convention amends ADR-021's display/selection form, not its identity semantics.
Separately, `--provider` no longer hardcodes its choices and is validated against
the loaded catalog, so every declared provider (including `github`, `kiro`,
`opencode_go`) is accepted. See
[ADR-065](decisions/ADR-065-route-id-naming-convention.md).

## ADR-066 — Scrutiny is advisory; its findings must reach the model

**Status:** Accepted (advisory policy); revision-loop extension design confirmed
by owner 2026-10-23 (Option B minimal loop; Option B `format_issues` rendering)

**Date:** 2026-10-23

Owner made orchestrated scrutiny advisory by default: a non-`pass` verdict
records findings, risks and a next action, but does not by itself decide that
the work is unaccepted, because it falsely blocks too much in practice. A hard
requirement stays available as an explicit future option rather than being
deleted. A malformed review report is recorded as a *review failure* and must
never stand in for a quality verdict — the current hard gate on an exact
6-heading format lets a local model's formatting decide the outcome.

Investigation established that scrutiny is **terminal, not a feedback loop**:
it runs after the last repair, `repair_workflow.py` never references it, and
its `revised_response` is rendered as "not applied or independently verified".
The intended corrective design already exists for the research profile
(`ai_provider.research_refinement`) and is the reference implementation to
extend to coding. Owner chose the **minimal loop** (Option B): one extra
scrutiny-fed repair pass gated on the existing `--max-repair-cycles`, deferring
the full guard set (review-time reserve, no-progress fingerprint) until live
signal justifies it. `format_issues` renders in the closeout only when
non-empty on a `pass` verdict (Option B). See
[ADR-066](decisions/ADR-066-scrutiny-is-advisory-and-its-findings-must-reach-the-model.md).


## ADR-067 - Temporary: Codex write delegation runs with the sandbox bypass

**Status:** Accepted as a temporary workaround, flagged for replacement

**Date:** 2026-10-23

Codex write delegation is blocked on this machine: the PyCharm-bundled binaries
(0.137.0 rejects all model ids; 0.160.1 works but its sandbox backend is
disabled, so workspace-write still cannot write). The owner chose to run write
delegations with `--dangerously-bypass-approvals-and-sandbox` as an explicitly
**temporary** solution. Compensating controls: git diff review of every Codex
write against a pre-run snapshot, prompts restricted to named files, no secrets
in prompts, read-only analysis keeps its normal sandbox. Exit when a working
sandbox backend, a fixed bundled binary, or a proper CLI install exists. See
[ADR-067](decisions/ADR-067-temporary-codex-sandbox-bypass-for-delegated-write-work.md).


## Go Kimi native coding output default - 2026-10-23

Owner selected the automatic default after confirming the proposed cap was
16000 output tokens per call. Native coding admission now reserves 16000 for
exactly opencode_go / kimi-k2.7-code when no request limit was supplied. Explicit
limits and other models' defaults are unchanged. This uses the existing neutral
request field before sizing; insufficient context refuses rather than reducing
the selected default. No new CLI option, billing source or reasoning persistence.
The owner selected this over an explicit CLI budget option; no additional rationale
is inferred. See source-state for the official Kimi recommendation and ADR-055
for transient continuation handling. This default is not live quality acceptance.

## CLI baseline support routing - owner clarification 2026-10-24

Keep auxiliary review and scrutiny on local models for the next Go-primary CLI
baseline, consistent with ADR-025. Escalation to a wholly paid-tier workflow is
permitted if observed evidence establishes that local models do not handle the
required support well. Local token economy is secondary to adequate context,
output and execution time; preserve finite run/cleanup bounds and count all
roles, while reporting hosted allowance consumption separately. This is task
authority, not an automatic routing-policy change or permission for overage,
new private payloads, or unbounded retries. Preserve each consumed result.

## ADR-068 - Free routes are the default preference

**Status:** Accepted

**Date:** 2026-10-24

Owner decision: free routes are preferred by default and more free sources are
welcome. Free-first ordering applies whenever a free route can actually serve
the task's quality, privacy, capability and provider requirements; it never
waives those requirements, never authorizes paid overage, and never turns a free
route's provisional quality into a measured claim. The default catalog now
declares an OpenRouter free route; that route is declared but not yet ordered
because the no-credits account is refused by the entitlement guard for ordinary
CLI requests. See
[ADR-068](decisions/ADR-068-free-routes-are-the-default-preference.md).

## ADR-069 — Restricted reviewed non-sensitive input

**Status:** Accepted direction, 2026-10-25.

Owner selected A: restricted task access with reviewed non-sensitive inputs and
controlled tools/credentials, while keeping genuinely private data and API keys
out. The narrow implementation uses one exact digest-bound input without tools,
ambient repository context, history or continuation. ADR-063 public/synthetic
attestation is unchanged. B, protection for general repository access, is planned
rather than enabled. No purchase or broad privacy bypass is authorized.

See [ADR-069](decisions/ADR-069-restricted-reviewed-non-sensitive-input.md) and
[the A/B plan](repo-assistant/restricted-input-plan.md).
