# Next session: plan and owner decisions

2026-10-04. Latest implementation slice COMPLETE; CLI foundation INCOMPLETE.
This is a pending decision brief, not approval or a replacement for ADRs.

## Approved next implementation

Implement versioned native tool-compatibility evidence and effective model-input
admission using existing routing/context contracts (ADR-041). Respect explicit
model selection; prefer verified GPT-OSS for automatic native tool routes.
Invalidate compatibility evidence after relevant model/runtime changes. Preserve
complete required instructions and refuse requests that cannot fit; distinguish
estimated byte admission from verified token counts. Use offline fixtures first.
Then continue shared terminal mutation approvals and external-client receipts.

Completion condition for the next slice: deterministic compatibility/invalidation
and input-fit refusal tests, reviewed focused commit, updated roadmap/handoff and
specified bounded live checks. No new compute window is currently authorized.
The PyCharm bridge can proceed after the explicit local endpoint is supplied;
its read-only scope and optional official MCP SDK are already approved.

## D1: privacy and approval defaults in user configuration

These affect external data routing and command/write authority. Current CLI
choices already exist; this decision concerns persistent personal defaults.

- A: Add configurable defaults with shipped `local_only` and `interactive`.
  External routing and broader permissions still require explicit per-run/config
  selection. Supports personal preferences without broadening shipped authority.
- B: Select `external_allowed` and/or a broader approval default now.
  Convenient for hosted agents/unattended work, but permits more data transfer
  and actions without the same repeated human involvement.
- C: Keep privacy and approval CLI-only. Least work, less convenience.

Recommendation: A. `workspace_write` permits workspace file writes but denies
legacy shell actions; `trusted_local` allows local writes/shell. Neither should
be adopted automatically just to make tests run unattended. A default is not a
substitute for task-level privacy classification or native client restrictions.
Question: approve A, keep C, or explicitly select broader values under B?

## D2: restore search after the public SearXNG instance fails upstream

Existing endpoint returns HTTP 200 with zero results and suspended engines.
Direct public URL fetching works. This is an operator problem, not evidence that
the project can repair the operator's upstream configuration.

- A: Select another explicitly configured SearXNG operator after a public,
  model-free shortlist/smoke check. No new local service; availability and query
  privacy depend on that operator. Do not send repository content during probes.
- B: Host SearXNG locally. Operator control, but new service/container maintenance.
- C: Select a keyed search provider. Potential reliability benefits; credentials,
  external query processing and possible billing must be selected explicitly.
- D: Defer search acceptance and continue direct-source/offline implementation.

Recommendation: A; choose D if search is not needed in the next slice.
Question: investigate a replacement SearXNG operator, host locally, select a
keyed provider, or defer? A shortlist does not authorize switching operators.

## D3: scheduler scope for deferred live acceptance

Existing scheduler executes typed supervised research tasks. It must not be
presented as a generic coding/evaluation queue. Earlier failed refinement
acceptance remains failed even though a reviewer passed an intermediate result.

- A: Design a narrow typed acceptance-job extension using fixed project-owned
  harnesses, explicit model/account/resource limits, durable result receipts,
  deadlines and owned-process cleanup. Reuses scheduler supervision while adding
  a public job contract; investigate the exact contract before implementation.
- B: Keep the research-only queue; perform other live checks manually in selected
  windows. Smallest scope, less automation.
- C: General arbitrary-command jobs. Flexible but introduces much broader
  execution/security/recovery obligations than the demonstrated need.

Recommendation: A if automated acceptance is wanted; otherwise B. Defer C.
Question: approve investigating the bounded typed acceptance extension, or keep
non-research checks manual? Neither selection authorizes inference immediately.

## Inputs and deferred options, not new approval requests

- Supply the credential-free local HTTP Stream config shown by PyCharm MCP
  settings; unrestricted execution stays disabled. Bridge activation scope is
  already approved. IDE-host tools in this chat do not prove CLI connectivity.
- Select a compute window before live overload/fallback/handoff and repaired
  research refinement acceptance. Keep unsupported cases in the backlog, not as
  fabricated executable queue entries. Deterministic completion uses process
  status; a local model is useful only for bounded interpretation.
- Browser/UI testing, notebooks, debugger control, GitHub, visual documents and
  image generation remain optional. Recommend completing C1-C6 before selecting
  these, unless an immediate application task demonstrates the need.
- Preserve reports, queue records and interruption/ownership receipts. This
  session's cleanup means clarifying docs and saving work, not deleting artifacts.

## Session boundary

Use a new session at this committed logical checkpoint. A reported 55M cached
input total does not by itself establish live context size or remaining quota.
Current IDE `/status` is needed for those signals; no exact savings are promised.
The immediate handoff and copyable resume prompt are in `CURRENT_CONTEXT.md`.
