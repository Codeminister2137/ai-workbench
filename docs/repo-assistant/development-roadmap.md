# CLI Development Foundation Roadmap

[CLI guide](../repo-coding-assistant.md) ·
[Accepted scope: ADR-040](../decisions/ADR-040-shared-agent-tools-and-cli-development-foundation.md)

## Status and outcome

**INCOMPLETE — independent foundation slices implemented; design and acceptance gaps remain.**
Decision and milestone recording is complete as of 2026-10-04. Verified tools and
fallback are foundations; they do not constitute completed cross-agent parity.

The current [next-session plan and approved directions](next-session-decisions.md)
records D1-D3 approval: conservative configurable privacy/approval defaults,
replacement SearXNG investigation, and the accepted local typed acceptance-job
contract. D3 is implemented offline under ADR-043; live execution still needs an
explicit compute window. Specific SearXNG operator selection remains unresolved.
Historical checkpoints below retain their original validation counts. The latest
full offline checkpoint is 1106 passed, seven live tests skipped, Ruff/Pyright clean.

The goal is to perform inspect/plan/edit/test/review workflows from the project
CLI, invoke the required skills, resume work and recover from allowance exhaustion
with the common tools still available. PyCharm may host tools initially; eventually
it should only be the human editor/viewer. Different model performance is allowed.

## 2026-10-05 checkpoint and remaining boundaries

**Current slices COMPLETE; remaining CLI foundation BLOCKED on concrete inputs/decisions.**

Final validation: 1106 passed, seven live tests skipped in 142.00 seconds; repository
Ruff lint/format, Pyright and focused commit hooks passed. Separate live results
below are preserved independently of the skipped optional integration tests.

- Shared partial-effect fallback retains complete instructions, objectives,
  task identity, fresh run scopes/approvals, updated receipts and external deadlines.
- Saved foreground process observations survive route changes; an actual synthetic
  in-flight child is polled through the same handle without relaunch. Restarted
  handles remain metadata, not attachment authority.
- Fixed D3 native acceptance passed with real GPT-OSS read/edit effects, host
  validation and verified runtime/worker/validator cleanup. Two earlier startup
  failures remain preserved. Existing model-library configuration is retained;
  owned acceptance runtimes disable cloud discovery/pruning and bound metadata
  readiness retries. No download or global setting changes were made.
- Real Copilot 1.0.91 and Kiro 2.24.0 continued a synthetic Codex quota failure
  using shared workspace writes. Each fixture recorded exactly two successful
  edits under distinct run IDs, retained the partial comment and passed host
  assignment validation. This is bounded continuation evidence, not complete
  tool/skill/interactive-approval parity.
- The [D2 public operator investigation](search-operator-investigation.md) found
  no usable JSON replacement. No configured search operator was changed.

The owner subsequently selected authenticated loopback MCP in
[ADR-044](../decisions/ADR-044-authenticated-foreground-mcp-host.md) and supplied
their machine-local PyCharm endpoint. The shared foreground host is implemented:
fresh bearer/session scopes, start/status/stop across routes, denial/expiry,
interruption cleanup and restart refusal. Real Copilot and Kiro each polled the
same live child after synthetic quota fallback and completed the partial edit;
both children were cleaned up. Four failed Copilot handshake runs are preserved;
the newer `server/discover` probe now receives the supported protocol fallback.

The read-only IDE wrappers/configuration importer are implemented, with the
supplied endpoint saved only in ignored local storage. After the owner's SDK
installation approval, SDK interoperability and all three project IDE wrappers
passed, including successful IDE session deletion. Missing-SDK/unavailable-endpoint
diagnostics were verified. See [local setup](local-tool-hosts.md).
Interactive human approval acceptance still requires an attended terminal.
Antigravity remains excluded. This is bounded acceptance, not full tool parity.
Component selection and suite timing are documented in [test workflow](../test-workflow.md).
The workspace check also runs the previously omitted Council suite separately.

Wider master/Council/Orchestrator plans were checked against the current code.
Their historic unchecked foundation items are not fresh implementation tasks.
Council synthesis/application integration, job-search ingestion/evidence storage
and quota-source integration need focused API/data/provider decisions before
starting a separate feature track. Optional capabilities remain outside C1-C6.

## Approved capability set

