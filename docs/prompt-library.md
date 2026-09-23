# Prompt Library

This is the canonical repository prompt library for Codex workflows. Its
workflow guidance is repository-controlled and may be used by other coding
assistants, but it cannot override the active assistant runtime's tool,
commentary, or completion rules.

The prompts were migrated from the custom PyCharm AI Assistant prompt library on
2026-09-20. This Markdown file is the source of truth for this repository. The
PyCharm prompt library may need manual sync when this file changes.

`docs/pycharm-ai-prompt-library.md` was the earlier local summary and should be
treated as superseded by this file.

## How Codex Should Use This File

When the user asks to run or check the prompt library, read this file as the
actual prompt library.

If a prompt references `$SELECTION`, treat it as the user-selected code/text in
PyCharm. In this Codex chat, use the user's request, current conversation, and
relevant repository context as the equivalent selection unless the user provides
specific selected text.

When asking Codex to use a prompt, name it directly:

```text
Use Codex: Investigate First for this request.
```

For autonomous taskful execution, named prompts are not a requirement to emit
an update after each sub-step. Keep investigation and implementation internal
unless the user asks for an interim report; communicate only at material phase
changes, long-running waits, blockers, or the final verified closeout.

## PyCharm Sync

The PyCharm Prompt Library is separate IDE state. To use the same prompts there:

1. Open PyCharm AI Assistant prompt/library settings.
2. Create or update a prompt with the same `Codex: ...` name.
3. Copy the corresponding prompt body from this file.
4. Keep `$SELECTION` where the prompt expects selected code or text.

Use `Codex: PyCharm Prompt Sync` to compare this canonical file with the
IDE-side prompt library before manually syncing changes.

## Suggested Prompt Flow

For larger tasks:

1. `Codex: Context Primer`
2. `Codex: Investigate First`
3. `Codex: Decision Brief`, if a material decision appears
4. `Codex: Implement After Decision`
5. `Codex: Test Plan`, if test coverage is unclear
6. `Codex: DoD Closeout`

For transition points after commits, before a new slice, or after resuming:

1. `Codex: Prompt Library Check`
2. Follow the smallest useful prompt sequence it recommends.

For mid-day session boundaries:

1. `Codex: Session Boundary Check`
2. Continue the current chat, or update `CURRENT_CONTEXT.md` and start a new
   chat, based on the recommendation.

For PyCharm/Codex IDE compaction-risk checks:

1. Run `.\scripts\session-boundary.ps1` for the repository-side signal.
2. If the script asks for IDE status, run `/status` in the PyCharm Codex chat
   and share the context/rate-limit signal.
3. Use `Codex: Session Boundary Check` before switching chats so
   `CURRENT_CONTEXT.md` is current.

For end-of-day or stopping-point closeout:

1. `Codex: DoD Closeout`
2. Let it run the reusable closeout helpers it needs:
   `Codex: Prompt Library Check`, `Codex: Capture Current Context`,
   `Codex: ADR Gap Check`, `Codex: PyCharm Prompt Sync`, and git/validation
   checks.
3. Commit only when the closeout finds a coherent, validated change set ready
   for history.

The goal is that the user can say "DoD closeout" instead of separately asking
for commits, context handoff, prompt-library review, ADR review, and final
validation every time.

For architecture-heavy work:

- `Codex: ADR Gap Check` checks for missing or stale ADR coverage.
- `Codex: ADR Capture` records an approved durable decision.

For scope control:

- `Codex: MVP/Stop Review` checks whether the current plan is becoming too broad
  or speculative.

## Prompt Index

- `Codex: Weekly Review`
- `Codex: DoD Closeout`
- `Codex: Closeout Helper Set`
- `Codex: Session Boundary Check`
- `Codex: MVP/Stop Review`
- `Codex: Job Search Task`
- `Codex: AI Council Task`
- `Codex: Orchestrator Evaluation`
- `Codex: Orchestrator Task`
- `Codex: Provider Layer Task`
- `Codex: Privacy/Security Review`
- `Codex: Project Placement`
- `Codex: ADR Capture`
- `Codex: ADR Gap Check`
- `Codex: Decision Brief`
- `Codex: Resume From Context`
- `Codex: Context Primer`
- `Codex: Capture Current Context`
- `Codex: Update Docs`
- `Codex: Refactor Safely`
- `Codex: Test Plan`
- `Codex: Code Review`
- `Codex: Implement After Decision`
- `Codex: Investigate First`
- `Codex: Prompt Library Check`
- `Codex: PyCharm Prompt Sync`

