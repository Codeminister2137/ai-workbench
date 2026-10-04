# CLI Development Foundation Roadmap

[CLI guide](../repo-coding-assistant.md) ·
[Accepted scope: ADR-040](../decisions/ADR-040-shared-agent-tools-and-cli-development-foundation.md)

## Status and outcome

**INCOMPLETE — approved roadmap, implementation milestones pending.**
Decision and milestone recording is complete as of 2026-10-04. Existing tools and
fallback are foundations; they do not constitute completed cross-agent parity.

The goal is to perform inspect/plan/edit/test/review workflows from the project
CLI, invoke the required skills, resume work and recover from allowance exhaustion
with the common tools still available. PyCharm may host tools initially; eventually
it should only be the human editor/viewer. Different model performance is allowed.

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
| M2 | Common tools and portable skills | In progress; context diagnostics and read/search MCP profile verified | C1-C4 work through common contracts on selected routes; explicit skills resolve dependencies; required instructions are available or omissions cause a clear refusal |
| M3 | Semantic tooling with temporary IDE host | Pending | Selected C5 operations work through a verified PyCharm bridge with defined semantics and permissions |
| M4 | Coding and process continuity | Pending; design choices open | Agreed session/process model preserves objective, decisions, scoped approvals, receipts and handles across turns and fallback; uncertain effects are reconciled |
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

The next independent slices include nested repository instructions for selected
paths and visible context truncation/omission diagnostics. Existing budgets still
apply; enforcing complete required instructions remains a decision. A model-free
`--read-search-only` MCP profile exposes repository inspection tools. A
bounded real Copilot acceptance discovered and called `find_files`, `list_dir`
and `read_file` with explicit read/search grants, returned the fixture marker and
left the fixture unchanged. This confirms one client connection, not write/shell,
skill activation, all-client parity or fallback with common MCP configuration.

Native coding and the opt-in inspection MCP profile now share bounded local Git
status/diff tools under READ permissions; the default Codex delegation profile
is unchanged. Focused fixtures verify index preservation, staged/unstaged diffs,
literal paths, outside-root refusal and disabled external diff helpers.

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

- Minimal project-owned coding-session state and native-session interaction.
- Process ownership, handle lifetime and recovery after client or host shutdown.
- Any persistence/schema change required by those designs.
- Shared-tool approval channel and equivalent native-client restrictions.
- Concrete independent semantic tooling, dependencies and runtime integrations.

These are unresolved implementations within an approved direction. Do not ask
again whether shared tools or a temporary IDE host are wanted. Investigate each
decision when its milestone requires it, recommend options and defer only that
part until the owner chooses.

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
Long local model work must wait for an explicitly selected
compute window and a supported queued task. ADR-039 does not authorize inserting
arbitrary coding or acceptance commands into that queue. Record unsupported live
cases as pending work, rather than presenting them as executable queue entries.

## Session handoff and milestone updates

This file is the tracked milestone source; ADR-040 preserves the decision.
Update milestone status only with implementation and acceptance evidence, naming
any deferred live checks. Keep the ignored `CURRENT_CONTEXT.md` current with the
latest checkpoint, active milestone, imperative next action and completion test.
Private research plans supplement these documents but must not be required to
recover the approved scope in a new session.
