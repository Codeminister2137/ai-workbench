# CLI foundation: decisions awaiting the owner

**INCOMPLETE — investigated proposals, not accepted architecture.**

Prepared during the owner-selected 2026-10-04 implementation and acceptance window.
[ADR-040](../decisions/ADR-040-shared-agent-tools-and-cli-development-foundation.md)
already approves shared tools, C1-C6 and a temporary PyCharm tool host. The choices
below concern implementation; they do not reopen that direction. The
[roadmap](development-roadmap.md) records verified progress and acceptance limits.

## 1. Shared requirements and client configuration

Decision needed: how a task selects common tools and skills, and how adapters
carry that selection to a replacement client.

- A: Built-in project profiles backed by existing `ToolDefinition`/`ToolRegistry`,
  with per-run client mappings and explicitly selected skill sources. Smallest
  implementation; adding profiles initially requires a code change.
- B: A user-editable, versioned capability manifest and configuration format.
  More flexible, but adds validation, migrations and a second source of truth.

Recommendation: A first. Keep orchestration requirements neutral; execution
adapters own native names, MCP configuration and permission mapping. Readiness
must distinguish declared support, installation, authentication, connection,
authorization and actual execution. Reject incompatible fallback before execution.
Skill instructions never grant tools or approvals. Decide discovery/distribution
and dependency validation as part of this slice; the example skill is not yet a
runtime registry. Do not silently install into user-wide directories.

Owner selection pending: A or B, and whether this is the next implementation slice.

## 2. Required repository instructions and budgets

Decision needed: what to do when complete applicable `AGENTS.md` instructions do
not fit. Current 5,000-character total / 2,500-per-file limits can truncate them;
new diagnostics expose this, but do not guarantee instruction integrity.

- A: Reserve a separate budget for complete applicable instructions, ahead of
  ordinary file context; refuse execution if the effective model input still
  cannot accommodate them. Better usability, larger inputs and changed defaults.
- B: Keep current limits and refuse execution when required instructions are
  incomplete; require an explicit larger budget. Smaller compatibility change
  to budgeting, but current repositories with long instructions may routinely stop.

Recommendation: A, with a clear refusal when complete instructions cannot fit.
Do not promise that a character budget alone proves tokenizer/model capacity.
Selected source snippets and optional context can still be shortened visibly.
This changes execution behavior and context economics, so it needs owner approval.

Owner selection pending: A or B and the acceptable default instruction allowance.

## 3. Shared approvals and Antigravity eligibility

Decision needed: how the shared server receives scoped approvals, and whether an
official client without equivalent headless permissions is eligible for a task.

- A: Start with shared inspection under narrow read/search grants. Keep mutation
  routes excluded until a project approval channel is implemented and verified.
- B: Implement that approval channel now, including write/shell request delivery,
  scope, denial, expiry and behavior when the human is unavailable. Larger slice;
  necessary before claiming interactive coding parity across all clients.

Recommendation: A followed by B as a separate milestone slice. Preserve native
client restrictions as an additional boundary; MCP annotations are descriptive.
Do not map interactive approvals to broad automatic client flags.

