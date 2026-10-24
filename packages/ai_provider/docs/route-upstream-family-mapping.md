# Route â†’ upstream-family mapping

**Checked:** 2026-10-22 (snapshot date of both leaderboards below)
**Purpose:** turn public leaderboard priors into an explicit, dated, reviewable
mapping so a later scoring rule grades a *specific* route rather than silently
inheriting a family name.

This table is a **selection prior, never acceptance evidence**
(see `docs/repo-assistant/acceptance-criteria.md`). Local L3 CLI measurements
override every row here.

**Bands (decided 2026-10-23).** The granular per-source band graded from each
row below is published in [model-catalog.md](model-catalog.md) under
*Per-route bands*. This table stays the single record of which row was matched
and why; the band table is derived from the primary row of each source here.

## Sources

| Source | URL | Snapshot | Freshness |
| --- | --- | --- | --- |
| Aider polyglot leaderboard | <https://aider.chat/docs/leaderboards/> | `artifacts/model-capability-priors-20261022/aider-polyglot.json` (observed 2026-10-22) | runs 2024-12-21 â†’ 2025-10-03 |
| SWE-bench Verified leaderboard | <https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json> | `artifacts/model-capability-priors-20261022/swe-bench-verified.json` (observed 2026-10-22) | runs 2023-10-10 â†’ 2026-02-26 |

Aider uses **one harness**, so its scores are comparable model-to-model, and it
publishes the exact `--model` id. SWE-bench rows are *(model, harness)* pairs
under 77 different scaffolds and are **not** comparable across rows. The two
scales (`percent_correct` vs `percent_resolved`) must never be averaged.

## Confidence levels

| Level | Meaning | May carry a prior? |
| --- | --- | --- |
| `exact` | The leaderboard row is the same pinned model id as the route. | Yes |
| `family` | Same upstream family, but a version and/or size gap exists. | Yes, flagged as lower confidence |
| `alias` | The leaderboard publishes a rolling/unpinned alias that may resolve differently today. | Only with the alias warning attached |
| `unmatched` | No leaderboard row for this route's family. | **No â€” left ungraded** |

## Mapping table

Route ids are the 19 routes declared in
`packages/ai_orchestrator/examples/model_catalog.toml` as of 2026-10-22.