## `Codex: Weekly Review`

```text
Task:
Run a short planning review across the active projects.

Context:
$SELECTION

Instructions:
- Use the master checklist and CURRENT_CONTEXT.md.
- Answer: what finished, what evidence changed the plan, which project has the highest immediate payoff, what can be removed from scope, what is the smallest next action, and what should be handed to Codex next.
- Keep the provider -> orchestrator -> Council/job-search milestone order in mind.
- Do not turn this into implementation unless I ask.

Output:
Give a concise review, recommended next task prompt, and any decision boundary that should be resolved before coding.
```

## `Codex: DoD Closeout`

```text
Task:
Close out this completed work against the repository definition of done and
prepare a clean stopping point.

Context:
$SELECTION

Instructions:
- Treat `Codex: Closeout Helper Set` as reusable helper guidance for this
  prompt. Run the relevant helper checks instead of waiting for the user to ask
  for them one by one.
- Check requested behavior, unchanged existing behavior, edge cases, error
  handling, tests, Ruff, formatting, pyright, secrets, scope, docs, ADRs,
  CURRENT_CONTEXT.md, git diff, and git status.
- Read `docs/prompt-library.md` and identify whether any closeout-specific
  prompt should be run before stopping. Use the smallest useful set; do not
  run broad workflows just because they exist.
- Update `CURRENT_CONTEXT.md` when the work was non-trivial or the next session
  would otherwise lose important state.
- Check whether a missing or stale ADR is likely. Do not create or edit an ADR
  unless the user has approved that decision or the ADR is already part of the
  agreed scope.
- Check whether prompt-library changes need PyCharm manual sync notes. Do not
  modify PyCharm settings unless the user explicitly approves it.
- If the current diff is coherent and validated, recommend the commit grouping
  and commit message. If the user already asked you to commit, create the
  focused commit after validation.
- Do not create commits for unrelated or partially validated work.
- Do not claim checks were run unless they were actually run.
- Separate validation performed from validation not run.
- Identify known limitations and residual risks.

Output:
Provide a concise completion report: what changed, why, validation run,
docs/decision updates, prompt-library/helper checks used, context handoff
status, git status/diff summary, recommended commit action, and remaining risks
or follow-ups.
```

## `Codex: Closeout Helper Set`

```text
Task:
Apply the reusable helper checks that support `Codex: DoD Closeout`.

Context:
$SELECTION

Instructions:
- Use this as a helper prompt, not as a standalone replacement for
  `Codex: DoD Closeout`.
- Prompt-library helper: read `docs/prompt-library.md`, identify only prompts
  that are genuinely useful for the current stopping point, and explain why.
- Context helper: update `CURRENT_CONTEXT.md` when work was non-trivial,
  decisions changed, validation status matters, or the next action would be
  unclear after context loss.
- ADR helper: check for missing, stale, or contradicted ADR coverage only when
  the work touched architecture, provider boundaries, privacy, dependencies,
  persistence, public APIs, data contracts, or durable workflow decisions.
- Docs helper: verify that changed public behavior, configuration,
  architecture, or workflow guidance is reflected in the canonical docs without
  duplicating requirements unnecessarily.
- Git helper: inspect `git diff` and `git status`, identify unrelated changes,
  generated files, secrets risk, incomplete migrations, and sensible commit
  grouping.
- Validation helper: report checks actually run and checks intentionally not
  run; never imply a clean validation state from intent alone.
- PyCharm sync helper: when `docs/prompt-library.md` changes, report that the
  IDE-side prompt library may need manual sync. Use `Codex: PyCharm Prompt Sync`
  only when the user asks for a sync check or when sync status materially
  matters.
- Keep the helper set small for the situation. Skip helpers that do not apply.

Output:
List the helper checks used, helper checks skipped, why they were skipped, and
any action that should happen before stopping or committing.
```

## `Codex: Session Boundary Check`