Antigravity's installed headless client denied MCP access without an answer while
returning process exit zero. The adapter now reports failure. Its
[headless documentation](https://www.antigravity.google/docs/cli/headless/) describes
scoped grants in global settings; a supported narrow per-run override has not been
established. Choose either explicitly approved native grants for the selected
inspection server/tools, or temporary exclusion from shared-tool fallback.
Changing global settings may affect other sessions; broad bypass is not proposed.
A separate tool-free request returned the expected answer through existing sign-in;
the MCP refusal is distinct from basic client execution availability.

Owner selection pending: approval-channel sequencing and Antigravity grant/exclusion.

## 4. Temporary IDE bridge

Decision needed: connect official clients directly to PyCharm MCP, or expose
project-owned tool wrappers that forward approved operations to it.

- A: Direct native-client connections. Fastest early integration, but names,
  permissions and responses remain host-specific; provider-native execution needs
  a separate MCP client path and eventual replacement affects callers.
- B: Project-owned wrappers over an explicitly configured local PyCharm MCP
  endpoint. More adapter work, but preserves common contracts across clients and
  permits replacing the host later.

Recommendation: B, beginning with read-only interpreter, diagnostics and semantic
navigation. Use the IDE's supported transport rather than a new custom IDE plugin.
[PyCharm documents MCP transports and external-client setup](https://www.jetbrains.com/help/pycharm/mcp-server.html).
Direct host checks here passed; an external project CLI connection is still unverified.
Endpoint configuration, MCP client dependency and mutating refactor review semantics
must be selected before implementation. Do not enable IDE brave mode automatically.

Owner selection pending: A or B; approve a bounded transport/dependency proposal
once endpoint discovery is verified. Rename preview cannot be assumed from a tool
that only performs the mutation.

## 5. Coding-session and process continuity

Decision needed: what survives a client switch and a project CLI restart, and who
owns long-running processes and their approvals.

- A: An explicit handoff with in-memory continuity while the foreground CLI lives.
  Smallest scope; restarting loses live handles and requires effect reconciliation.
- B: A foreground project-owned supervisor plus durable session/process metadata
  in the existing application SQLite database. Supports recovery evidence and
  shared ownership, but needs an additive schema and explicit retention/approval
  rules. Metadata cannot restore dead pipes or prove an uncertain write happened.
- C: A persistent background service. More availability, installation, lifecycle
  and security work; no demonstrated need to start there.

Recommendation: B without a daemon. Preserve objective, decisions, scoped approvals
and observed receipts locally; never private model reasoning or credentials.
Do not blindly replay uncertain effects. Scope fresh approvals to the same task,
workspace and operation; document which approvals expire on restart. Choose the
exact persistence and host-lifetime contracts before coding, and keep existing
research scheduling separate from coding-process control.

Owner selection pending: A or B and restart/retention expectations. C is deferred.

## 6. Native model compatibility

Decision needed: whether verified native tool behavior should gate coding routes.
In paired synthetic probes GPT-OSS returned actual calls; Qwen2.5-Coder returned
textual requests on all 20 tasks under both prompts. These are bounded compatibility
results, not a general model-quality ranking. Catalog routing remains unchanged.

- A: Prefer a verified native-tool model for coding, with explicit diagnostics for
  unverified/incompatible choices. Changes selection/readiness policy.
- B: Keep selection unchanged and investigate Qwen/Ollama compatibility separately.
  Preserves defaults, but known textual requests cannot execute as native tools.

Recommendation: A while investigating B. Never convert arbitrary response text
into executable tool calls to make an incompatible model appear functional.
Define how verified support expires across model/runtime updates before treating
it as permanent catalog truth. Larger representative quality evaluation remains
separate; the current scheduler supports supervised research, not arbitrary evals.

Owner selection pending: A or B and whether changing the default native coding
route is wanted. No natural account-exhaustion test is required.

## Work order after selections

### Concrete package proposed to the owner on 2026-10-04

These are recommendations awaiting selection, not additional accepted decisions.

- Profiles: choose 1A; discover skills from explicit project-local directories,
  validate declared prerequisites, and pass selected instructions and equivalent
  tools to each eligible route. No automatic global installation.
- Instructions: choose 2A with a configurable 64,000-character instruction limit,
  separate from optional snippets. The root AGENTS.md currently contains 31,724
  characters. Never truncate required instructions; refuse when the instruction
  limit or a known model input limit cannot accommodate them. Character counts
  alone must not be described as proof of model token capacity.
- Permissions: inspection first, then a terminal approval channel for shared
  writes/commands using existing permission presets. Requests identify the task,
  workspace and operation. Interactive requests do not proceed without a human;
  other authorized work may continue. Approvals expire on CLI restart. Keep
  Antigravity out of tool-requiring fallback until scoped permissions are verified;
  leave its global settings unchanged.
- IDE bridge: choose 4B and approve the official Python MCP SDK as an optional
  bridge dependency, with a pinned compatible release selected after checking the
  configured Python SDK and the actual local IDE transport. Begin with interpreter,
  diagnostics and navigation; mutations stay behind the shared approval contract.
  Keep all endpoint configuration explicit and local.
- Continuity: choose 5B, a foreground supervisor and additive records in the
  existing application SQLite storage. Save objectives, explicit decisions and
  observed process/tool results, not credentials or private model reasoning.
  Retain records until explicit user deletion. Restart invalidates mutation
  approvals and requires reconciliation of uncertain effects; no blind replay.
  No persistent daemon or promise to restore dead process pipes.
- Local coding: choose 6A for automatic routing, initially using the verified
  GPT-OSS route. Explicit model choices remain explicit; incompatible native tool
  choices receive a refusal with an explanation, not a silent substitution. Record
  model/runtime versions; invalidate compatibility evidence after relevant updates.
  Investigate Qwen separately without treating the synthetic probes as a quality
  ranking.

Proposed five-hour priorities: CLI common profiles/instructions/fallback, followed
by IDE/approvals/continuity as dependencies permit; a second track investigates
research search failures and no-progress refinement, then runs bounded acceptance
through the existing research scheduler. Summarize available usage receipts without
new account polling or storage. The current scheduler does not accept arbitrary
coding/evaluation jobs; generalizing it remains a separate decision. Council,
job-search and optional browser/notebook/debugger integrations remain later goals.
Do useful authorized work until completed, blocked or the window ends; do not
occupy the deadline with idle model calls. Save changes, validation and the handoff
before invoking the owner-authorized sleep helper.

Implement shared inspection requirements/client mappings and complete-instruction
handling first; verify the same fixture through forced allowance fallback. Then
add the read-only IDE bridge, shared mutation approvals and selected session/process
model. Finish with inspect/edit/test/review plus interruption and uncertain-effect
recovery. Keep optional browser, notebook, debugger, account integrations, visuals
and broader delegation outside this foundation until a concrete need is approved.

Completion requires reviewed changes, deterministic contract checks and bounded
live receipts. A successful scheduler worker or authenticated client is not proof
of model quality, remaining allowance or complete common-tool parity.
