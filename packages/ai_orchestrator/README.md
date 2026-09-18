# ai-orchestrator

Transparent orchestration primitives above `ai_provider`.

Current scope:

- deterministic prompt judge heuristics;
- task profile and prompt issue data models;
- transparent model/backend recommendation over a caller-provided catalog.
- TOML model-catalog loading;
- execution planning to `ai_provider.BackendConfig` without calling providers.

Current non-goals:

- provider adapters;
- autonomous agents;
- learned routing;
- quota/billing platform;
- mandatory orchestration for every AI call.

The orchestrator should call `ai_provider` for execution once a backend/model is selected. It must not implement provider APIs directly.

## Model Catalog

Use a TOML catalog with `[[models]]` entries. See `examples/model_catalog.toml`.

```python
from pathlib import Path

from ai_orchestrator import TaskProfile, load_model_catalog, plan_execution, recommend_model

catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
recommendation = recommend_model(TaskProfile(), catalog)
plan = plan_execution(TaskProfile(), recommendation)
```
