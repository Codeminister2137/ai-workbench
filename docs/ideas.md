# Ideas

This file parks useful future ideas that should not be loaded into the active
implementation path until they become scheduled work. Items here are not accepted
architecture decisions or current requirements.

## Email ingestion and newsletter digests

Owner-requested, low priority (2026-10-28): let Workbench read selected mail,
including provider onboarding messages, and digest newsletters for useful facts,
links and opportunities across the connected applications.

- Investigate a read-only mail connection and explicit message/label selection;
  the current assistant's Gmail connection does not automatically grant Workbench
  an OAuth token or permission to read an entire mailbox.
- Preserve message/link provenance, dates and uncertainty; distinguish private
  correspondence from public articles reached through newsletter links.
- Treat email and linked pages as untrusted input, not instructions to execute
  commands, reveal credentials or expand access. Do not echo keys or signed links.
- Decide local processing, permitted external processors, retention/deletion and
  cross-application sharing before implementation. Sending mail is separate scope.

This records the idea only; no mailbox worker, schedule or persistence is approved.

## Account balances, allowance windows and reset visibility

Owner-requested, low priority but important for long-term usability (2026-10-28):
show provider credit balances, subscription usage, reset times and overage state
in the app, and make the same observations available to `ai_orchestrator`.

- Reuse `ai_provider` account/source readers and neutral observations rather than
  separate dashboard and routing scrapers. Go already exposes account-wide usage
  percentages/reset times; other supported native readers cover additional sources.
- Report source, checked time, account/route scope and stale/unknown status.
  Percentages, token usage, provider balances and estimated cost are different facts.
- Preserve explicit unknowns where a provider offers no supported billing API;
  investigate documented read-only access first and allow labelled manual reports
  when needed. A visible balance is not proof that overage is disabled.
- Keep credentials and private account figures out of public source and worker
  prompts. The Orchestrator may consume evidence under existing admission policy;
  a dashboard display must not silently relax billing/privacy restrictions.

Detailed UI, refresh cadence and storage choices remain future decisions. This
idea does not authorize a background monitor or a new persistence/service layer.

## Reduce redundant agent calls and context work

Owner-requested backlog (2026-10-19): investigate avoidable model/allowance cost
from repeated reassessment, redundant actions, context rereads and tool calls.
This is a future investigation, not authorization for new inference or telemetry.

- Use existing safe receipts to distinguish productive work from checkpoint,
  repeated-read, duplicate-command and unnecessary evaluation overhead.
- Compare calls, input/output tokens, elapsed time and observed spend or allowance
  where available; distinguish cached/billed usage and keep unknown values unknown.
- Prefer lightweight checkpoints inside existing turns and reuse current evidence;
  investigate batching and removal of redundant work before adding automation.
- Verify that any reduction preserves quality, complete required instructions,
  meaningful validation, effect reconciliation, approval boundaries, time
  reassessment, cleanup and default sleep. Do not save calls by dropping safeguards.

Schedule a bounded review when this work is selected. Do not introduce a new
logging service, persistent metrics format, paid comparison or raw-prompt/private-
reasoning capture merely to measure the issue.

## Personal AI Assistant / Local Context

Potential future app or module:

- local personal context store for habits, preferences, current state, writing
  and coding style, skills, goals, and job-search profile;
- explicit and implicit learning from user interactions;
- mentor role that helps with tasks and suggests growth areas;
- possible integration with Job Search Automation for skills, CV evidence, and
  role targeting;
- possible integration with AI Council for reflective review and multi-model
  advice.

Hard constraints to decide before implementation:

- personal data stays local by default;
- private data, derived profiles, embeddings, logs, and memories must not be
  committed;
- any cloud use needs explicit privacy classification and approval;
- storage format, data ownership, deletion/export, and review/edit controls need
  a separate decision;
- the public repository may contain the reusable app/framework, but not the
  owner's private data.

Open product questions:

- Is this a separate `apps/personal_ai_assistant` app, part of AI Council, or a
  reusable personal-context package plus app?
- What should be learned automatically versus explicitly confirmed by the user?
- How should stale or wrong memories be corrected?
- Should mentor suggestions be scheduled, event-driven, or only requested?
- What data, if any, may be shared with Job Search Automation or external AI
  providers?

## Provider / Orchestrator Dashboard

Potential future user-facing app:

- prompt editor backed by `ai_provider` and `ai_orchestrator`;
- general chat surface intended to replace a meaningful share of day-to-day
  ChatGPT usage, including research, shopping decisions, workout planning, and
  project planning;
- provider/model selector with local, Requesty, and OpenAI-backed options;
- refinement controls next to the text prompt instead of hidden inside prose;
- single-choice or multi-choice controls for privacy class, desired quality,
  maximum acceptable runtime, cost sensitivity, autonomy level, and whether
  prompt refinement requires approval;
- transparency panel showing selected provider/model, routing reasons, numeric
  latency/cost estimates, context-window usage, and any omitted or summarized
  context;
- model evaluation surfaces for latency, coding correctness, general assistant
  quality, cost, and failure-rate comparisons;
- background task visibility for long-running local evaluations, model
  comparisons, and AI Council discussions;
- future integration point for other apps such as AI Council and job-search
  automation.

Hard constraints to decide before implementation:

- dashboard must not become the owner of provider APIs or orchestration policy;
- cloud execution needs explicit privacy/config controls;
- prompt rewriting should start as review plus suggested changes requiring user
  approval;
- local transcript ownership should remain provider-neutral so model switching
  can replay retained context into the selected backend.
- persistence, personal memory, search/web integrations, background scheduling,
  and autonomous external actions each need a separate decision before they are
  implemented.
- model replacement claims should be evidence-based. Compare local/cloud models
  against the current Codex and ChatGPT workflows with representative coding,
  research, planning, and general-chat tasks before treating a model as a
  preferred default.

Open product questions:

- Should this be a standalone app, CLI-first with a later dashboard, or both?
- Which refinement controls deserve first-class UI widgets versus text prompt
  instructions?
- How should long-running autonomous coding tasks expose progress, approval
  stops, and cancellation?
- What telemetry should be stored locally for personalization, and what should
  remain ephemeral?
- How should quality benchmarks combine established coding suites, project-local
  tasks, and subjective general-assistant evaluations?
- What model-quality threshold is good enough to replace ChatGPT/Codex for a
  given task class, and when should the dashboard deliberately route to hosted
  models instead of local ones?