```text
Task:
Decide whether to continue the current Codex chat/session or move to a new one.

Context:
$SELECTION

Instructions:
- Keep this check cheap. Do not run a broad repository review just to answer it.
- Inspect `git status --short` and `CURRENT_CONTEXT.md`.
- Identify whether the current work is mid-task, at a committed milestone, at an
  uncommitted but coherent stopping point, or about to switch to a distinct task.
- If context pressure matters, ask the user to run `/status` in the Codex IDE
  chat and share the context-usage signal. Do not guess an exact threshold.
- If available, run `.\scripts\session-boundary.ps1` first and use its output as
  repository-side evidence. The script cannot inspect PyCharm's private chat
  state, so `/status` remains the source for IDE context/rate-limit signals.
- Recommend starting a new chat when a milestone is committed, when
  `CURRENT_CONTEXT.md` is current and the next task is distinct, after
  compaction-related errors or context confusion, or when `/status` shows high
  context usage.
- Recommend staying in the current chat when implementation is mid-change,
  unresolved decisions exist only in the transcript, validation/debugging context
  is still active, `CURRENT_CONTEXT.md` is stale, or the next action is a tiny
  follow-up.
- Balance token cost and diminishing returns against quality. Prefer continuing
  when the active conversation contains reasoning or debugging state that would
  be expensive or risky to reconstruct. Do not recommend a new chat solely to
  reduce tokens when that would reduce quality.
- Treat PyCharm/Codex IDE compaction failures as environment-specific empirical
  signals. Do not assume the same threshold applies to every Codex surface.
- If moving to a new chat is recommended, first ensure `CURRENT_CONTEXT.md`
  contains the last completed work, validation status, open decisions/risks,
  current git state, and the next recommended action.
- Whenever a new chat is recommended, or the user requests one, provide a
  copy-paste-ready `New chat prompt` in the response. It must include the
  repository, branch, latest checkpoint, next task/action, required files,
  task-specific constraints, and first verification step. General quality and
  communication principles are standing repository guidance and should not be
  repeated in every prompt. Keep the same prompt at the bottom of
  `CURRENT_CONTEXT.md` when that handoff is used.
- The handoff must prominently classify the task or roadmap as `COMPLETE`,
  `INCOMPLETE`, or `BLOCKED`. For `INCOMPLETE`, include an imperative next
  action and a concrete completion condition. Do not treat a descriptive
  roadmap summary as permission to stop without implementing the next action.

Output:
Say either `continue current chat`, `update handoff then start new chat`, or
`do not switch yet`. Explain the reason briefly and list any handoff update
needed before switching. Classify the reason as `context-pressure`,
`logical-checkpoint`, or `quality-preserving continuation`. If starting a new
chat, include the exact `New chat prompt` after the decision.
```

## `Codex: MVP/Stop Review`

```text
Task:
Review this plan or implementation for scope control and stop conditions.

Context:
$SELECTION

Instructions:
- Prefer a small finished vertical slice over speculative infrastructure.
- Check whether a real consumer and measurable reason justify any new abstraction, service, dependency, storage, or automation.
- Identify if more than two projects are actively gaining features and suggest reducing context switching.
- Call out cases where the Orchestrator/Council/automation adds cost or latency without measurable value.
- Preserve direct/bypass paths when overhead is not justified.

Output:
List keep, defer, remove, decision-needed, and next-smallest-action items. Include the concrete acceptance gate for the next slice.
```

## `Codex: Job Search Task`

```text
Task:
Work on job-search automation.

Context:
$SELECTION

Instructions:
- Use docs/plans/03_Job_Search_Automation_Project_Plan.docx.
- Optimize for relevant applications with less repetitive effort, not blind volume.
- Candidate profile is the source of truth; every factual claim must trace to evidence.
- Never invent or upgrade experience, employment, projects, certifications, metrics, responsibilities, or tools.
- Keep human approval before sending applications or taking consequential external actions.
- Start with one reliable/permitted source before broad ingestion.
- Use the Orchestrator for prompt/model selection where useful; do not embed provider logic here.

Output:
Propose the smallest workflow slice, evidence/fabrication checks, approval boundary, data model/tests, and privacy risks. Ask before storage, schema, scraping, sending, or external-service decisions.
```

## `Codex: AI Council Task`

```text
Task:
Work on the AI Council application.

Context:
$SELECTION

Instructions:
- Use docs/plans/02_AI_Council_Project_Plan.docx and keep Council responsibilities separate from Orchestrator/provider responsibilities.
- Council owns multi-perspective workflow, response collection, disagreement handling, synthesis, presentation, and export.
- Preserve raw answers, provenance, uncertainty, minority claims, and visible local/cloud/hybrid routing.
- Do not put provider adapters, model routing policy, prompt judging/refinement, or quota-aware routing inside the Council.
- Start with the smallest useful CLI or minimal interface before product UI.

Output:
Propose the smallest Council change, boundary checks, tests for provenance/partial failure/minority visibility, and evaluation criteria for whether Council adds value over a single model.
```

