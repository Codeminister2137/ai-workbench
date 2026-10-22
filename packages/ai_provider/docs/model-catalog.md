# Provider model recommendations

This is a human-readable recommendation catalog, not executable routing policy.
The runtime route catalog belongs to
[ai_orchestrator](../../ai_orchestrator/examples/model_catalog.toml).
Provider/gateway, exact model and access route remain separate identities.
Listing a model here does not implement its adapter or authorize inference.

## OpenCode Go

Checked 2026-10-22. See [dated source findings](source-state.md#opencode-go-model-starting-points--checked-2026-10-22)
and [official Go documentation](https://opencode.ai/v2/docs/console/go/).

| Model | Model ID | Recommended role | Evidence / limitation |
| --- | --- | --- | --- |
| Kimi K2.7 Code | `kimi-k2.7-code` | Current single-model starting point for implementation, tests and frozen review | Provisional engineering recommendation; repository quality acceptance unestablished |
| GLM-5.2 | `glm-5.2` | Alternative implementation model for later selection | Retained option; no manual switch required by the current workflow |
| GLM-5.3 | `glm-5.3` | Optional different-model reviewer for later automated selection | Not a current review requirement; repository quality acceptance unestablished |

Current workflow preference: use Kimi throughout while model switching remains
manual. Keep frozen review as a separate read-only phase, preferably a fresh
session using the same model. This avoids manual model coordination; the cost is
that implementation and review may share model-specific blind spots. A fresh
session provides separation of task/context, not model diversity or guaranteed
independent judgment. Actual tests, factual reporting, frozen inputs and owned
cleanup remain required.

Model alternatives are recommendations for future selection, not an automatic
fallback chain, measured quality ranking, model-switch instruction, or permission
to change billing/privacy. Record new task evidence before promoting a model's
quality grade. Account quota and exact hosted model availability still need fresh
admission; credentials never belong in this catalog.

## OpenCode Go temporary free candidates

Checked 2026-10-22 against the [official offer and privacy table](https://opencode.ai/v2/docs/console/go/). Live model listing and access probes were also run; see [source-state.md](source-state.md).

| Model | Exact ID | Advertised usage | Training / retention | Live listing status |
| --- | --- | --- | --- | --- |
| LongCat 2.5 Preview Free | `longcat-2.5-preview-free` | Temporarily free, unlimited | No training / zero days | **Not returned** by `GET /inference/go/v1/models` today; access unverified |
| MiniMax M3.1 Flash Free | `minimax-m3.1-flash-free` | Temporarily free, unlimited | No training / zero days | Listed; probe **ok** |
| Beam Free | `beam-free` | Temporarily free, unlimited; regional exclusions | No training / 30 days | Listed; probe **ok** |

These are future evaluation candidates, not accepted coding replacements. The
promotion has no specified end date on the checked page; traffic abuse controls
remain. Advertised allowance is not guaranteed throughput or model quality.
Retain Kimi as the current single-model preference; no manual switch or inference
is requested by listing these options.

Live access probes found **13 of 36 models failing** with the initial
Chat-Completions-only adapter. After implementing Responses/Messages protocol
routing and toggling Console Privacy settings for Global regions and
training-on-request-data, the rerun with `max_output_tokens=16` found **3 of 36
models still failing** (`mimo-v2.5-pro`, `gemini-4-argon-contributor`,
`longcat-2.0`). Several models (`qwen3.6-plus`, `qwen3.7-max`, `qwen3.7-plus`,
`grok-4.6`) still ignore the requested `max_output_tokens` limit. Update any
fallback plan with these observations rather than assuming all listed models are
interchangeable.

OpenCode Go exposes **three protocol endpoints**, all now implemented in
`ai_provider`:

- **Chat Completions** (`/inference/go/openai/v1/chat/completions`): GLM, Kimi,
  LongCat, MiMo, Hy3, Omen Alpha, Space Bunny, Qwen. Served by
  `OpenCodeGoChatClient`.
- **Responses** (`/inference/go/v1/responses`): Grok, GPT Luna, Muse Spark
  Contributor, DeepSeek (some variants). Served by `OpenCodeGoResponsesClient`,
  which extends the generic `OpenAIResponsesChatClient` base adapter.
- **Messages** (`/inference/go/v1/messages`): MiniMax M2.7, Claude Haiku 5.5.
  Served by `OpenCodeGoMessagesClient`, which extends the generic
  `AnthropicMessagesChatClient` base adapter.

`create_chat_client` selects the adapter based on the model's declared protocol.
`OpenCodeGoSourceInfo` populates each model's `protocol`,
`trains_on_request_data`, and `requires_global_regions` metadata so callers can
enforce privacy choices before inference.

DeepSeek and Muse Spark Contributor models additionally require specific Privacy
settings in the OpenCode Console (Global regions and "allow paid endpoints that
train on request data"). With those toggles enabled, the latest all-model probe
achieved **33 ok / 3 error**; `gemini-4-argon-contributor` remains unsupported on
all three endpoints, `mimo-v2.5-pro` remains upstream-unsupported, and
`longcat-2.0` remains unavailable.

## Capability prior coverage — checked 2026-10-22

Where an *internet* capability prior exists for the routes above, and where it
does not. The prior is a selection aid, never acceptance evidence: a public
benchmark scores a model under a particular agent scaffold, not our CLI.

Two public sources were checked:

| Source | Shape | Coverage of our routes | Limitation |
| --- | --- | --- | --- |
| [SWE-bench Verified](https://www.swebench.com/) | One row per **(model, agent scaffold)** pair; 180 rows, 84 distinct model names, 77 distinct scaffolds | 17 of the 36 Go routes have a *family* match, always across a version gap; the 17 OpenRouter free variants have **none** | Scaffold-confounded: the same model appears under many agents with different scores. Runs dated 2023-10-10 to **2026-02-26** |
| [Aider polyglot](https://aider.chat/docs/leaderboards/) | One row per model under **a single consistent harness**; 69 runs, 53 distinct model ids | Covers the gateway-served open-weight families we actually have: `gpt-oss-120b`, `kimi-k2`, `qwen3-32b`, `gemma-3-27b-it`, `grok-3/4`, plus `deepseek`, `gemini`, `claude`, `gpt` | Comparability and coverage are better, but **currency is worse**: runs dated 2024-12-21 to **2025-10-03** |

Neither source wins outright. Aider is the better prior for ranking models
against each other, because one harness makes its scores comparable and it
publishes a **specific model id** rather than a display name. SWE-bench is
fresher by about four months and closer to our real task shape, but its rows
cannot be compared with each other. Record both, weigh currency explicitly, and
do not average across them: `percent_correct` and `percent_resolved` are
different scales, and the readers keep them distinct rather than pretending
they are interchangeable.

**Four findings constrain any future scoring decision.** All four were measured
from the readers on 2026-10-22 and are saved with provenance under
`artifacts/model-capability-priors-20261022/`:

1. **An unpinned model id is a rolling alias.** `deepseek/deepseek-chat`
   published 17.8, 48.4, 55.1 and 70.2 under an *identical* configuration
   between 2024-12-21 and 2025-10-03. A leaderboard score for an unpinned id
   describes a snapshot, not what that id resolves to today. Prefer pinned ids
   such as `anthropic/claude-3-7-sonnet-20250219` or
   `gemini/gemini-2.5-pro-preview-06-05`.
2. **Configuration materially changes the score.** `openai/gpt-5` scored 88.0
   at high reasoning effort, 86.7 at medium and 81.3 at low; `o3` scored 81.3
   as `diff` and 78.2 as `architect`. Every record keeps its configuration, so
   repeated runs stay distinguishable instead of appearing to contradict.
3. **Accuracy is not reliability.** `openai/gpt-5` reached 88.0% with only
   91.6% well-formed answers, while `gemini/gemini-2.5-pro-preview-06-05`
   reached 83.1% at 99.6% well-formed. A model that is right more often can be
   the worse choice for an unattended run.
4. **The OpenRouter free route set turns over.** Between two sweeps about fifty
   minutes apart, `openai/gpt-oss-120b:free` and `qwen/qwen3.8-27b:free`
   dropped out of the public free catalogue while the count stayed at 17.
   Availability is therefore a point-in-time reading that must be re-read
   before use, never a cached property.

**No public leaderboard covers the newest route ids.** Qwen 3.6+/3.7+/3.8+,
Kimi K2.7, GLM 5.1-5.3, Grok 4.6/4.7, MiMo 2.5/2.6, LongCat 2.0, Beam,
Muse Spark, Omen Alpha and the Hy previews have no published internet prior at
all. For those routes the internet prior is **absent**, not merely weaker,
which is the strongest practical argument for judging them from our own CLI
transcripts.

Readers: `ai_provider.openrouter_endpoints` (route availability),
`ai_provider.swe_bench_scores` and `ai_provider.aider_polyglot_scores`
(published capability priors). The shared records are documented in
[the interface contract](interface.md). **Scoring is deliberately undecided**:
the Orchestrator keeps routing from the declared catalog until these readings
are normalized into a per-model grade, and no prior changes a route on its own.

## Adding other providers

Add recommendations as they are investigated, recording exact model/access route,
task role, checked date, source and evaluated versus provisional status. Do not
invent a recommended model for every provider simply to fill a table. Existing
source readiness and unresolved limitations remain in [source-state.md](source-state.md).
Keep public recommendations separate from private account-specific preferences.
