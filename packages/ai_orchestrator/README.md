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
  and execution planning without calling providers;
- neutral deterministic prompt refinement with optional prior-response and critique
  provenance;
- subtask profile derivation and local delegation planning.

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

Entries may also declare optional context metadata:

```toml
[models.context_limits]
context_window_tokens = 32768
runtime_context_tokens = 4096
```

`context_window_tokens` is the model's advertised maximum. `runtime_context_tokens`
is the effective deployment default when a local runtime allocates less than the
model maximum because of available memory or other runtime settings. These are
metadata signals for routing and prompt budgeting, not a guarantee that every
provider route accepts the same value.

Use `[models.metadata]` for additional scalar model facts that should be
displayed or preserved but do not yet affect orchestration:

```toml
[models.metadata]
family = "qwen2"
parameter_size = "14.8B"
quantization_level = "Q4_K_M"
```

This keeps the TOML catalog easy to extend today while leaving room to migrate
the same structured records into a database later.

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
request. Prompt-review warnings and refinement suggestions are advisory; only
issues marked `blocking` stop execution.

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

## Subtask Profile Derivation And Delegation

Use `derive_subtask_profile` and `plan_delegated_subtask` to delegate smaller,
preparatory, or subsidiary steps (such as context summarization or prompt
refinement) to local or low-cost compute:

- Child profiles inherit their parent's `privacy_class` by default.
- Child profiles default their `cost_policy_tier` to `LOCAL_ONLY` to route
  smaller steps to free local models (e.g., Ollama), while accepting an
  explicit tier if hosted subtask execution is desired.
- Parent model/backend overrides do not constrain child subtasks unless
  explicitly passed.

For coding tasks, local delegation is intended for bounded, source-verifiable
work such as context extraction, file summarization, symbol extraction, and
test-case generation. Architectural recommendations and implementation
decisions stay with the primary model. Use `assess_delegation` with a
`DelegationKind` before executing a delegated coding subtask.

See `packages/ai_orchestrator/examples/ollama_delegation.py` for a working
multi-phase workflow planning example.

## Prompt Refinement

Use `PromptRefinementRequest` and `refine_prompt` for a provider-independent
pre-execution refinement pass. The orchestrator can also carry an optional prior
response and critique as provenance, but it does not execute models or depend on
the AI Council. Applications may inject their own executor for model-assisted
variants or post-response critique.

```python
from ai_orchestrator import PromptRefinementRequest, refine_prompt

refinement = refine_prompt(
    PromptRefinementRequest(
        prompt="Analyze this project and suggest next steps.",
        prior_response=None,
    )
)
if refinement.requires_user_approval:
    prompt = refinement.refined_prompt
```

```python
from ai_orchestrator import TaskProfile, TaskType, load_model_catalog, plan_delegated_subtask

catalog = load_model_catalog(Path("packages/ai_orchestrator/examples/model_catalog.toml"))
parent_profile = TaskProfile(privacy_class=PrivacyClass.EXTERNAL_ALLOWED)

subtask_plan = plan_delegated_subtask(
    parent_profile=parent_profile,
    catalog=catalog,
    task_type=TaskType.SUMMARIZATION,
    subtask_id="context_summary",
    description="Summarize large repo context locally",
)
# subtask_plan.execution_plan.target will route to a local Ollama model
```

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
route_id = "openai-codex-gpt-5-5"
provider = "openai"
product = "codex"
model = "gpt-5.5"
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
  --model gpt-5.5 `
  --skip-prompt-review
```

By default the example uses ephemeral Codex sessions. Pass
`--codex-persist-session` to start a resumable session, or
`--codex-resume last` / `--codex-resume <session-id-or-name>` to resume through
`codex exec resume`.
Pass `--codex-output-last-message path\to\last-message.txt` to also request
Codex's `--output-last-message` artifact for deterministic final-message
capture.