## `Codex: Orchestrator Evaluation`

```text
Task:
Design or review an evaluation harness for prompt refinement, model recommendation, or routing.

Context:
$SELECTION

Instructions:
- Compare at least: original prompt with fixed default, refined prompt with fixed default, and orchestrator-selected execution where applicable.
- Use a small representative real-task set before scaling up.
- Track usefulness/success, latency, usage/cost, failure rate, backend/provider/model, and regressions.
- Include cases where refinement or orchestration should be skipped.
- Do not let one model generate, judge, and certify its own success without safeguards.

Output:
Provide evaluation design, dataset shape, metrics, baseline, regression cases, and what result would justify keeping or changing the orchestrator feature.
```

## `Codex: Orchestrator Task`

```text
Task:
Work on the AI Orchestrator.

Context:
$SELECTION

Instructions:
- Use docs/plans/05_AI_Orchestrator_Project_Plan.docx and the provider/orchestrator boundary in docs/architecture.md.
- The Orchestrator owns prompt judging/refinement, task profiles, model recommendation, request configuration, routing, fallbacks, privacy constraints, quota/economics awareness, and usage integration.
- It must not implement provider adapters or become the Council.
- Preserve original prompts. Refinement must not silently change user intent or invent facts.
- Privacy classification happens before any external judge/refiner/router call.
- Keep bypass/manual override paths.

Output:
Propose the smallest vertical slice, evaluation/test set, deterministic tests, and the routing/reasoning transparency needed. Ask before autonomous optimization, learned routing, persistent storage, or cloud privacy changes.
```

## `Codex: Provider Layer Task`

```text
Task:
Work on the provider-agnostic AI infrastructure.

Context:
$SELECTION

Instructions:
- Use docs/plans/01_AI_Provider_Agnostic_Infrastructure_Plan.docx, docs/architecture.md, and ADR-014/ADR-015 as planning context.
- The provider layer owns common contracts, adapters, provider identity, errors, usage metadata, timeouts, and local/cloud visibility.
- It does not own prompt judging, model selection policy, Council synthesis, job-search logic, or autonomous agents.
- Keep the interface small and capability-gated. Preserve useful raw provider metadata.
- Do not add cloud adapters, dependencies, or unsupported provider capabilities unless approved.

Output:
Give the smallest implementation plan, boundary checks, tests, and validation commands. Ask before any material dependency, cloud, privacy, or public-contract change.
```

## `Codex: Privacy/Security Review`

```text
Task:
Review this planned change for privacy, security, secrets, and external data flow risks.

Context:
$SELECTION

Instructions:
- Identify whether data leaves the local environment and which provider/service receives it.
- Check local-only, external-allowed, sensitive-review-required, or public/low-risk implications.
- Look for hard-coded secrets, prompt/content logging, credential handling, and unsafe defaults.
- For job-search materials, ensure no fabricated experience or qualifications are introduced.
- Stop at any unresolved privacy or external-processing decision.

Output:
List risks, required mitigations, decision boundaries, tests/regressions to add, and a clear go/no-go recommendation.
```

## `Codex: Project Placement`

```text
Task:
Decide where this code or feature belongs in the repository.

Context:
$SELECTION

Instructions:
- Use docs/project-map.md and the architecture dependency direction: apps -> ai_orchestrator -> ai_provider -> backends.
- Keep provider-specific logic in provider adapters.
- Keep orchestration policy out of applications and provider adapters.
- Keep app-specific workflows inside apps unless shared stable behavior is genuinely needed.
- Ask if placement is materially ambiguous.

Output:
Recommend the target package/app/module, explain why, list rejected placements, and identify tests/docs that should move with the change.
```

## `Codex: ADR Capture`

```text
Task:
Record or prepare an architecture decision.

Context:
$SELECTION

Instructions:
- Use docs/decisions.md as the lightweight index and docs/decisions/ for detailed ADRs only when the decision is durable and material.
- Preserve previous decisions; mark superseded decisions instead of rewriting history.
- Do not invent my rationale. Ask for it if it is not clear from the conversation.
- Link related ADRs, plans, and architecture sections.

Output:
Say whether an ADR is warranted. If yes, draft the decision-index entry and detailed ADR content, including context, options, decision, rationale source, consequences, and related docs.
```

## `Codex: ADR Gap Check`

