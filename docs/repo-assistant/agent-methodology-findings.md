# Agent methodology findings and research sources

Recorded 2026-10-14. This is a reusable engineering review and research seed,
not a model ranking, availability guarantee, or instruction to run inference.
Source claims must be rechecked against current official documentation and the
exact hosted route before implementation. Historical failures remain evidence.

## Findings to retain

The native model/tool/observation loop follows conventional agent architecture.
A new agent framework is not needed to address the identified gaps.

| Finding | Evidence and limits | Engineering implication |
| --- | --- | --- |
| Gateway, model and upstream availability are separate | A direct Gemma request returned upstream throttling; other free routes answered small requests. Neither establishes enduring availability or coding quality. | Investigate alternate models/upstreams before making a provider-wide claim. Separate access checks from quality evaluations. |
| Ordinary history and provider continuation are different | Synthetic compatible-adapter inspection preserved tool IDs/arguments but did not capture or replay provider continuation. Ordinary loop history was retained. | Test the exact route contract using ADR-055's transient, origin-bound state and admission/logging protections. Missing continuation is not a proven cause of the observed repetition. |
| Effective model settings are unknown | Requests omitted sampling settings; NVIDIA and Cohere model cards recommend explicit settings. Native template options are not automatically gateway options. | Record matched, unmatched and unknown settings. Verify hosted support before changing payloads. |
| The strict pilot under-observes iterative recovery | Edit phases prohibited tests before independent host inspection; the first failed host check stopped the run. | Retain this safety evidence and add a distinct bounded edit/test/repair evaluation. Do not reinterpret failed strict trials as successes. |
| Structural inspection is not substantive plan acceptance | Initial requirements deliberately conflicted with a protected test; later correction resolved them. Some model planning claims were inaccurate despite passing structural gates. | Report structural and semantic outcomes separately; use a clear-task baseline as well as correction/freeze stress tests. |
| Repeated reads indicate lack of progress, not its cause | A correct source edit was followed by unchanged companion reads until the per-turn cap; required companion tests/review were incomplete. No observed API/tool validation error explains it. | Start with offline trace diagnosis. Warning, stopping and recovery behavior need separate policy decisions. |
| Normal CLI usage is not cumulative | The final response's usage was reported; intermediate metered calls were missing from normal turn totals, especially on failure. Independent pilot receipts retained the totals. | Distinguish per-response metrics, cumulative known sums and incomplete coverage. Missing usage/cost remains unknown. |
| Tool usability and attention need evaluation | Literal reads and edits worked in the observed runs; the required instructions, schemas and history were retained. | Evaluate clear tool feedback and current-task signals rather than removing required context or adding infrastructure. |

One small failed task per model cannot establish relative quality. A successful
connection or arithmetic response is not a coding-agent acceptance result.
Use independent checks of authored effects, protected inputs, substantive review,
numeric usage evidence and verified cleanup.

## Accepted direction and remaining boundaries

The owner accepted the recommendation on 2026-10-14: begin with offline exact-route
adapter/settings conformance and numeric usage reporting; retain the strict
authoring/correction/freeze evaluation and add a separately labelled bounded
iterative-development acceptance. Baseline CLI remains the priority; independent
unattended supervision remains the next established priority after baseline CLI.
Later research should inform these goals, rather than displace them.

The acceptance method is approved in principle. A concrete new live trial still
needs fresh inputs, explicit attempt/per-turn/time/tool bounds, permitted repair
conditions, independent final checks and owner grant/readiness. Consumed grants
cannot be reused. This record does not authorize reasoning logging, relaxed
privacy guards, paid fallback, a dependency, scheduler activation or promotion.

## 2026-10-15 evaluation follow-up

The scoped OpenRouter continuation/accounting changes are implemented offline.
A fresh bounded iterative run repaired source and passed its original tests, but
exhausted eight edit calls before companion tests, a final report or frozen review.
Its later host oracle pass is diagnostic only; acceptance remains failed.

The owner approved preparing a fresh 16-edit/4-review trial and requested an
alternative to repeated hard iteration cutoffs without allowing indefinite loops.
Progress-aware checkpoints are under investigation; no warning, recovery or stop
policy is selected or implemented. Distinguish resource exhaustion from observed
incorrectness, while preserving raw CLI status and strict historical outcomes.
Any alternative must retain explicit privacy, authorization and resource ceilings,
independent acceptance, fresh live grants and verified cleanup. Review allowance
must support serial tool use rather than relying on model batching. Thresholds,
attended versus automatic recovery and flexible phase allocation remain decisions.

