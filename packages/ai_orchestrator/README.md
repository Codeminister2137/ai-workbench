# ai-orchestrator

Transparent orchestration primitives for AI prompt review, model selection, and
execution planning.

Current scope:

- deterministic prompt judge heuristics;
- task profile and prompt issue data models;
- transparent model/backend recommendation over a caller-provided catalog.
- TOML model-catalog loading;
- execution planning to neutral `ExecutionTarget` values without calling providers.
- reusable execution preparation that combines prompt judging, model recommendation,
  and execution planning without calling providers.

Current non-goals:

- provider adapters;
- autonomous agents;
- learned routing;
- quota/billing platform;
- mandatory orchestration for every AI call.

The orchestrator owns decision contracts, not provider execution. Callers may adapt
an `ExecutionTarget` to `ai_provider`, direct Ollama calls, or another executor.
It must not implement provider APIs directly.

## Model Catalog

Use a TOML catalog with `[[models]]` entries. See `examples/model_catalog.toml`.

```python
from pathlib import Path

from ai_orchestrator import TaskProfile, load_model_catalog, plan_execution, recommend_model

catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
recommendation = recommend_model(TaskProfile(), catalog)
plan = plan_execution(TaskProfile(), recommendation)
```

## Execution Preparation

Use `prepare_execution` when a caller wants the first orchestration pass in one
step. It preserves the original prompt, optionally runs prompt review, recommends
a model/backend, and returns an execution plan. It does not execute the provider
request.

```python
from pathlib import Path

from ai_orchestrator import OrchestrationStatus, TaskProfile, load_model_catalog, prepare_execution

catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
result = prepare_execution(
    "Explain how to run the provider tests as a numbered list with short commands.",
    TaskProfile(),
    catalog,
)

if result.is_ready:
    target = result.execution_plan.target
elif result.status is OrchestrationStatus.MODEL_SELECTION_FAILED:
    reason = result.failure_reason
else:
    suggested_prompt = result.prompt_judge.refined_prompt
```

Set `review_prompt=False` for a direct/bypass path when the caller already knows
that prompt-review overhead is unnecessary. Expected model-selection failures,
such as an empty catalog or no candidate satisfying privacy/capability
constraints, are returned as `MODEL_SELECTION_FAILED` results.