```text
Task:
Check whether we are missing any important Architecture Decision Record for the current implementation, or whether any existing ADR has drifted from the code.

Context:
$SELECTION

Required workflow:
1. Read CURRENT_CONTEXT.md if present.
2. Read AGENTS.md.
3. Read docs/architecture.md, docs/decisions.md, docs/decisions/, docs/project-map.md, and docs/workflow.md.
4. Inspect the relevant current code, tests, configuration, package metadata, and README files.
5. Identify material decisions already embodied in the implementation that are not covered by an ADR.
6. Identify existing ADRs that appear outdated, contradicted, or too vague for the current implementation.
7. Separate true ADR-worthy gaps from ordinary implementation details.
8. Do not create or edit ADRs unless I explicitly approve that follow-up.

Report:
- missing ADR candidates, ordered by importance;
- existing ADRs that may need updates or superseding;
- implementation details that do not need ADRs;
- your technical recommendation for what to record next and why.
```

## `Codex: Decision Brief`

```text
Task:
Identify and explain the decision boundary for this request.

Context:
$SELECTION

Instructions:
- Investigate repository docs, decisions, plans, code, tests, and git history where relevant before asking.
- Distinguish implementation details from product, architecture, dependency, privacy, API, persistence, or scope decisions.
- Do not choose a material direction on my behalf.
- Give a technical recommendation only after explaining alternatives and consequences.

Output:
Use this structure: Decision needed, Why it matters, Options, Trade-offs, Technical recommendation, User question, and whether an ADR should be created after the decision.
```

## `Codex: Resume From Context`

```text
Task:
Resume work from CURRENT_CONTEXT.md and proceed toward the next provider/orchestrator step.

Context:
$SELECTION

Instructions:
- First read CURRENT_CONTEXT.md, AGENTS.md, docs/architecture.md, docs/decisions.md, docs/workflow.md, docs/project-map.md, docs/definition-of-done.md, relevant ADRs, and relevant docs/plans files.
- Verify the handoff against current code, tests, config, and git status before trusting it.
- Identify whether the next step belongs in ai_provider or ai_orchestrator and confirm the boundary.
- If the next action is clear and no material decision is required, implement it with focused tests and validation.
- If a material decision appears, stop and provide a decision brief.
- Avoid redoing broad investigation unless the handoff is stale or contradictory.

Output:
Briefly state the verified current state, the next action, any decision boundary, then either implement the clear next step or ask for the needed decision.
```

## `Codex: Context Primer`

```text
Task:
Prepare for a non-trivial task in this repository.

Context:
$SELECTION

Instructions:
- Read CURRENT_CONTEXT.md if present, AGENTS.md, docs/architecture.md, docs/decisions.md, docs/workflow.md, docs/project-map.md, docs/definition-of-done.md, relevant ADRs, and relevant docs/plans files.
- Identify which plan files are relevant and which are skipped as unrelated or superseded.
- Inspect the current code and tests before assuming documentation is current.
- Do not modify files.

Output:
Summarize active constraints, relevant plans, likely files/modules, open risks, and the smallest useful next investigation step.
```

## `Codex: Capture Current Context`

```text
Task:
Update CURRENT_CONTEXT.md so a future Codex session can resume immediately.

Context:
$SELECTION

Instructions:
- Inspect the current repository state, relevant docs/plans, recent work, validation status, git status, and open risks.
- Keep CURRENT_CONTEXT.md compact and action-oriented; it is an ignored local handoff, not an ADR or history log.
- Preserve only information needed to restart work quickly: last completed work, validation baseline, active boundaries, open risks, and next recommended action.
- Remove stale or duplicated details when they no longer help resumption.
- Do not claim validation or changes that were not verified.

Output:
Update CURRENT_CONTEXT.md, then report what changed, what was verified, and what the next session should do first.
```

## `Codex: Update Docs`

```text
Task:
Update or draft documentation for this behavior/change.

Context:
$SELECTION

Instructions:
- Avoid duplicating requirements across docs.
- Use docs/decisions.md and docs/decisions/ only for durable architecture decisions.
- Do not invent user rationale for ADRs; ask for rationale when needed.
- Keep project plans as context and requirements, not literal code specifications.
- Prefer concise, maintainable documentation tied to current code.

Output:
Identify which docs should change, provide the proposed wording or patch plan, and call out any decision that needs user confirmation.
```

## `Codex: Refactor Safely`