## Source index for later research

| Source | Why retain it / question to revisit |
| --- | --- |
| [OpenRouter reasoning documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) | Returned reasoning exclusion differs from disabling generation; investigate documented continuation through tool turns and exact route requirements. |
| [NVIDIA Nemotron Super model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16) | Recommended sampling and coding-agent template settings; distinguish native capabilities from hosted free-route support. |
| [Cohere North Mini Code model card](https://huggingface.co/CohereLabs/North-Mini-Code-1.0) | Recommended sampling and benchmark harness/repetition methodology; benchmark claims are not local acceptance evidence. |
| [Cohere North Mini Code documentation](https://docs.cohere.com/docs/north-mini-code-1.0) | Current supported model behavior and integration guidance. |
| [Cohere tool-use patterns](https://docs.cohere.com/docs/tool-use-usage-patterns) | Normal multi-step tool/observation interaction and repair feedback. |
| [NVIDIA agent integration cookbook](https://github.com/NVIDIA-NeMo/Nemotron/blob/main/usage-cookbook/Nemotron-3-Super/OpenScaffoldingResources/README.md) | First-party agent configurations and pitfalls; recheck example aliases and allowances against the current endpoint. |
| [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Simple loops, environmental feedback and usable agent/computer interfaces. |
| [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Tool clarity and relevant current context; preserve required instructions while testing presentation. |
| [SWE-agent paper](https://arxiv.org/abs/2405.15793) | Study how interface design changes coding-agent performance; examine task sets, controls and transfer limits. |
| [LangChain/NVIDIA Nemotron Ultra harness study](https://www.langchain.com/blog/tuning-the-harness-not-the-model-a-nemotron-3-ultra-playbook) | First-hand study of trace-specific harness signals. Different model/harness; assess reproducibility and avoid fixture-specific prompt overfitting. No framework adoption implied. |
| [OpenClaw issue 86669](https://github.com/openclaw/openclaw/issues/86669) | Reported dropped template options and reasoning-only retry loops. A diagnostic clue, not a match to our successful tool calls or proof of our cause. |
| [OpenClaw issue 90982](https://github.com/openclaw/openclaw/issues/90982) | Reported hidden schema errors and retry loops. Our observed receipts had no such validation errors; inspect applicability before attribution. |
| [OpenRouter NVIDIA free endpoint metadata](https://openrouter.ai/api/v1/models/nvidia/nemotron-3-super-120b-a12b:free/endpoints) | Recheck current upstream, limits and supported parameters. Metadata is not a completion/access test. |
| [OpenRouter Cohere free endpoint metadata](https://openrouter.ai/api/v1/models/cohere/north-mini-code:free/endpoints) | Same route-specific checks; current official API outranks old catalog snapshots. |
| [OpenRouter status](https://status.openrouter.ai/) | Service-wide incident signals cannot prove an individual free route is usable. |
| [OpenRouter Downdetector](https://downdetector.co.uk/status/openrouter/) | User-report aggregation; useful corroboration, not a model-specific health oracle. |
| [Gemma model-status page](https://modelstatus.dev/models/google/gemma-4-31b-it:free) | Third-party route metrics; establish whether observations are independent or republished gateway data. |
| [Third-party OpenRouter free-tier probe](https://klymentiev.com/blog/openrouter-free-tier) | Historical cross-model access observations and linked data. Revisit methodology, timestamps and upstream isolation; arithmetic success does not establish agent quality. |

## Future research brief

Revisit these sources through the existing research workflow when it has an
authorized execution window and verified source/search grants. Produce a claim
matrix separating official contracts, study results, issue reports, local facts
and hypotheses. Record date/version, model, upstream, harness, settings, task set,
repetitions, controls, failure taxonomy and applicability to our implementation.
Keep contradictory evidence and identify what an offline check can resolve before
requesting inference. Select the smallest relevant experiment; do not install
software from examples or turn research into an automatic live model sweep.

The complete local review and immutable trial evidence remain separately preserved
in the private handoff/artifacts. This public-safe index contains no credentials,
raw prompts, private reasoning, account balances or machine-specific sessions.
