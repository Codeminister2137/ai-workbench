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
contract. D3's bounded live fixture passed. The owner now retains direct URL
fetching; search replacement is deferred and does not block independent work.
Historical checkpoints below retain their original validation counts. The latest
full offline workspace gate is 1,372 passed and 2 skipped; Council: 21 passed.
The final M1 readiness suite has 84 passing tests. Ruff/formatting, Pyright and
`git diff --check` pass. Live-provider cases remain excluded. See
[test workflow](../test-workflow.md).

The goal is to perform inspect/plan/edit/test/review workflows from the project
CLI, invoke the required skills, resume work and recover from allowance exhaustion
with the common tools still available. PyCharm may host tools initially; eventually
it should only be the human editor/viewer. Different model performance is allowed.

## 2026-10-06 closeout consistency — COMPLETE

The repo-assistant CLI now renders one fixed `## **SUMMARY**` envelope across
chat, provider, native-tool, external-agent, and fallback routes. It preserves
agent output separately and bases validation/execution fields on CLI-recorded
evidence rather than model claims. This closes the immediate reporting-contract
priority; it does not change the remaining roadmap scope. Final gate: 1,295
workspace tests passed, 2 skipped; 21 Council tests passed; Ruff, formatting,
Pyright, and `git diff --check` passed.

## 2026-10-05 checkpoint and remaining boundaries

**Earlier slices COMPLETE; CLI foundation INCOMPLETE, with fresh audit below.**

Earlier checkpoint validation: 1106 passed, seven live tests skipped in 142.00 seconds; repository
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
One exact owner-approved shared file write passed through the live terminal
approval handler; the owner's chat confirmation was relayed into the controlling
terminal. This does not prove the owner physically typed there. Live shell approval
and broader client parity remain unverified.
The owner selected the Jedi-based, preview-first Python rename direction on
2026-10-06. The offline implementation is complete: `rename_preview` and
`rename_apply` share the guarded workspace tool contract; `python_navigate`
provides bounded definitions/references through the same optional Jedi extra.
Jedi 0.20.0 is opt-in
under `uv sync --extra rename-preview`. Full offline workspace and Council tests,
Ruff, formatting, Pyright and lock checks pass. Coverage includes preview
immutability, concurrent edits during analysis, cross-file imports/calls,
duplicate local names, Unicode/CRLF, stale and expired plans, complete-diff
approval, one-use handles and partial-write reporting. An actual attended/native/
shared-client apply fixture remains. An isolated temporary-package preview has
passed through both the native registry and foreground HTTP MCP transport using
a synthetic MCP client; the two-file fixture remained unchanged. This is not
installed third-party client or apply-approval acceptance. The owner selected
this direction to advance IDE independence while permitting PyCharm as a
temporary tool host; see [ADR-045](../decisions/ADR-045-ide-independent-semantic-rename.md).
Interactive denial also passed through the foreground HTTP MCP transport: the
approval callback received the complete diff, denied the write, and the fixture
remained unchanged. After the owner approved the exact displayed two-file
`Widget` -> `Gadget` diff, apply passed through the foreground HTTP MCP transport
under the interactive permission policy; the exact diff/digest was checked,
both file effects were verified, and the disposable fixture was cleaned up.
This is bounded synthetic-client shared-transport acceptance, not evidence of
physical terminal input, installed third-party-client parity, or full C5/M5
completion.
Antigravity remains excluded. This is bounded acceptance, not full tool parity.
Component selection and suite timing are documented in [test workflow](../test-workflow.md).
The workspace check also runs the previously omitted Council suite separately.

The fresh wider-plan audit found eligible unfinished work beyond those earlier
slices: common public fetching, deadline/session/shutdown races, streamed provider
tools and trailing usage, malformed-response normalization, saved usage diagnostics,
complete report paging and hard-latency validation. These are implemented and
verified; the earlier blanket blocker conclusion was insufficient.

A bounded actual Copilot fixture called the common public fetch tool once and
returned its HTTP 200 receipt and matching body digest. It used only a public
Python documentation URL in a synthetic workspace, took 13.7 seconds and reported
one premium request. The foreground listener closed. This verifies one client,
not all-client research parity or authenticated-source access.

All six private DOCX plans and five Markdown plans were reviewed again against
code and accepted decisions. Remaining concrete boundaries and recommended next
work are recorded in [the fresh audit](post-audit-decisions.md). This does not mark
the wider project complete or turn old unchecked plan items into new approval.

### Standalone Python runtime diagnostics (C3)