| ID | Capability | Required outcome |
| --- | --- | --- |
| C1 | Repository tools and local Git | Inspect, search, edit and review changes under the selected permissions |
| C2 | Portable skills/instructions | Discover and invoke development skills with checked dependencies and applicable repository instructions |
| C3 | Python environment/validation | Select the correct interpreter and run tests, lint and type checks with useful diagnostics |
| C4 | Documentation/public research | Retrieve permitted sources and preserve provenance |
| C5 | Semantic code tools | Navigate symbols/references and perform supported safe refactoring |
| C6 | Process/session continuity | Poll/interrupt operations and continue coding through turns and route switches |

## Milestones

| ID | Milestone | Status | Completion condition |
| --- | --- | --- | --- |
| M1 | Readiness and adapter contracts | In progress; offline fallback diagnostic slice verified | Deterministic route/tool/skill/approval checks explain eligibility and exclusions; forced-limit coverage preserves tier and task constraints |
| M2 | Common tools and portable skills | In progress; shared inspection works on three official clients; portable Copilot skill fixture passed | C1-C4 work through common contracts on selected routes; explicit skills resolve dependencies; required instructions are available or omissions cause a clear refusal |
| M3 | Semantic tooling with temporary IDE host | Pending CLI bridge; direct host operations verified | Selected C5 operations work through a verified PyCharm bridge with defined semantics and permissions |
| M4 | Coding and process continuity | In progress; opt-in native sessions and foreground children implemented | Agreed session/process model preserves objective, decisions, scoped approvals, receipts and handles across turns and fallback; uncertain effects are reconciled |
| M5 | Independence from the IDE tool host | Pending | Approved C1-C6 workflows remain usable with PyCharm tool hosting unavailable; PyCharm can serve only as editor/viewer |

Each milestone has deterministic correctness checks and separately recorded live
acceptance where necessary. A milestone cannot be reported fully accepted on
synthetic evidence alone when it requires an installed client or IDE bridge.
Deferred live checks must not prevent independent offline implementation.

### M1: imperative next action

First slice implemented on 2026-10-04: `--fallback-readiness` reports static
policy and executor exclusions without authentication/tool/provider probes;
execution preflight retains precise incompatibility reasons. Same-tier and
different-bucket policy tests now cover every cost ceiling. Full offline suite:
828 passed, seven live tests skipped; Pyright clean. Fresh synthetic-exhaustion
acceptance continued a partial edit through real Copilot and passed its fixture.
These results do not prove canonical tool/skill parity or alternate approval modes.

Implemented context slices include nested repository instructions for selected
paths and visible context truncation/omission diagnostics. Existing budgets still
apply; enforcing complete required instructions remains a decision. A model-free
`--read-search-only` MCP profile exposes repository inspection tools. A
bounded real Copilot acceptance discovered and called `find_files`, `list_dir`
and `read_file` with explicit read/search grants, returned the fixture marker and
left the fixture unchanged. Further isolated fixtures connected Codex and Kiro to
the same inspection profile. Codex found an injected regression through shared
Git/read/search tools; Kiro returned a marker using shared file discovery/read.
These checks confirm three client connections, not write/shell, all-client parity
or fallback with common MCP configuration. Codex's review is not evidence of a
dedicated native skill activation receipt.

All four configured official clients are discovered when the repository's normal
environment file is loaded, and their existing authentication checks report ready.
This does not establish remaining allowance or equivalent authorization. An
Antigravity inspection fixture returned exit zero with no answer or tool receipts:
headless MCP permission was auto-denied. The adapter now reports that explicit
diagnostic as failure while preserving the process status. Narrow native grants
and common approval mapping remain unresolved; no global permission settings
were changed for this fixture. A separate short tool-free Antigravity request
returned the expected answer; basic execution works despite the MCP refusal.

Native coding and the opt-in inspection MCP profile now share bounded local Git
status/diff tools under READ permissions; the default Codex delegation profile
is unchanged. Focused fixtures verify index preservation, staged/unstaged diffs,
literal paths, outside-root refusal and disabled external diff helpers.
Final review also verified that ordinary Git diff can execute configured content
filters. Inspection now disables clean/process helpers and nested submodule content
scans, preserves pointer changes, and reports raw-content comparison explicitly.
Regression fixtures verify helpers do not run and configuration/index stay intact.

A portable `review-repo-change` skill source lives under `packages/ai_agent/skills/`.
Its syntax validator passed. Copilot CLI 1.0.91 discovered an isolated fixture copy,
produced an explicit skill invocation receipt, used shared Git/read tools and
reported an injected regression without changing files. This is one bounded
read-only skill acceptance; automatic installation, common discovery/dependency
checks and provider-native skill activation remain incomplete.