| Route id | Catalog model id | Inferred upstream family | Best matching leaderboard row | Confidence | Gap | Evidence | Checked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ollama/deepseek-coder-v2:16b` | `deepseek-coder-v2:16b` | DeepSeek Coder V2 | â€” | `unmatched` | Coder V2 is a distinct line from the V3 general models SWE-bench lists (`deepseek v3 0324`, `deepseek v3.2`); Aider's only DeepSeek rows are the rolling alias `deepseek/deepseek-chat` and `deepseek/deepseek-reasoner` | no Coder V2 row in either snapshot | 2026-10-22 |
| `ollama/gpt-oss:20b` | `gpt-oss:20b` | OpenAI gpt-oss | Aider `openrouter/openai/gpt-oss-120b`, 41.8% `percent_correct`, `edit=diff`, 2025-08-06 | `family` | size gap: 20b vs 120b | Aider polyglot row | 2026-10-22 |
| `ollama/qwen2.5-coder:14b` | `qwen2.5-coder:14b` | Qwen2.5-Coder | Aider `openai/Qwen/Qwen2.5-Coder-32B-Instruct`, 8.0% `percent_correct`, `edit=diff`, 2024-12-22; SWE-bench `qwen2.5 coder 32b instruct` (9.0 mini-SWE-agent, 2025-08-03; 38.0 Skywork-SWE-32B, 2025-06-16) | `family` | size gap: 14b vs 32b | Aider + SWE-bench rows | 2026-10-22 |
| `ollama/qwen3:14b` | `qwen3:14b` | Qwen3 | Aider `openrouter/qwen/qwen3-32b`, 40.0% `percent_correct`, `edit=diff`, 2025-05-08 (also `openai/qwen3-235b-a22b`, 59.6%) | `family` | size gap: 14b vs 32b / 235b | Aider polyglot rows | 2026-10-22 |
| `openai/codex-gpt-6.1-sol` | `gpt-6.1-sol` | GPT-6.1 | â€” | `unmatched` | neither snapshot contains a GPT-6 row | no GPT-6 row in either snapshot | 2026-10-22 |
| `openai/codex-gpt-5.5` | `gpt-5.5` | GPT-5 | Aider `openai/gpt-5`, 88.0% `percent_correct`, `edit=diff; reasoning=high`, 2025-08-23 (86.7 medium, 81.3 low) | `family` | version gap: 5.5 vs 5.0; also a rolling family with materially different scores per reasoning level | Aider polyglot rows | 2026-10-22 |
| `google/ai-studio-gemini-3.1-pro` | `gemini-3.1-pro` | Gemini 3 Pro | SWE-bench `gemini 3 pro`, 69.6 `percent_resolved`, mini-SWE-agent, 2026-02-26 (also `gemini 3 pro preview` 74.2 verified, mini-SWE-agent, 2025-11-18) | `family` | version gap: 3.1 vs 3.0; Aider carries no Gemini 3 rows at all | SWE-bench rows | 2026-10-22 |
| `google/ai-studio-gemini-3.8-flash` | `gemini-3.8-flash` | Gemini 3 Flash | SWE-bench `gemini 3 flash`, 75.8 `percent_resolved`, mini-SWE-agent, 2026-02-17 | `family` | version gap: 3.8 vs 3.0 | SWE-bench row | 2026-10-22 |
| `google/antigravity-gemini-3.1-pro-high` | `gemini-3.1-pro-high` | Gemini 3 Pro | SWE-bench `gemini 3 pro`, 69.6 `percent_resolved`, mini-SWE-agent, 2026-02-26 | `family` | version gap plus the `-high` effort suffix, which no leaderboard measures | SWE-bench row | 2026-10-22 |
| `google/antigravity-gemini-3.8-flash-high` | `gemini-3.8-flash-high` | Gemini 3 Flash | SWE-bench `gemini 3 flash`, 75.8 `percent_resolved`, mini-SWE-agent, 2026-02-17 | `family` | version gap plus the `-high` effort suffix | SWE-bench row | 2026-10-22 |
| `github/copilot-cli-auto` | `auto` | provider-selected | â€” | `unmatched` | the model id is not fixed; the provider picks per request, so a static prior cannot describe this route | catalog declares `model = "auto"` | 2026-10-22 |
| `kiro/auto` | `auto` | provider-selected | â€” | `unmatched` | same as above | catalog declares `model = "auto"` | 2026-10-22 |
| `openai/api-gpt-5.1` | `gpt-5.1` | GPT-5 | Aider `openai/gpt-5`, 88.0% `percent_correct`, `edit=diff; reasoning=high`, 2025-08-23 | `family` | version gap: 5.1 vs 5.0 | Aider polyglot rows | 2026-10-22 |
| `openai/api-gpt-5-mini` | `gpt-5-mini` | GPT-5 | Aider `openai/gpt-5`, 88.0% `percent_correct`, `edit=diff; reasoning=high`, 2025-08-23 | `family` | version/size gap: the mini tier is unmeasured; the flagship score is the only GPT-5 row | Aider polyglot rows | 2026-10-22 |
| `requesty/free-google/gemma-4-31b-it` | `google/gemma-4-31b-it` | Gemma | Aider `openrouter/google/gemma-3-27b-it`, 4.9% `percent_correct`, `edit=whole`, 2025-03-15 | `family` | version + size gap: Gemma 3 27b vs Gemma 4 31b; the matched row is also the weakest-edit-format tier, so it is a weak prior | Aider polyglot row | 2026-10-22 |
| `requesty/openai/gpt-5.1` | `openai/gpt-5.1` | GPT-5 | Aider `openai/gpt-5`, 88.0% `percent_correct`, `edit=diff; reasoning=high`, 2025-08-23 | `family` | version gap: 5.1 vs 5.0 | Aider polyglot rows | 2026-10-22 |
| `requesty/openai/gpt-5-mini` | `openai/gpt-5-mini` | GPT-5 | Aider `openai/gpt-5`, 88.0% `percent_correct`, `edit=diff; reasoning=high`, 2025-08-23 | `family` | version/size gap: mini tier unmeasured | Aider polyglot rows | 2026-10-22 |
| `opencode-go/go-kimi-k2.7-code` | `kimi-k2.7-code` | Kimi K2 | SWE-bench `kimi k2.5`, 70.8 `percent_resolved`, mini-SWE-agent, 2026-02-17 (also `kimi k2` 71.2 Lingxi v1.5, 2025-10-14; Aider `openrouter/moonshotai/kimi-k2` 59.1% `percent_correct`, `edit=diff`, 2025-07-17) | `family` | version gap: K2.7 vs K2.5/K2.0; the route is also a code-tuned variant the leaderboards do not distinguish | SWE-bench + Aider rows | 2026-10-22 |
| `openrouter/free-google/gemma-4-31b-it:free` | `google/gemma-4-31b-it:free` | Gemma | none | `unmatched` | the `:free` serving variant has no measured row, and the matcher refuses to inherit the paid Gemma row for a differently served variant | no leaderboard row for the `:free` variant | 2026-10-24 |

## Coverage summary (2026-10-22)

| Confidence | Count | Route ids |
| --- | --- | --- |
| `exact` | 0 | â€” |
| `family` | 14 | `ollama/gpt-oss:20b`, `ollama/qwen2.5-coder:14b`, `ollama/qwen3:14b`, `openai/codex-gpt-5.5`, `google/ai-studio-gemini-3.1-pro`, `google/ai-studio-gemini-3.8-flash`, `google/antigravity-gemini-3.1-pro-high`, `google/antigravity-gemini-3.8-flash-high`, `openai/api-gpt-5.1`, `openai/api-gpt-5-mini`, `requesty/free-google/gemma-4-31b-it`, `requesty/openai/gpt-5.1`, `requesty/openai/gpt-5-mini`, `opencode-go/go-kimi-k2.7-code` |
| `alias` | 0 | â€” |
| `unmatched` | 5 | `ollama/deepseek-coder-v2:16b`, `openai/codex-gpt-6.1-sol`, `github/copilot-cli-auto`, `kiro/auto`, `openrouter/google/gemma-4-31b-it` |

14 + 5 = 19 routes, matching the declared catalog. **No route achieved
`exact`**, because neither leaderboard publishes any of our pinned,
current-generation ids verbatim. **Every `unmatched` route stays ungraded** â€”
no score from a neighbouring family is attached to it.

## Standing cautions

1. **Every match is a family match.** A family score describes a *different*
   model than the one our route serves. Treating it as this route's quality
   would be a silent substitution, which is why each row states its gap.
2. **`model = "auto"` routes cannot have a static prior.** Copilot and Kiro pick
   the underlying model per request; only a live observation of what actually
   served a request could grade them.
3. **Unpinned aliases decay.** Aider's `deepseek/deepseek-chat` published 17.8 â†’
   70.2 under an identical configuration across ten months; do not use an
   alias row as a current-quality claim.
4. **Effort/size suffixes are unmeasured.** `-high`, `-mini`, `-31b` and similar
   suffixes change results materially and no leaderboard row here isolates
   them.
5. **Re-read before relying.** The OpenRouter free-route snapshot from the same
   collection showed the free catalogue turning over within the hour; the same
   freshness caveat applies to leaderboard rows that are periodically rerun.

## Offline mapping proposals

`ai_provider.route_family_matcher.propose_route_family` proposes a dated mapping
from a route id, catalog model id and already parsed `CapabilityScore` rows.
It runs offline, preserves the selected configuration and harness, and states
identity gaps and rolling-alias warnings. It never assigns bands or changes routing.
A machine proposal is **not an accepted mapping until a human reviews it**.
See [route_family_matcher.py](../src/ai_provider/route_family_matcher.py) for the
conservative matching layers and deterministic candidate selection policy.
