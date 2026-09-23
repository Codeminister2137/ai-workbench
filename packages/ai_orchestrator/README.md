# ai-orchestrator

Transparent orchestration primitives for AI prompt review, model selection, and
execution planning.

Current scope:

- deterministic prompt judge heuristics;
- task profile and prompt issue data models;
- transparent model/backend recommendation over a caller-provided catalog;
- TOML model-catalog loading;
- execution planning to neutral `ExecutionTarget` values without calling providers;
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

Catalog entries and execution targets are access-route oriented. Keep these
concepts separate:

- `route_id`: stable identifier for one official execution path;
- `provider`: the model provider or local runtime family, such as `ollama`,
  `openai`, or `requesty`;
- `product`: the product or service that owns the route, such as `ollama`,
  `openai_api`, `requesty`, or `codex`;
- `model`: the backend model identifier;
- `access_method`: how execution is reached, such as `local_runtime`,
  `provider_api`, or `codex_cli`;
- `auth_method`: the credential/session type required by that route, such as
  `none`, `api_key`, or `chatgpt_sign_in`;
- `billing_source`: where usage, quota, or allowance is consumed, such as
  `local_free`, `openai_api_billing`, `requesty_billing`, or
  `chatgpt_subscription_allowance`;
- `cost_policy_tier`: the minimum task policy required to use the route.

This distinction prevents agent/client surfaces such as Codex CLI from being
treated as ordinary provider API adapters. An `ai_provider` adapter should only
accept targets whose `access_method` matches provider execution; other access
methods need dedicated executors.

Task profiles default to `CostPolicyTier.ALLOWANCES_ALLOWED`. That allows local,
free, and included subscription/allowance routes, but rejects prepaid-credit and
metered-billing routes unless the caller explicitly raises the policy. This
prevents silent fallback across billing boundaries.

## Model Catalog

Use a TOML catalog with `[[models]]` entries. See `examples/model_catalog.toml`.
Catalog entries may include optional source-labelled numeric estimates under
`[models.estimate]`, such as typical latency and input/output cost per million
tokens. Recommendations include these numbers when available, and
`TaskProfile(max_expected_latency_seconds=...)` treats missing latency data as
not satisfying the hard time constraint.

Public pricing and model documentation are useful catalog priors, but wall-clock
latency should be treated as unknown unless it comes from measured local or
provider-specific benchmark data. Do not add generic latency numbers merely
because one model is described as faster than another.

```python
from pathlib import Path

from ai_orchestrator import TaskProfile, load_model_catalog, plan_execution, recommend_model

catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
profile = TaskProfile(max_expected_latency_seconds=60)
recommendation = recommend_model(profile, catalog)
plan = plan_execution(profile, recommendation)
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

## Codex CLI Execution Example

`packages/ai_orchestrator/examples/codex_cli_executor.py` is the minimal
dedicated executor route for targets with `access_method = "codex_cli"`. It runs
`codex exec` through an installed Codex CLI and uses the user's existing ChatGPT
sign-in state; it does not use API keys or `ai_provider.BackendConfig`.

Because Codex CLI is an external ChatGPT execution surface, the example rejects
`PrivacyClass.LOCAL_ONLY`. Use `PrivacyClass.EXTERNAL_ALLOWED` only for prompts
that may leave the local environment.

Use a small catalog containing the intended Codex CLI target, for example:

```toml
[[models]]
route_id = "openai-codex-gpt-5-1"
provider = "openai"
product = "codex"
model = "gpt-5.1"
location = "external"
access_method = "codex_cli"
auth_method = "chatgpt_sign_in"
billing_source = "chatgpt_subscription_allowance"
cost_policy_tier = "allowances_allowed"
quality = "standard"
latency = "interactive"
```

Then run a dry preparation pass before execution:

```powershell
python packages\ai_orchestrator\examples\codex_cli_executor.py `
  "Explain the repo test command." `
  --catalog path\to\codex-cli-catalog.toml `
  --model gpt-5.1 `
  --skip-prompt-review
```

Add `--execute` only when the prompt is ready to send to Codex CLI. If `codex`
is not on PATH, pass `--codex-command` with the executable path.