```text
Task:
Refactor the selected code safely without changing behavior unless explicitly requested.

Context:
$SELECTION

Instructions:
- First identify the behavior that must remain unchanged.
- Keep the refactor local and reversible.
- Reuse existing project patterns.
- Do not change public APIs, config formats, persistence formats, privacy behavior, or architecture boundaries without asking.
- Preserve tests or add characterization tests where risk is non-trivial.
- Avoid speculative abstractions.

Output:
Explain the smallest safe refactor, risks, and validation needed. Ask before implementation if a material decision appears.
```

## `Codex: Test Plan`

```text
Task:
Design the tests for this change or component.

Context:
$SELECTION

Instructions:
- Separate deterministic software tests from provider/API integration tests and AI-quality evaluations.
- Prefer focused unit tests for deterministic logic and contract tests for shared interfaces.
- Avoid live provider calls unless explicitly requested or already gated by configuration.
- For AI behavior changes, suggest a small representative evaluation set and comparison criteria.
- Respect existing test style and project validation commands.

Output:
Provide the recommended test cases, fixtures/mocks, validation commands, and any edge cases that should be covered.
```

## `Codex: Code Review`

```text
Task:
Review this code/change for bugs and regressions.

Context:
$SELECTION

Instructions:
- Use a code-review stance, not a rewrite stance.
- Prioritize correctness bugs, security/privacy risks, behavioral regressions, missing tests, and architecture-boundary violations.
- Check whether AGENTS.md, docs/architecture.md, docs/decisions.md, and relevant plans create constraints for this change.
- Do not focus on style unless it can cause concrete maintenance or behavior problems.
- Do not modify files unless I explicitly ask for fixes.

Output:
List findings first, ordered by severity, with file/line references when possible. Then list open questions and test gaps. If no issues are found, say so clearly.
```

## `Codex: Implement After Decision`

```text
Task:
Implement the agreed change.

Context:
Use the selected code and prior discussion as context:
$SELECTION

Instructions:
- Follow AGENTS.md and existing project architecture.
- Keep the change scoped to the agreed behavior.
- Reuse existing abstractions and conventions.
- Do not introduce new dependencies, storage, services, external calls, or public API changes unless already approved.
- Add or update focused tests for meaningful behavior changes.
- Run the relevant validation checks.
- Inspect git diff and git status before reporting.
- Update docs or CURRENT_CONTEXT.md where project rules require it.

Output:
Summarize what changed, why, validation run, and any remaining risks.
```

## `Codex: Investigate First`

```text
Task:
Investigate this request before proposing implementation.

Context:
Use the selected code as the starting point:
$SELECTION

Instructions:
- Inspect relevant repository files, tests, configuration, and documentation before making assumptions.
- Respect AGENTS.md and local project rules.
- Identify current behavior, relevant components, risks, and tests.
- If there is a product, architecture, dependency, privacy, data-model, API, or scope decision, stop at the decision boundary and ask me.
- Do not modify files yet.

Output:
Give a concise investigation report, proposed implementation, validation plan, and any decisions I need to make.
```

## `Codex: Prompt Library Check`

This prompt is canonical in the repository but has not yet been synced into the
PyCharm prompt library.

```text
Task:
Review the repository prompt library and decide whether any existing Codex prompt should be run before continuing work.

Context:
$SELECTION

Required workflow:
1. Read docs/prompt-library.md as the canonical prompt library.
2. Check current git status and recent context.
3. Identify whether the current situation matches any available prompt.
4. Recommend any prompt or prompt sequence that is genuinely useful now, or say that no prompt is needed.
5. Explain briefly why each recommended prompt is useful and what order to run them in.
6. Prefer the smallest useful sequence. Do not suggest prompts just because they are available.
7. Do not run a broader workflow unless it is clearly useful for the next step.

Use this especially after commits, before starting a new logical work slice, after resuming context, or before architecture/significant implementation work.
```

## `Codex: PyCharm Prompt Sync`

This prompt is canonical in the repository but has not yet been synced into the
PyCharm prompt library.

```text
Task:
Check whether the repository prompt library and PyCharm AI Assistant prompt library are in sync.

Context:
$SELECTION

Required workflow:
1. Read docs/prompt-library.md as the canonical prompt library.
2. If PyCharm prompt-library storage is available and access is approved, inspect the IDE-side prompt entries.
3. Compare prompt names and prompt bodies.
4. Identify prompts missing from PyCharm, prompts missing from the repository, and prompts whose text differs.
5. Do not modify PyCharm settings unless I explicitly approve that follow-up.

Output:
Report sync status, differences, recommended source of truth for each difference, and exact manual sync steps.
```