The native and shared coding profiles now expose a read-only `python_runtime`
tool. It reports the interpreter executing the project agent plus declared
`requires-python`, lockfile presence and a conventional workspace `.venv`
candidate. It does not switch interpreters, execute workspace code, or claim
that separately launched commands use the reported environment. This is an
initial IDE-independent diagnostic. The default orchestrated pytest validation
invokes the same Python executable running the repo-assistant process instead of
resolving `python` through PATH; its result records that executable. The
accepted ADR-046 adds `--validation-python` to explicitly select a different
interpreter for that default command. Explicit custom validation commands remain
caller-selected and unchanged. On Windows, quoted command arguments are
unwrapped without losing backslashes. The default remains pytest only;
Ruff/Pyright are available through explicit commands or pre-commit, without
expanding default validation policy.

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
| M1 | Readiness and adapter contracts | **Complete offline**; fallback diagnostics distinguish adapter compatibility/executable presence and report effective skill, tool-profile, approval, and option requirements. Live client/account parity is deferred. | Deterministic route/tool/skill/approval checks explain eligibility and exclusions; forced-limit coverage preserves tier and task constraints |
| M2 | Common tools and portable skills | Offline discovery/prerequisite reporting is implemented; Copilot and Kiro passed live selected-skill inspection; Antigravity's default headless MCP permission was verified denied; Codex check is deferred until its reported reset | C1-C4 work through common contracts on selected routes; explicit skills resolve dependencies; required instructions are available or omissions cause a clear refusal |
| M3 | Semantic tooling with temporary IDE host | Read-only IDE bridge, optional Jedi preview/apply, and read-only Python definitions/references implemented; bounded native/shared MCP rename acceptance passed with a synthetic client | Selected C5 operations pass native/shared live acceptance with defined semantics and permissions; installed-client coverage is still required where applicable |
| M4 | Coding and process continuity | In progress; live Copilot and Kiro fallback each continued shared edits and polled the same in-flight process handle | Agreed session/process model preserves objective, decisions, scoped approvals, receipts and handles across turns and fallback; uncertain effects are reconciled |
| M5 | Independence from the IDE tool host | Pending | Approved C1-C6 workflows remain usable with PyCharm tool hosting unavailable; PyCharm can serve only as editor/viewer |

Each milestone has deterministic correctness checks and separately recorded live
acceptance where necessary. A milestone cannot be reported fully accepted on
synthetic evidence alone when it requires an installed client or IDE bridge.
Deferred live checks must not prevent independent offline implementation.

### M1: offline acceptance — COMPLETE

First slice implemented on 2026-10-04: `--fallback-readiness` reports static
policy and executor exclusions without authentication/tool/provider probes;
execution preflight retains precise incompatibility reasons. Same-tier and
different-bucket policy tests now cover every cost ceiling. Full offline suite:
828 passed, seven live tests skipped; Pyright clean. Fresh synthetic-exhaustion
acceptance continued a partial edit through real Copilot and passed its fixture.
These results do not prove canonical tool/skill parity or alternate approval modes.

2026-10-06 diagnostic follow-up: the offline report now exposes
`executable_status` (`available`, `unavailable`, or `not_applicable`) separately
from adapter compatibility. This checks local command presence only; it never
starts a client or probes credentials, tool connection, or allowance. Tests
cover a compatible adapter with a missing executable and a present local
executable. Full offline suite: 1,296 passed, 2 skipped; Council: 21 passed;
Ruff and Pyright clean.

The static compatibility matrix now covers both shared-tool profiles across
Codex, Copilot, Kiro, and Antigravity, with all four approval presets for the
coding profile. It verifies that the effective profile/policy reaches the
existing adapter configuration and that unsupported Antigravity shared-tool
mapping is reported rather than treated as eligible. It uses mocked executable
discovery and does not start clients or probe accounts. Installed-client
permission parity remains separate acceptance. Full offline gate after the
matrix: 1,320 passed, 2 skipped; Council: 21 passed; Ruff, formatting, Pyright,
and `git diff --check` passed.

Offline readiness now applies normal shared-tool normalization before reporting:
an explicit skill implies shared inspection and `read_only`, selected skill
sources and existing tool prerequisites are checked, and missing skills produce
a blocked result. The report includes effective shared profile, approval
policy, and validated selected skill names. Regression coverage also verifies
that an unsupported Codex-specific search option is reported as incompatible
for alternate shared-tool routes rather than hidden behind general adapter
support. The option compatibility tests now cover every declared Codex-specific
CLI option for Codex and alternate Copilot/Kiro routes, both with and without
shared coding tools. Existing constraints are preserved, and mutually exclusive
native-tool/session flags are rejected consistently by offline readiness.

