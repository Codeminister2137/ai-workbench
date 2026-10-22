# Access and agent integration options

Use [source-state.md](source-state.md) as the dated facts and source index. Read
its latest scoped updates before using historical tables. It covers Codex expansion,
Copilot, OpenRouter, Kiro, Antigravity, Claude, OpenCode Go and free/trial offers,
including privacy and quality uncertainties. Private account state belongs in local
receipts and the immediate handoff, never in this public document.

## Capacity and integration are separate choices

| Choice | Benefit | Cost or constraint |
| --- | --- | --- |
| Extend an established subscription route | Smallest integration change | Checkout terms and remaining quota need account evidence |
| Add another official agent subscription | Alternative native coding workflow and billing source | Verify its tools, permissions, instructions, history and lifecycle |
| Use a gateway subscription such as Go | Model choice without requiring replacement of the whole application | Adapter/source-info implemented; remaining allowance is not exposed by the Go inference key |
| Use free/trial offers | Potential low-cost bounded evaluation | Availability, quality and tool compatibility may not fit the task |

Recommended models and roles are in the [provider model catalog](model-catalog.md),
with dated limits and privacy findings in
[the model follow-up](source-state.md#opencode-go-model-starting-points--checked-2026-10-22).
An external IDE agent is a useful development environment; its work must still
be attributed correctly and cannot certify a workflow it did not exercise.

## Official SDKs versus current CLI executors

The researched Codex and Copilot SDK capabilities and primary links are in
[the SDK follow-up](source-state.md#follow-up-opencode-go-claude-and-official-agent-sdks--2026-10-22).
The [Claude subscription/Agent SDK finding](source-state.md) is recorded there too.

| Approach | Benefit | Cost or risk |
| --- | --- | --- |
| Keep existing CLI executors | Existing behavior, tests and native-client compatibility | Continue maintaining command and event adaptation |
| Add optional SDK-backed executors | Potentially clearer sessions, streamed events, cancellation and permission callbacks | New dependencies, version/runtime management and renewed contract verification |
| Replace the neutral execution architecture with one vendor SDK | Fewer local abstractions in a vendor-specific application | Conflicts with this repository's provider-neutral composition; not recommended |

Recommendation: assess optional SDK adapters against current contracts offline
before choosing adoption. Start with an explicit child-process transport. Keep
the existing Orchestrator responsible for route/fallback choices and existing
project tools responsible for scoped authorization and observable effects.

Verify instruction/history delivery, model/reasoning settings, permissions, tool
mapping, events/errors/usage, cancellation, time bounds, cleanup, retention and
billing identity. Preserve client-owned session/auth behavior where applicable;
do not treat SDK defaults as approval to broaden authority. SDK convenience does
not establish additional allowance, higher model quality or automatic parity.

No SDK adoption, dependency, gateway adapter, scheduler, persistence change or
automatic model selection follows from this research. ADR-021/031 govern access
and billing boundaries; ADR-040 covers shared tools; ADR-042/052 cover fallback.
Manual model recommendations remain distinct from production routing policy.