Native coding now uses an actual-tool prompt and retains receipts on bounded
loop failure or an unexecuted final textual request. A live local GPT-OSS coding
fixture performed inspect/edit/PowerShell validation/diff successfully. A paired
20-task synthetic probe returned real tools on GPT-OSS (19/20 strict checks under
each prompt; both missed checks only removed a final newline). Qwen2.5-Coder
returned textual requests with no actual calls on all 20 tasks under each prompt.
No broad model-quality or pass-rate improvement is established; model-native
tool compatibility remains a readiness gap. Catalog routing was not changed.

Direct current-session PyCharm host checks verified interpreter selection, symbol
information, diagnostics and a rename that updated an import and call in a small
temporary package; the imported result passed afterward. The owned fixture was
archived and removed. These checks validate host operations, not the project CLI
bridge, mutating refactor approval semantics or independence from the IDE.

Next, investigate per-tool/skill readiness using existing tool contracts. A new
shared capability manifest or materially different client configuration contract
needs a decision brief before implementation. Continue independent context
integrity and existing-tool validation while that choice is deferred.

Inspect the current fallback compatibility predicate, official-client command
builders, tool registry and relevant tests. Implement the smallest deterministic
readiness slice that explains required-tool and approval incompatibility using
existing contracts. Add focused same-tier and incompatible-feature tests; do not
infer new state formats or automatically probe credentials/models.

Inspect these existing components first:

- `packages/ai_provider/src/ai_provider/repo_coding_assistant.py`;
- `packages/ai_provider/src/ai_provider/external_agents.py`;
- `packages/ai_provider/src/ai_provider/execution_fallback.py`;
- `packages/ai_orchestrator/src/ai_orchestrator/fallback.py`;
- `packages/ai_agent/src/ai_agent/contracts.py` and `mcp_server.py`;
- `tests/test_execution_fallback.py`, `test_alternate_agent_routes.py`,
  `test_external_agents.py` and `test_ai_agent_mcp_server.py`.

Distinguish declared support, installed executable, tool connection, authorization
and actual live availability. Explain unknown status honestly. An auth check is
not proof of remaining allowance. Decide whether a new shared capability contract
is necessary only after inspecting existing contracts; defer a material public
contract change for an explicit decision and continue independent tests/diagnostics.

### Cross-agent acceptance

Synthetic shared-coding continuation is verified for usage exhaustion and overload
through Codex/Copilot command mappings and actual MCP read/edit effects. Full
instructions, objective, preset, quality/tier policy and task identity survive;
run IDs are fresh even without durable sessions. Saved sessions supply updated
hashed receipts on route switches. Interactive continuation requires fresh exact
approval; a denied call leaves the partial edit unchanged. Deadlines refuse later
stages and bound external clients even when they continuously emit output.
This is deterministic evidence, not live client mutation/terminal acceptance.

Synthetic clients must perform a representative inspect/edit/test/review fixture,
exhaust a route after a partial effect, continue using the common tools without
replaying that effect, and produce a resumable handoff. Incompatible routes refuse
before execution with the missing capability or policy named.

After the process/session design is agreed, add equivalent synthetic coverage for
an in-flight operation and handle recovery. Start with bounded operations rather
than introducing a general service or queue.

Later short live checks verify actual client tool discovery, permission behavior,
an explicitly invoked skill and forced-exhaustion continuation. Naturally burning
through an account allowance is not required. Record client versions, tested
capabilities and limitations. Model-quality comparisons are a separate evaluation.

## Open design decisions

The investigated options and recommendations are in
[foundation decisions](foundation-decisions.md). All six recommendations are now
accepted in ADR-041; historical pending labels above are superseded. They must not
be presented to the owner for approval again. Current status follows below.

### 2026-10-04 implementation checkpoint

Overload and usage fallback now share the configurable ADR-042 continuation gate.
Default `preserve_quality` requires the original declared grade; explicit
`task_minimum` permits task-qualified weaker routes. Failed continuation saves a
local handoff without a weaker model call. Remaining balances and actual model
quality are not guaranteed by these deterministic checks. Full current validation:
933 passed, seven live tests skipped; live overload/quality-gate acceptance deferred.