The M1 deterministic completion criteria are now met. Existing fallback tests
cover same-tier and cost-ceiling constraints, privacy and tool-capability
filtering, quality-preserving defaults and explicit task-minimum downgrades,
forced quota continuation, exhaustion bounds, incompatible-route refusal, and
preservation of task instructions. Readiness tests cover effective skill,
shared-tool, approval and CLI-option compatibility, including unsupported
routes. Final validation: readiness suite 84 passed; full workspace 1,372
passed and 2 skipped; Council 21 passed; Ruff/formatting, Pyright and
`git diff --check` passed. This completes M1 offline only. Authentication,
remaining allowance, installed-client permissions and live route parity remain
unverified and require a separately selected acceptance window.

Implemented context slices include nested repository instructions for selected
paths and visible context truncation/omission diagnostics. Under ADR-041, complete
applicable instructions use a separate configurable budget and overflow refuses
before execution rather than truncating instructions. A model-free
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
read-only skill acceptance; automatic installation and provider-native skill
activation remain incomplete. `--list-skills` now discovers known supported
project-local sources and reports their common-tool/Git prerequisites without
starting a client, provider, installer or granting new permissions. Unknown
skills are not advertised without a prerequisite contract.
Offline regression coverage also confirms that selected skills refuse a missing
Git executable and that the complete selected skill instructions survive
usage-limit fallback continuation.

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

The per-tool/skill readiness audit is complete using existing contracts; no new
capability manifest or public client contract was needed. Authentication, tool
connection, authorization and live availability remain distinct from static
readiness and are not inferred by the offline report.

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

### 2026-10-06 bounded live acceptance

All requests used disposable synthetic fixtures; no private repository source was
sent to the clients. No web/search calls or natural account exhaustion were used.

| Client | Live check | Result |
| --- | --- | --- |
| GitHub Copilot CLI 1.0.90 | Simulated initial Codex quota failure; shared coding continuation and foreground process continuity | Passed. Two completed edits used distinct run IDs, the existing child was polled by handle and cleaned up, the source passed the host validator, and protected fixture files stayed unchanged. Artifact: `artifacts/fallback-acceptance-20261006-124322`. |
| Kiro CLI 2.24.0 | Same forced-fallback/shared-process fixture | Passed with the same checks. Artifact: `artifacts/fallback-acceptance-20261006-124344`. |
| GitHub Copilot CLI 1.0.90 | Explicit `review-repo-change` skill with shared inspection/read-only permissions | Passed on a synthetic defect: the client used shared inspection tools and reported the changed operator and failing test contract; no edits or web calls. Artifact log: `artifacts/skill-live-copilot-20261006-124538.log`. |
| Kiro CLI 2.24.0 | Same explicit skill and inspection fixture | Passed with the same finding; no edits or web calls. Artifact log: `artifacts/skill-live-kiro-20261006-124617.log`. |
| Google Antigravity CLI 1.2.16 | Workspace-local `repo_shared` MCP config; one `read_file` request under default headless permissions with `--sandbox` and no bypass flag | Server/tool was discovered, but `mcp(repo_shared/read_file)` was denied before execution; no marker was returned and the fixture was unchanged. CLI stderr says headless mode auto-denies MCP permissions and requires an allow rule in `settings.json`. Fixture: `artifacts/antigravity-permission-probe-20261006-125851`. |
| Google Antigravity CLI 1.2.16 | Candidate workspace permission files: root `settings.json` and `.agents/settings.json`, each with only `mcp(repo_shared/read_file)` allowed | Neither location affected the CLI permission decision; both read calls were denied. These files existed only in disposable fixtures. Fixtures: `artifacts/antigravity-project-settings-settings.json-20261006-130912` and `artifacts/antigravity-project-settings-.agents-settings.json-20261006-130912`. |
| Google Antigravity CLI 1.2.16 | Native `write_to_file` request in a disposable fixture, with `--sandbox` and no bypass flag | Denied in headless mode because `write_file` had no allow rule; sentinel remained unchanged. Fixture: `artifacts/antigravity-native-write-probe-20261006-130539`. |
| Google Antigravity CLI 1.2.16 | Harmless native `run_command` (`Write-Output sandbox_probe_only`) with `--sandbox` and no bypass flag | Denied in headless mode because `command` had no allow rule; no marker was produced. This verifies that the tested sandbox invocation did not authorize shell execution. Fixture: `artifacts/antigravity-sandbox-command-probe-20261006-130539`. |
| GitHub Copilot CLI 1.0.90 | Shared coding profile under `read_only`; attempted one `edit_file` call | Denied by the MCP permission manager with “no scoped approval”; the sentinel stayed unchanged and the session recorded the failed edit receipt. Fixture/receipt: `artifacts/permission-live-20261006-124835`. |
| GitHub Copilot CLI 1.0.90 | Shared coding profile under `read_only`; attempted harmless `run_command` output | Denied before command execution with “no scoped approval”; no command output was produced. Fixture/log: `artifacts/shell-permission-live-20261006-124910` and `artifacts/shell-permission-live-copilot-20261006-124919.log`. |
| PyCharm-bundled Codex CLI, route `openai-codex-gpt-5-5` / model `gpt-5.5` | Explicit skill/read-only inspection on the same synthetic review fixture | Deferred until the provider-reported reset on 2026-10-10 at 08:35 (timezone unspecified). The earlier attempt was blocked before any tool call by a usage-limit response; zero tool and file-change events. It was not retried. |

