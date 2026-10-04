# Next session: plan and owner decisions

2026-10-04. Latest implementation slice COMPLETE; CLI foundation INCOMPLETE.
Owner approved recommendations D1-D3 on 2026-10-04. Implementation/investigation
remains INCOMPLETE. Alternatives below preserve the reviewed decision brief.

## Approval recorded

- D1-A: Implement configurable privacy and approval defaults, retaining shipped
  `local_only` and `interactive`. No broader default authority was selected.
- D2-A: Investigate replacement SearXNG operators through public, model-free
  shortlist/smoke checks. Present the specific operator before switching; no
  local service, keyed provider or repository-data transmission was approved.
- D3-A: Investigate/design a narrow typed acceptance-job scheduler extension with
  fixed harnesses, resource limits, receipts, deadlines and owned-process cleanup.
  Review the concrete contract before implementation. Arbitrary-command jobs and
  immediate live inference remain outside approval.

These selections implement the owner's approval of the recommendations as
presented; the technical trade-offs below preserve their rationale. Do not ask
the owner to approve the same directions again. New material choices, the IDE
endpoint and a compute window remain separate boundaries/inputs.

## Approved next implementation

The versioned native coding compatibility/estimated input-admission slice is now
**COMPLETE offline**; see [implementation and deferred checks](native-admission.md).
CLI foundation remains **INCOMPLETE**. The requirements below are retained as the
slice's acceptance contract, not a request to repeat completed implementation.
D1 configurable privacy/approval defaults are implemented offline. D2's fresh
public operator probes remain deferred under the current offline constraint.
D3's [concrete local-first job proposal](acceptance-job-proposal.md) is ready for
owner review; it is not an approved executable scheduler contract.
Shared external mutation approvals remain an approved foundation follow-up.

Implement versioned native tool-compatibility evidence and effective model-input
admission using existing routing/context contracts (ADR-041). Respect explicit
model selection; prefer verified GPT-OSS for automatic native tool routes.
Invalidate compatibility evidence after relevant model/runtime changes. Preserve
complete required instructions and refuse requests that cannot fit; distinguish
estimated byte admission from verified token counts. Use offline fixtures first.
Then continue shared terminal mutation approvals and external-client receipts.

Completion condition for the compatibility slice: deterministic compatibility/invalidation
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
Owner selection: A. Implemented offline with enum validation, explicit CLI
precedence, effective session privacy and retained read-only shared inspection.

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
Owner selection: investigate A. A shortlist does not authorize switching operators.

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
Owner selection: investigate/design A. This does not authorize inference immediately.
Concrete proposal: [typed acceptance jobs](acceptance-job-proposal.md). Approval
of this contract remains required before implementation; existing jobs are unchanged.

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