Owner-approved task quality, context/instruction limits, request/validation
timeouts and repair caps are now typed private user defaults. Explicit CLI flags
win; shipped values, instruction overflow refusal and scheduler deadline admission
are preserved. Configurable privacy/approval defaults are implemented with shipped
`local_only`/`interactive`; explicit flags and client restrictions take precedence.

- Common inspection, checked project-local skill selection and complete required
  instructions are implemented. Forced Codex-limit fallback through real Copilot
  preserved those contracts; the production Kiro mapping passed its read fixture.
- Opt-in coding sessions retain objectives, explicit decisions and hashed receipts
  in existing application SQLite storage. Native process tools inspect direct
  children without AI calls; cleanup stops owned children. Restart requires human
  reconciliation of uncertain effects and never restores old approvals or pipes.
- Shared mutation approval across external clients remains incomplete. Versioned
  native coding compatibility and estimated model-input admission are implemented
  offline; exact tool-bearing counts and fresh live acceptance remain deferred.
  Native approval requests now show task, workspace and complete operation;
  no-human requests deny.
- Superseded on 2026-10-05: the endpoint was supplied, the SDK was installed with
  owner approval, and project-wrapper/session-lifecycle acceptance passed.
- The scheduled full-instruction acceptance ended failed at 14:05:08 UTC. The repair
  exceeded its local context budget; the saved report and final handoff survived.
  The scheduler recorded failure and stopped the sequence. No quality improvement
  or successful refinement acceptance is established by the reviewer pass.
- Offline follow-up bounds tool-capable repair/refinement previews instead of
  copying the tool-free review packet, retaining complete original requirements.
  This addresses avoidable input duplication; successful live repair is unverified.
- Historical 2026-10-04 compute/sleep limits applied to that run. Current resource
  authorization belongs to the active owner's instruction, not this roadmap.

The owner subsequently raised allowance overhead and requested sleep after saved
work. [Resource and usage guidance](resource-and-usage.md) records the immediate
avoid-idle-model-polling workflow, observed client usage and prioritized measurement
follow-up. An explicit Windows sleep helper is implemented; it adds no automatic
queue behavior or global power configuration.

- Explicit local IDE endpoint/activation and its access scope.
- Search source configuration: missing Tavily/Brave credentials and the failed
  SearXNG endpoint prevent search acceptance; direct URL fetching already works.
- Optional capabilities and generalizing the research-only scheduler, if needed.

Shared terminal approvals and native foreground recovery are accepted directions,
with implementation/acceptance still outstanding. Additional architecture choices
must be investigated separately; they are not automatically new approval gates.

### Native compatibility/input slice: COMPLETE offline

[Native admission contracts and bounded live checks](native-admission.md) document
the implementation. Automatic native coding retains positive GPT-OSS evidence;
explicit models/routes remain hard constraints. Model manifest, Ollama runtime and
native contract changes invalidate receipts. Every coding turn reserves generation
and framing capacity and includes complete instructions, skills, schemas and history.
Ollama requests pin the admitted runtime context. Overflow refuses before inference
and preserves earlier receipts. Byte-derived counts are explicitly estimated;
verified tool-bearing token counting is still incomplete.

Deterministic invalidation/refusal tests and native loop/fallback regressions passed.
No model inference, live client acceptance, new service or workstation sleep ran.
Final full offline suite: 965 passed, seven live tests skipped; Ruff lint/format and
Pyright clean. Foundation M1/M2
remain in progress; synthetic checks do not complete live acceptance or tool parity.
D1-D3 owner answers remain approved. D1 now includes enum validation, explicit CLI
precedence, effective persisted session privacy and retained read-only inspection.
D2 public operator probes remain deferred while work is offline. D3's
[typed-job contract](acceptance-job-proposal.md) was subsequently accepted and
implemented offline under ADR-043.
Shared external mutation approvals were subsequently implemented offline; bounded
live permission acceptance remains deferred.

### D1 user defaults: COMPLETE offline

Commit `f86aca5` adds typed `privacy`/`approval_policy` defaults retaining shipped
`local_only`/`interactive`. Explicit CLI options win, including abbreviations,
equals syntax and selections equal to shipped defaults. Session storage uses the
effective privacy before execution; incompatible resumes still refuse. Shared
inspection remains read-only and native client restrictions remain effective.
Owner private configuration was not rewritten. Full offline validation: 996 passed,
seven live skipped; Ruff lint/format, Pyright and commit hooks passed. At that
checkpoint D3 design awaited review; subsequent acceptance is recorded below.
No inference, service startup or sleep ran.

