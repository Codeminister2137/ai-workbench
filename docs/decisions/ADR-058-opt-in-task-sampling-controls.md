# ADR-058 — Opt-in task sampling controls

**Status:** Accepted and implemented offline; live settings/quality acceptance incomplete
**Date:** 2026-10-15

## Decision and rationale

The owner accepted the recommendation to add opt-in per-run temperature and top_p
controls while preserving existing defaults. The decision followed the offline
finding that native coding requests omitted sampling, while the selected NVIDIA
and Cohere model cards recommend explicit settings. The technical recommendation
was reproducible task requests without silently choosing new model defaults;
the owner agreed with that recommendation. No additional personal rationale is
inferred.

Expose `--temperature` (finite 0–2) and `--top-p` (finite 0–1) on the repo-assistant
CLI. Append optional `top_p` to the neutral AIRequest contract; existing request
construction remains compatible. These are invocation options, not persisted user
defaults, routing policy or automatic model-specific presets. Omitted values
remain omitted on the wire; zero is an explicit value. Endpoint/model-specific
restrictions may still reject otherwise valid CLI values.

Forward explicit values through task requests, native tool turns, task repairs,
legacy action follow-ups, scrutiny, provider chat and provider fallback/preservation.
Native delegated task loops inherit their invocation arguments. Independently
configured context delegation and rolling-summary requests retain their separate
behavior; these flags do not reconfigure every auxiliary model in the process.
Compatible APIs receive top-level sampling fields; Ollama receives options.
The measured-prefix experiment includes both values in its scope fingerprint.
Print requested values as safe numeric metadata, without claiming the endpoint
actually applied them or that quality improved.

External native-agent clients do not have verified equivalent parameter mappings.
Explicit task sampling therefore excludes those primary/fallback/preservation
executors with an actionable refusal before authentication/execution, rather than
silently discarding a user option. Existing fallback quality, tier, privacy,
approval and deadline constraints remain binding. No template override, new
dependency, storage schema, default promotion or fresh inference grant follows.

## Alternatives and consequences

- **Opt-in controls, selected:** allows explicit and comparable requested settings,
  preserves omitted defaults; adds two optional contract/CLI fields and requires
  forwarding tests. Some otherwise usable external clients become incompatible
  when a sampling override is supplied.
- **Endpoint defaults:** avoids expanding configuration and maintains the existing
  executor set; settings remain unmatched/unknown and reduce trial comparability.

## Validation and sources

Deterministic checks cover absent and zero settings, finite/range admission,
native/compatible payloads, complete tool turns, provider fallback after partial
effects, repair request composition, external-client refusal and admission-scope
invalidation. Fake HTTP only; no allowance-consuming checks in pytest or hooks.

- [OpenRouter sampling parameters](https://openrouter.ai/docs/api_reference/parameters)
- [Ollama options](https://docs.ollama.com/modelfile#valid-parameters-and-values)
- [NVIDIA model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16)
- [Cohere model card](https://huggingface.co/CohereLabs/North-Mini-Code-1.0)
