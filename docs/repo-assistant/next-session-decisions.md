# Next session: plan and owner decisions

2026-10-06 update: ADR-045 records the owner's IDE-independence rationale.
ADR-046 additionally records the owner's selection of an explicit
`--validation-python` for the default pytest command, preserving the current
assistant-process default and custom validation commands. The rationale is
predictable selection without silent environment guessing, advancing IDE
independence. The effective default executable is reported in the run plan and
the actual executable is retained in validation results.
Native and synthetic shared-MCP rename preview, denial and owner-approved exact
apply passed on an isolated temporary package; both file effects were verified
and cleaned up. This does not establish physical terminal input or installed
third-party-client parity. The standalone `python_runtime` diagnostic and
orchestrated default validation interpreter binding are implemented; default
pytest now uses the repo-assistant's Python executable, and Windows quoted
validation paths preserve backslashes. Ruff/Pyright remain opt-in. SDK-based IDE
acceptance, grouped test-workflow slice,
and one owner-approved live shared-file-write approval are COMPLETE. The owner
supplied the IDE endpoint and selected authenticated foreground MCP under
ADR-044; these inputs are resolved. The confirmation came in chat and was
relayed into the controlling terminal, so this does not prove the owner
physically typed there. Shell approval and general client parity remain
unverified. The owner selected the Jedi-based preview-first rename direction
(option A) on 2026-10-06; its optional dependency and narrow tool contract are
implemented offline. The owner chose it to advance IDE independence while
permitting PyCharm as a temporary tool host; see ADR-045.
See the [implementation contract](semantic-refactoring-proposal.md),
[roadmap](development-roadmap.md) and [test workflow](../test-workflow.md).
The owner accepted grouped local checks and retaining direct URL fetching on
2026-10-05. Jenkins/hosted CI and a new search service are deferred; they do not
block independent implementation. A fresh unattended plan audit must substantiate
remaining candidates individually before treating the wider roadmap as blocked.
The fresh audit found and implemented additional eligible work; see
[evidence and remaining decisions](post-audit-decisions.md). Search replacement
is now deferred in favor of direct fetching. Historical D2 alternatives below
remain a record of the earlier investigation, not a current blocker.

The attended approval fixture's first terminal result was not retained, but its
process exited and cleaned the temporary directory. A second bounded run after
the owner's explicit `yes` passed through the actual foreground HTTP host and
terminal approval handler, verified the exact temporary file, and cleaned it up.
Its evidence and limitation are recorded in [post-audit decisions](post-audit-decisions.md).

Historical 2026-10-04 brief follows; completed tasks and resource restrictions
below are superseded by the current checkpoint and active owner's instruction.
Latest implementation slice COMPLETE; CLI foundation INCOMPLETE.
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
  Owner subsequently accepted the concrete local v1 contract on 2026-10-04;
  offline implementation is complete under ADR-043. Arbitrary-command jobs and
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
D3's [concrete local-first contract](acceptance-job-proposal.md) is accepted and
implemented offline. No executable job or compute window was selected.
Shared external mutation approvals and scoped receipts are implemented offline
under ADR-041. Live terminal/client permission acceptance remains deferred.

2026-10-05: fixed D3 native acceptance and shared `workspace_write` continuation
through real Copilot/Kiro passed. Interactive terminal acceptance is still pending.
The IDE endpoint and [foreground process-channel choice](process-sharing-decision.md)
are now resolved and their acceptance passed. D2's
[fresh operator investigation](search-operator-investigation.md) found no usable
JSON replacement; no operator setting was changed.

Implement versioned native tool-compatibility evidence and effective model-input
admission using existing routing/context contracts (ADR-041). Respect explicit
model selection; prefer verified GPT-OSS for automatic native tool routes.
Invalidate compatibility evidence after relevant model/runtime changes. Preserve
complete required instructions and refuse requests that cannot fit; distinguish
estimated byte admission from verified token counts. Use offline fixtures first.
Synthetic continuation after partial shared-tool effects is now COMPLETE offline:
actual MCP effects continue through Codex/Copilot mappings without replay, with
fresh approvals/run IDs, stable task identity and bounded external deadlines.
Updated saved session receipts accompany route switches. Full offline suite:
1091 passed, seven live skipped; Ruff and Pyright clean. Live client/terminal
mutation acceptance remains separate from this synthetic evidence.

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
Owner selection: A, including acceptance of the [concrete local v1 contract](acceptance-job-proposal.md).
Offline implementation is complete; see [ADR-043](../decisions/ADR-043-fixed-local-native-acceptance-jobs.md).
This does not authorize inference immediately; existing research jobs are unchanged.

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