### D3 fixed local acceptance jobs: COMPLETE offline

Owner accepted the concrete contract in this session. `ai_provider.acceptance_jobs`
adds strict immutable v1 definitions and separate receipts to existing SQLite,
with conditional claims and explicit sequential time admission. The fixed native
harness allows source-only edits, preserves instructions/protected tests, requires
actual ordered read/edit effects, and uses bounded host arithmetic validation.
Retained Windows Job Objects own runtime/worker/validator trees, including after
root exit; other platforms refuse before runtime launch. Cleanup, interruption
and stale runtime/model/native-contract refusal have deterministic coverage.
Receipts flush during work and survive worker interruption. Planning starts no
processes and creates no fixture. Existing research contracts remain unchanged.

Focused offline tests: 55 passed; Pyright clean. Full suite and repository checks
are recorded in the latest checkpoint above. No model inference, actual acceptance
queue entry, runtime startup, new service, download or sleep was performed.
Dummy owned-process tests and fixed validators do not establish live model quality.
Shared external mutation approvals and scoped receipts are implemented below;
D3 live execution remains deferred until a selected compute window.

### Shared coding approvals: COMPLETE offline

`--shared-tools coding` exposes existing inspection/file/shell tools with the
selected preset. Official-client MCP calls pass the project permission manager;
interactive requests use a controlling terminal independently of MCP transport,
approve one exact operation and deny when unavailable. Fresh run IDs and
foreground PID/birth checks prevent inherited authority after owner exit.
Existing optional coding sessions persist task/run/tool and argument/output digest
receipts, including denied/failed calls. No new store, service or saved grant exists.
Shared inspection remains read-only; per-run Codex/Copilot/Kiro mappings avoid
global bypass flags, and Antigravity stays excluded.

Offline tests verify policies, denial, one-use approvals, owner/restart expiry,
workspace refusal, terminal escaping/isolation, scoped mappings and existing
SQLite receipt reuse.
Focused shared-tool/session/MCP tests: 54 passed; full suite: 1079 passed, seven
live tests skipped. Ruff lint/format and Pyright are clean. Live terminal
propagation and actual client mutations remain unverified under the offline limit.
The CLI foundation remains INCOMPLETE. Next verify synthetic fallback after a
partial shared-tool effect without replay, preserving tool/preset/privacy/deadline
contracts and observed receipts; live acceptance waits for an explicit window.

## Optional capabilities: unselected

Browser/UI testing, notebooks, debugger control, GitHub issues/PR/CI, visual
document analysis, image generation and broader delegation/scheduling remain
outside the selected foundation. Present a concrete need and bounded integration
before adding one. Their research options are preserved in private local plans,
when available; this public roadmap is sufficient to resume the approved work.

## Resource and scheduling constraints

Live acceptance requires an explicitly selected compute window. Do not start
inference, clients for model work, runtimes or sustained local workloads merely
because this roadmap was approved. Prefer offline validation and synthetic clients.

The configured supervised research acceptance passed through the scheduler in
an owner-selected window on 2026-10-04, including verified tokenizer admission,
report receipts and durable final handoff. Its refinement attempts made no report
progress, and search failure remained recorded. This establishes plumbing, not
model-quality improvement or continuous use of the full allocated budget.
Selecting that completed task again was refused before worker execution with
"Only planned tasks are eligible to start"; terminal tasks are not replayed.
Long local model work must wait for an explicitly selected
compute window and a supported queued task. ADR-039 does not authorize inserting
arbitrary coding or acceptance commands into that queue. Record unsupported live
cases as pending work, rather than presenting them as executable queue entries.

## Session handoff and milestone updates

At the 2026-10-04 implementation checkpoint, the full offline suite passed:
857 tests, seven live checks skipped. Ruff and Pyright passed. Separate live checks
described above ran only during the owner-selected compute window. No new runtime
dependencies or user-wide permission settings were introduced. The owned Ollama
runtime was stopped and its listener was verified absent after live work finished.

This file is the tracked milestone source; ADR-040 preserves the decision.
Update milestone status only with implementation and acceptance evidence, naming
any deferred live checks. Keep the ignored `CURRENT_CONTEXT.md` current with the
latest checkpoint, active milestone, imperative next action and completion test.
Private research plans supplement these documents but must not be required to
recover the approved scope in a new session.
