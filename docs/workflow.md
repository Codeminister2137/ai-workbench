# Development Workflow

## 1. Before starting
Use tiered context reading instead of rereading every document by default.

If the user asks to use, check, or run a named `Codex: ...` prompt, read
`docs/prompt-library.md` as the canonical prompt library and usage guide.

For most work:
1. Check cheap state: `git status --short`, current branch when relevant, and
   targeted file discovery/search.
2. Read local `CURRENT_CONTEXT.md` when present.
3. Read the relevant sections of root/nested `AGENTS.md` files and canonical docs.
4. Read only the ADRs and project plans that affect the current task.
5. Inspect current code, tests, and configuration in the affected area.

Do a fuller documentation sweep when the task changes architecture, privacy,
dependencies, persistence, public APIs, data contracts, or provider/application
boundaries; when docs and code conflict; when resuming after context loss; or
when a durable decision may be needed.

When reporting an investigation or implementation plan, identify the `docs/plans/` files used as planning input. If a plan is not used because it is unrelated, obsolete, or superseded, say so briefly.

## 2. Investigation pass
Do not modify files. Report:
- current state/behavior;
- relevant files/modules;
- proposed implementation;
- meaningful alternatives;
- risks;
- tests/validation needed;
- assumptions;
- questions requiring the user's decision.

For autonomous taskful work, this investigation is an internal phase unless the
user explicitly asks for an investigation report first. Do not emit a progress
message after every search, edit, or test. Keep updates silent between material
phase changes, long-running waits, or genuine blockers/decision boundaries, and
provide one concise completion report after the requested scope is verified.

## 3. Decision gate
**Stop and ask the user** when a material decision is required. Examples include choosing between materially different API behavior, introducing a database/service/dependency, changing an architecture boundary, changing privacy routing, or resolving contradictory requirements.

If the existing documentation already defines the decision, follow it without asking again.

Do not implement an option merely because it is easier.

## 4. Implementation pass
After scope is clear:
1. Implement only the approved scope.
2. Reuse existing abstractions where appropriate.
3. Avoid unrelated refactoring.
4. Add/update tests.
5. Run relevant validation.
6. Inspect the diff.
7. Update canonical docs if behavior/architecture changed.

## 5. Validation
Use the checks actually configured by the project, commonly:
```text
pytest
ruff check .
ruff format --check .
pyright
```
Do not claim a check was run if it was not.

## 6. AI evaluation workflow
For prompt/model/orchestration changes:
1. Define the task.
2. Select representative examples.
3. Establish a baseline.
4. Run the changed version.
5. Compare relevant quality measures.
6. Track latency/cost/failure rate where useful.
7. Inspect failures manually.
8. Avoid conclusions from one example.

## 7. Documentation
Update docs when public behavior/configuration changes, architecture changes, or a durable decision is made. Avoid duplicating the same requirement across multiple documents.

When a decision changes: supersede the old ADR, add the new ADR, then update architecture/project plans as necessary.

Update local `CURRENT_CONTEXT.md` at the end of non-trivial work when present so the next session has the latest completed work, conflicts/risks, validation status, and next plan.

## 8. Git
For substantial work use a focused branch/commit series. Before completion inspect:
```text
git diff
git status
```
Check for unrelated edits, secrets, generated files, accidental config changes, and incomplete migrations. Never reset/delete user work without approval.

## 9. Session boundaries
Use `Codex: Session Boundary Check` between work sessions, after a commit, before
switching to a distinct task, or after compaction/context errors.

Run `.\scripts\session-boundary.ps1` for a cheap repository-side signal before
switching chats or when compaction symptoms appear. It checks Git state and
`CURRENT_CONTEXT.md` freshness, but it cannot inspect private PyCharm chat
context, so ask the user for `/status` when context pressure or rate limits
matter.

Prefer a new chat when the current milestone is committed, `CURRENT_CONTEXT.md`
is current, and the next task can resume from repository files more cheaply than
from the accumulated transcript. Continue the current chat when work is
mid-change, unresolved decisions exist only in the transcript, or debugging and
validation context is still active.

In the Codex IDE chat, `/status` can show context usage and rate-limit state.
Use it as an input when context pressure matters; do not invent a fixed
cross-surface threshold.

## 10. Discoveries
If implementation reveals a materially better architectural idea, do not silently implement it. Explain the discovery and ask whether to change direction. Small internal improvements with no meaningful architectural consequence may be implemented normally.

## 11. Standard task prompt
```text
Task:
[what I want changed]

Context:
[why]

Constraints:
[important constraints]

Please first investigate the repository and report your proposed implementation.
Do not modify files until the investigation is complete and any material decisions have been resolved.

If the task requires a product, architecture, dependency, privacy, data-model, or scope decision that is not already defined, ask me before implementing it.

After approval, implement only the agreed scope, run the relevant tests/checks, inspect the diff, and report the result.
```
