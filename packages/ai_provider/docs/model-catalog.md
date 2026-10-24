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
[the interface contract](interface.md). The per-route mapping from each
declared route id to its inferred upstream family, with an explicit
confidence level and gap description, is in
[route-upstream-family-mapping.md](route-upstream-family-mapping.md).
**Scoring rule — recommendation-only bands, decided 2026-10-23.** Each source
gets its own categorical band, deliberately more granular than a
high/medium/low split, and the band is a *recommendation*: the Orchestrator
keeps routing from the declared catalog, no prior changes a route on its own,
and a local L3 CLI measurement overrides a band for a specific task.

### Band scale

Six bands per source. Each source's cutoffs were calibrated on that source's
own published-row distribution in the dated 2026-10-22 snapshot
(p10 / p25 / median / p75 / p90, rounded to readable anchors) and then fixed,
so a later refresh moves a row between bands only when its published score
changes rather than because the edges moved with the field. They are
population bands, not equal-width bands: SWE-bench clusters near the top, so
its upper edges sit closer together than Aider's.

| Band | Aider polyglot `percent_correct` | SWE-bench Verified `percent_resolved` |
| --- | --- | --- |
| Frontier | ≥ 80 | ≥ 75 |
| Very strong | 70 – 80 | 70 – 75 |
| Strong | 50 – 70 | 55 – 70 |
| Mediocre | 25 – 50 | 40 – 55 |
| Weak | 12 – 25 | 24 – 40 |
| Very weak | < 12 | < 24 |

**The labels are a vocabulary, not a calibration.** Owner decision
(2026-10-23) renamed the middle three bands from `Strong` / `Solid` /
`Competent` — which read as synonyms — to `Very strong` / `Strong` /
`Mediocre`. Only the labels changed; every cutoff above stayed exactly where
it was, because the calibration is the data and the labels are how we read it.
A five-tier `Very high` / `High` / `Medium` / `Low` / `Very low` alternative
was rejected for two reasons: it would discard the `Frontier` distinction the
data supports and that is decision-relevant, and it would collide with
`ModelCatalogEntry.quality`'s `low` / `standard` / `high`. That field is the
*minimum requirement a task declares*; a band is *published evidence about an
upstream family*. Two different layers, so two vocabularies that must never
overlap — otherwise a band can be misread as a requirement, and a future change
feeding bands into selection could appear to satisfy one.

Share of each source's published rows — 69 Aider rows, 180 SWE-bench rows.
Reproduce with `python -m ai_provider.capability_bands --prior <snapshot>`:

| Band | Aider | SWE-bench |
| --- | --- | --- |
| Frontier | 6 (9%) | 13 (7%) |
| Very strong | 12 (17%) | 33 (18%) |
| Strong | 18 (26%) | 47 (26%) |
| Mediocre | 16 (23%) | 45 (25%) |
| Weak | 11 (16%) | 24 (13%) |
| Very weak | 6 (9%) | 18 (10%) |

Scale definitions, validation and the recompute command live in
`ai_provider.capability_bands`, tested in
[tests/test_capability_bands.py](../../../tests/test_capability_bands.py).

### Per-route bands

The 19 routes declared in `model_catalog.toml`, graded from the primary matched
row in [route-upstream-family-mapping.md](route-upstream-family-mapping.md) —
the row with the closest identity; alternate rows recorded there are not used.
`—` means that source published no row for this route's family, so the route
stays ungraded in that column.

| Route | Aider band | SWE-bench band | Confidence |
| --- | --- | --- | --- |
| `ollama/deepseek-coder-v2:16b` | — | — | `unmatched` |
| `ollama/gpt-oss:20b` | Mediocre (41.8) | — | `family` |
| `ollama/qwen2.5-coder:14b` | Very weak (8) | Very weak (9) | `family` |
| `ollama/qwen3:14b` | Mediocre (40) | — | `family` |
| `openai/codex-gpt-6.1-sol` | — | — | `unmatched` |
| `openai/codex-gpt-5.5` | Frontier (88) | — | `family` |
| `google/ai-studio-gemini-3.1-pro` | — | Strong (69.6) | `family` |
| `google/ai-studio-gemini-3.8-flash` | — | Frontier (75.8) | `family` |
| `google/antigravity-gemini-3.1-pro-high` | — | Strong (69.6) | `family` |
| `google/antigravity-gemini-3.8-flash-high` | — | Frontier (75.8) | `family` |
| `github/copilot-cli-auto` | — | — | `unmatched` |
| `kiro/auto` | — | — | `unmatched` |
| `openai/api-gpt-5.1` | Frontier (88) | — | `family` |
| `openai/api-gpt-5-mini` | Frontier (88) | — | `family` |
| `requesty/free-google/gemma-4-31b-it` | Very weak (4.9) | — | `family` |
| `requesty/openai/gpt-5.1` | Frontier (88) | — | `family` |
| `requesty/openai/gpt-5-mini` | Frontier (88) | — | `family` |
| `opencode-go/go-kimi-k2.7-code` | Strong (59.1) | Very strong (70.8) | `family` |
| `openrouter/free-google/gemma-4-31b-it:free` | — | — | `unmatched` |

14 routes are graded at `family` confidence and 5 stay ungraded; 10 carry an
Aider band, 6 a SWE-bench band, and only `opencode-go/go-kimi-k2.7-code` and
`ollama/qwen2.5-coder:14b` carry both.

**How to read this table.**

- **Two columns, never one number.** `percent_correct` and `percent_resolved`
  are different scales under different harnesses, so the two bands stand side
  by side and are never averaged, merged or ranked against each other.
- **`—` is absence, not weakness.** No score is imputed for an ungraded route,
  and a missing row never becomes a low band.
- **Every graded row is `family`, never `exact`.** No route matched a published
  id verbatim, so a band describes an upstream family across a version, size or
  effort gap — read the gap column before acting on it. `Frontier` on
  `openai/api-gpt-5-mini` is the *flagship* gpt-5 row: the mini tier itself is
  unmeasured, and `requesty/free-google/gemma-4-31b-it` is graded from an
  `edit=whole` run, the weakest edit format.
- **SWE-bench rows are scaffold-specific.** Every number there carries one agent
  scaffold, so the band describes a (model, scaffold) pair, not the model alone.
- **The bands are stale by construction.** Aider runs are dated to 2025-10-03
  and SWE-bench to 2026-02-26; re-read both before relying on a band.
- **A band is not a declared requirement.** `ModelCatalogEntry.quality`
  (`low` / `standard` / `high`) stays the task's declared minimum tier for a
  catalog entry, while a band is published evidence about an upstream family.
  The vocabularies are kept distinct on purpose, and no band ever writes to a
  catalog entry or an admission decision.

## Adding other providers

Add recommendations as they are investigated, recording exact model/access route,
task role, checked date, source and evaluated versus provisional status. Do not
invent a recommended model for every provider simply to fill a table. Existing
source readiness and unresolved limitations remain in [source-state.md](source-state.md).
Keep public recommendations separate from private account-specific preferences.