Each completed Copilot invocation reported one premium request. Kiro emitted
per-run credit metering, but no account balance or allowance was queried. The
Codex service’s limit response is not treated as a live capability result. Its
next check is deferred until the provider-reported reset above; do not retry
early or switch routes to evade the limit. Antigravity server discovery is
verified, but its headless request-review mode denies MCP calls without a
matching grant. Official CLI documentation supports workspace-local MCP server
definitions in `.agents/mcp_config.json`; the live denial directs operators to
a `permissions.allow` rule in `settings.json`, while official settings docs
describe permissions as global or project-level settings. The project-only
grant scope was approved, but Antigravity CLI 1.2.16 exposes no project-permission
command or documented project-local permission file. Tests of root
`settings.json` and `.agents/settings.json` in disposable workspaces did not
grant access; the documented CLI settings file is user-level. No narrow per-run
grant override is documented or was tested. `agy mcp list` reported no global
server registrations, and no user/global or project permission/config files were
changed. Do not use
`--dangerously-skip-permissions`: it auto-approves all tool requests and is not
an acceptable substitute for scoped MCP grants. Two further sandboxed native
tool probes were denied as well: a `write_to_file` attempt did not alter its
sentinel, and a harmless `run_command` did not produce its marker. The tested
`--sandbox` invocation therefore did not authorize these native actions; a
project-scoped MCP read grant can be assessed separately while leaving native
file writes and commands without allow rules.
The earlier exact file-creation acceptance used a chat-relayed confirmation;
this run did not claim physical terminal approval, interactive shell approval,
or complete all-client parity. These execution checks do not evaluate model
quality.

Artifacts remain under ignored `artifacts/` for local inspection. The
read-only review fixture retains its intentionally planted diff and the
Codex-generated fallback handoff; no project source was changed by live runs.
The owner approved project-scoped allow rules for only the read-only inspection
tools; no native `write_file` or `command` grants are needed. Applying the
approved scope is blocked in this environment: only the headless CLI is
installed/available, and it provides no documented project-permission setup
path. Configure the exact MCP tool grants from Antigravity's project settings UI
when available, then rerun the live probe. Do not replace this with a user-wide
grant. Antigravity remains excluded until the exact project grants are active
and verified.

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

2026-10-06 follow-up: the planned synthetic fallback-after-partial-effect check
is complete. `tests/test_shared_coding_fallback.py` covers quota/overload failure,
`workspace_write`/`interactive`, and persisted/non-persisted sessions. It verifies
the original edit is retained, continuation uses the same task and deadline with
a fresh run ID, tool access is preserved, interactive approvals renew, protected
files/instructions survive, and effects are not replayed. Combined focused
fallback/refinement tests: 70 passed.

The same follow-up investigated the 2026-10-04 research no-progress acceptance.
The saved trace shows both refinement turns returned zero tool calls and no final
text despite actionable review findings. A successful-empty refinement with no
report/evidence fingerprint change is now classified as an execution failure
immediately; it no longer consumes another no-progress cycle. Explicit
non-empty explanations for leaving a report unchanged retain the existing
two-consecutive-no-progress policy. Regression coverage is in
`tests/test_research_refinement.py`. Further model-quality evaluation still
requires a newly selected compute window.

The CLI foundation remains INCOMPLETE. Remaining live checks require the
owner's attended terminal approval, an available Antigravity project-settings
UI to apply already-approved read-only MCP grants, and the Codex route's
provider-reported reset before retry. The latest focused independent-tools,
fallback and refinement regression batch passed: 93 passed, 1 skipped; Ruff,
formatting, Pyright and `git diff --check` passed.

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
