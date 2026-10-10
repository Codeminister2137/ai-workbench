# Continuous coding chat: implementation proposal

2026-10-09. Owner accepted the distinct continuous coding-chat interface and
existing-storage direction; [ADR-049](../decisions/ADR-049-continuous-coding-chat.md)
records the decision. Initial controller/terminal integration is implemented
offline; full migration quality/cost acceptance remains INCOMPLETE. Alternatives
below preserve the reviewed proposal.

The next foreground slice accepts queued in-flight corrections with immediate
local transcript persistence, fresh approval prompt IDs and one joined terminal
reader. Multiple queued messages use the latest request with earlier owner text
retained in history. Restart does not automatically execute saved input. Running
effects are not preempted by queued text; Ctrl+C retains reconciliation semantics.
The owner subsequently accepted deterministic local long-history reduction:
retain all owner messages/host outcomes, shorten older assistant reports visibly,
keep originals retrievable and refuse mandatory-context overflow. This now runs
without summary inference or schema changes, including after restart.
Deterministic history/input evidence is not model-quality or cost evidence.

## Required outcome

The owner can conduct ongoing development conversations in the project CLI:
ask questions, clarify requirements, approve a plan, request implementation,
steer work, inspect results and continue without reconstructing the task.
Development results must be comparable to or better than the current assistant
on representative conversations. Delegation should lower cost while preserving
quality. Separate command invocations alone do not meet the migration requirement.

## Current evidence and gap

- `ai_agent.repo_coding_assistant._run_chat_mode` handles one persisted provider
  turn; it calls `client.complete`, excludes official-client routes and does not
  invoke the coding tool loop. Argument validation prohibits coding actions and
  orchestration in this mode.
- `main` binds an optional `CodingSession` and foreground tool supervisor for
  one invocation, then closes it. Handoffs preserve objectives, explicit decisions
  and effect receipts, rather than a complete development conversation.
- Chat transcripts, coding receipts, context assembly, routing/fallback, native
  tools, shared MCP tools and scoped approvals already exist. Reuse them rather
  than introducing a daemon, new database or agent framework.
- Offline correctness and selected live fixtures are substantial, but do not
  establish continuous conversational quality or lower cost.

Relevant private plans: `docs/plans/repo-assistant-cli-parity-plan.md` and
`docs/plans/cli-development-readiness-review.md`. Their historical checkpoints
are superseded by current code and ADR-040/041/044/048. Wider application plans
are unrelated to this implementation slice.

## Material choice: public interactive workflow

| Option | Benefit | Cost / compatibility consequence |
| --- | --- | --- |
| Add a distinct continuous coding-chat entry point | Preserves existing provider-only `--mode chat` behavior; exposes coding authority and lifecycle explicitly; reuses provider-native and official-client execution behind one foreground controller | Adds a public mode/entry point and requires explicit linkage between conversation history and coding-session recovery |
| Extend existing `--mode chat` to opt into coding and official-client execution | One chat interface for discussion and coding; existing transcript concepts are directly visible | Changes an established mode contract and its invalid-argument rules; must carefully preserve read-only defaults and older scripts; still needs the same coding-session integration |

Recommendation: a distinct continuous coding-chat entry point in `ai_agent`,
implemented with a standard terminal interface and reusable foreground controller.
Keep the existing chat command compatible. Retain official clients for their
supported allowance access and provider-native execution as another route, in
line with ADR-040. A full terminal UI dependency is unnecessary for the first
contract. Exact naming follows owner selection of the interface direction.

Proposed session contract: reuse existing local SQLite chat transcript and coding
session records, with explicit linkage using existing metadata where sufficient;
persist user turns, final responses, explicit decisions and existing hashed
effect receipts. Do not broaden receipt persistence to credentials, private
reasoning or full raw tool arguments/outputs. Preserve privacy/cost boundaries
on resume, inherit primary privacy for delegated tasks, and renew operation
approvals. Investigate any necessary schema change before implementing it.

The owner selected the recommended distinct interface and existing-storage
contract. Do not reopen that choice. Live accounts/model windows and any later
material schema/security change remain separately scoped decisions.

## Implementation sequence after selection

1. Define controller/session contracts and deterministic fake-route fixtures.
   Preserve applicable instructions and conversational context across turns.
   Model clarifications and explicit owner decisions as conversation content.
2. Add a foreground terminal loop over the reusable controller. Keep terminal
   input and approval handling separate from provider/MCP protocol streams.
   Define EOF, cancellation and safe exit; do not preserve stale grants.
3. Integrate existing native and official-client coding execution, validation,
   scoped shared tools and fallback. Preserve one conversation across turns,
   refreshing source context and recording actual tool effects.
4. Verify restart recovery and uncertain effects. Keep interrupted receipts
   explicit; do not replay mutations or attach to arbitrary saved PIDs.
5. Audit C1-C6 on each eligible route: repository/Git, skills/instructions,
   interpreter/tests/diagnostics, documentation research, semantic navigation
   and safe refactoring, process/session continuity. Missing required capabilities
   must refuse or identify an eligible route before work. Keep PyCharm as an
   optional temporary host while the accepted independence work continues.
6. Run bounded installed-client acceptance and representative quality comparison
   within an owner-selected model/account/compute and data-transmission scope.
   Fix observed failures; publish a tested launch/resume guide afterward.

Offline tests must cover follow-up corrections, clarification then implementation,
fresh file context, lost/oversized context, interrupted turns, denied commands,
failed validation, restart reconciliation, fallback after partial effects,
session isolation and expired approval scopes. Controller tests use actual
temporary files/processes where effects matter; external model behavior is mocked.

## Quality and economics acceptance

Use approximately 20-50 representative development tasks/conversations, including
realistic bug fixes, test design/edge cases, refactoring and security-sensitive
review. Include the owner's existing conversation style, not just single-turn
synthetic edits. Agree concrete tasks and acceptable regression criteria before
claiming parity; a test pass count alone cannot establish model quality.
The [20-case comparison set](coding-chat-quality-cases.md) is prepared as a
reviewable starting point. The owner accepted strict per-required-case baseline
assessment; representative execution remains pending. ADR-050 records the
accepted economic metrics, 20% external savings target with case-by-case review
below target, and automatic integration direction.

Compare current-assistant baseline, CLI without delegation, and CLI with bounded
delegation where available. Match primary model/configuration/context as closely
as possible and report differences. Evaluate requirement adherence, correct
effects, regression/security coverage, evidence-based reviews, instruction and
decision retention, and permission compliance. Human review supplements executable
checks; no parity claim is justified by one successful fixture.

Record elapsed time and total primary/delegated token use, including failures
and retries. External economic comparisons use API spend or subscription
allowance consumption as applicable; local comparisons record total tokens and
use elapsed time as the practical resource measurement. Consider time without a
hard median-completion-time rejection gate. Extra delegation requests or
larger summaries can outweigh savings. Do not equate fewer tokens with lower
subscription charges or promise savings without measurements. Primary agents
retain architecture/implementation responsibility; delegated output remains
bounded support evidence and never approval authority.

New connectors, services, global grants and automatic external writes remain
outside this proposal. Browser/debugger/notebook or other quality tools should
be selected when representative development tasks establish the need; do not
silently expand the approved C1-C6 foundation into every available integration.
