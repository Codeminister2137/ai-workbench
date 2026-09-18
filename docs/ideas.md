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
