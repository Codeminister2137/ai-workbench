# ADR-065 — Route-id naming convention: `provider/product-model`

**Status:** Accepted

**Date:** 2026-10-22

**Amends:** ADR-021 (access routes and cost policy boundaries). ADR-021 defines a
route as `provider + product + model`; this ADR fixes how that identity is
*displayed and selected*, not what it means.

## Context

Route ids were hand-authored and inconsistent. Seventeen of eighteen routes in
`packages/ai_orchestrator/examples/model_catalog.toml` used a hyphen-joined
`provider-product-model` form with the model's punctuation stripped
(`ollama-qwen2-5-coder-14b` for model `qwen2.5-coder:14b`), while one route used
a bare model id (`kimi-k2.7-code`). The hyphen form was lossy: the label no
longer showed the real model string, and the boundary between provider, product
and model was not visible.

Separately, `--provider` hardcoded `["ollama", "openai", "requesty", "google"]`
in `packages/ai_agent/src/ai_agent/repo_assistant_args.py`, wrongly rejecting
`github`, `kiro` and `opencode_go`, which the catalog does declare.

## Investigation

`route_id` is never parsed anywhere in the codebase. It is only ever compared for
equality (recommender selection, fallback attempts) and printed to output, JSON
metadata and transcripts. It is never used as a filesystem path component in the
packages. The separator is therefore a readability choice, not a structural one,
so `/` is safe. Tests already used `/` in route ids (`ollama/qwen`,
`openrouter/free`).

Wider ecosystem conventions for namespaced identifiers all use `/` as the
hierarchy separator: OpenRouter `author/model` (`openai/gpt-5.1`, variant
suffixes `:free`), HuggingFace `org/model`, OCI/Docker
`registry/repository/image:tag`, and npm/PyPI `scope/package`. Ollama uses
`model:tag`. Three-segment gateway ids are conventional — OpenRouter's own ids
are `openrouter/moonshotai/kimi-k2` — so a route whose model id itself contains
`/` (the Requesty gateway routes) produces a normal, readable multi-segment
label rather than an anomaly.

## Decision

All route ids use the form **`provider/product-model`**:

- The provider is always the leading segment.
- Product and model are joined with `-`.
- The product is **omitted when it only repeats the provider**, so
  single-product routes read as `ollama/deepseek-coder-v2:16b`, not
  `ollama/ollama-deepseek-coder-v2:16b`.
- Model ids keep their **native punctuation** (`:`, `.`, `/`), so the label shows
  the real model string instead of a lossy hyphen-mangled form.
- Provider and product values that would be awkward in a label use human
  slugs: `opencode_go` → `opencode-go`, and `google_ai_studio`, `openai_api`,
  `requesty_free`, `github_copilot` → `ai-studio`, `api`, `free`, `copilot-cli`.

`product` stays in the label because ADR-021 makes it part of route identity.
Routes that share a provider and a model but differ by product are different
billing boundaries (OpenAI via Codex subscription vs OpenAI direct API; Google
AI Studio free tier vs Antigravity allowance), and hiding the product would make
those indistinguishable at a glance.

Route ids remain **opaque keys**. They are not parsed back into their components;
the catalog is the source of truth for `provider`, `product` and `model`.

`_default_route_id()` in `packages/ai_orchestrator/src/ai_orchestrator/catalog.py`
derives this form for any catalog entry that omits `route_id`, and a test asserts
the derivation reproduces every declared route id so the hand-authored catalog
cannot drift from the convention.

### `--provider` is catalog-derived

`--provider` no longer hardcodes its choices. It is validated against the
providers declared by the loaded `--catalog`, so every provider a catalog
declares is accepted and an unknown value fails with the available providers
listed.

## Consequences

- All 18 catalog route ids changed. Example commands in
  `docs/repo-assistant/coding-chat.md`, `getting-started.md` and
  `external-agents.md` were updated; they remain valid unquoted shell arguments
  since `/`, `.` and `:` need no quoting.
- `github-copilot-cli-default` becomes `github/copilot-cli-auto`, because the
  catalog's `model` field is `auto`, not `default`. The label now states the
  real model.
- Evidence artifacts under `artifacts/opencode-go-*` and
  `artifacts/cli-baseline-live-*` retain the old labels; they are historical
  records and are deliberately not rewritten.
- The two explicitly frozen historical routes — `gemini-cli-free-flash` in
  `packages/ai_orchestrator/examples/gemini_cli_catalog.toml` and
  `openrouter-free-qwen38-27b` in
  `packages/ai_orchestrator/examples/openrouter_free_catalog.toml` — were left
  unchanged. Both files are marked "preserve the failed route" evidence, and
  rewriting preserved evidence would defeat their purpose.
- A future route whose product equals its provider must omit the product; the
  derivation and its test enforce this automatically.
