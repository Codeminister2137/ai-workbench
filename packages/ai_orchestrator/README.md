# ai-orchestrator

Transparent orchestration primitives above `ai_provider`.

Current scope:

- deterministic prompt judge heuristics;
- task profile and prompt issue data models;
- transparent model/backend recommendation over a caller-provided catalog.

Current non-goals:

- provider adapters;
- autonomous agents;
- learned routing;
- quota/billing platform;
- mandatory orchestration for every AI call.

The orchestrator should call `ai_provider` for execution once a backend/model is selected. It must not implement provider APIs directly.
