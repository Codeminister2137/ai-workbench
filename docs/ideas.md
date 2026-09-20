# Ideas

This file parks useful future ideas that should not be loaded into the active
implementation path until they become scheduled work. Items here are not accepted
architecture decisions or current requirements.

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
- provider/model selector with local, Requesty, and OpenAI-backed options;
- refinement controls next to the text prompt instead of hidden inside prose;
- single-choice or multi-choice controls for privacy class, desired quality,
  maximum acceptable runtime, cost sensitivity, autonomy level, and whether
  prompt refinement requires approval;
- transparency panel showing selected provider/model, routing reasons, numeric
  latency/cost estimates, context-window usage, and any omitted or summarized
  context;
- future integration point for other apps such as AI Council and job-search
  automation.

Hard constraints to decide before implementation:

- dashboard must not become the owner of provider APIs or orchestration policy;
- cloud execution needs explicit privacy/config controls;
- prompt rewriting should start as review plus suggested changes requiring user
  approval;
- local transcript ownership should remain provider-neutral so model switching
  can replay retained context into the selected backend.

Open product questions:

- Should this be a standalone app, CLI-first with a later dashboard, or both?
- Which refinement controls deserve first-class UI widgets versus text prompt
  instructions?
- How should long-running autonomous coding tasks expose progress, approval
  stops, and cancellation?
- What telemetry should be stored locally for personalization, and what should
  remain ephemeral?
