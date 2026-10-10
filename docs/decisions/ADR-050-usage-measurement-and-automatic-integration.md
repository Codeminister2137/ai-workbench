# ADR-050 - Usage Measurement and Automatic Integration

**Status:** Accepted direction (2026-10-10); Codex/Copilot observations and Kiro native estimates integrated

## Context and alternatives

Delegation economics and usage-aware routing need measurements that reflect the
resource each route consumes. Token counts alone do not establish subscription
allowance consumption or API spend. Existing receipt diagnostics expose some
consumption counters but do not establish remaining account balances or resets.

Receipt/manual-only tracking is simpler and avoids account-specific collection,
but leaves routing dependent on manual updates and does not grow automatic
provider coverage. Automatic integration can keep supported sources current,
but requires provider-specific collection, compatibility tests and explicit
handling of unavailable or stale information.

A hard completion-time acceptance threshold makes the speed trade-off explicit,
but can reject useful local execution solely because it takes longer. Recording
time without that threshold preserves the evidence for owner judgment while
allowing slower local execution.

## Decision and owner rationale

The owner selected these measurement rules:

- External routes: measure subscription allowance consumed or API spend, as
  applicable to the billing source. Token counts remain supporting diagnostics.
- Local routes: record total input/output tokens across primary and delegated
  work, including failures and retries. Elapsed time is the practical resource
  measurement; reducing local runtime is not itself the objective.
- Record and consider elapsed time for comparisons, but do not use median
  completion time as a hard rejection criterion for migration or delegation.

The owner selected automatic usage/allowance integration over a manual-only
end state. Build supported provider adapters incrementally, case by case where
necessary. The stated rationale is to grow the library of automatically
supported providers.

Preserve the strict per-required-case quality bar in ADR-049. Missing economic
measurements still prevent savings claims. Compare matched tasks using total
primary plus delegated consumption; do not convert tokens into allowance or
money without an applicable billing measurement. Label reported and estimated
values separately, keep unknown values unknown, and expose source and freshness
when collecting account state.

On 2026-10-10 the owner adopted **20% savings as the target** for comparable,
measurable external allowance consumption or API spend. Include primary and
delegated work, failures and retries in both matched totals. For now, results
below the target require case-by-case owner review rather than automatic
rejection. This target does not relax the strict quality/security bar, turn
unknown measurements into zero, or impose a local runtime-reduction gate.

## Boundaries and next implementation slice

Provider-specific collection belongs behind provider/client adapters; neutral
usage-aware selection belongs in the Orchestrator. This direction does not
select a new database, daemon, external service or account access mechanism.
It does not change existing explicit task latency constraints or operational
timeouts; those serve different purposes from migration acceptance.

The numeric savings target was initially absent from the available handoff;
the owner's subsequent 20% target and case-by-case review rule are recorded above.
The first-source choice and its collection contract were also initially pending;
the owner selection and implementation are recorded below.
Preserve existing reactive fallback and receipt diagnostics during later routing
integration work.

On 2026-10-10 the owner selected Codex as the first source because it is their
main source, rather than the recommended Copilot-first transport reuse. The
accepted first slice uses a bounded native app-server account read through the
installed login, normalized snapshots in memory, and no initial routing change.
Codex implements provider-specific collection; the project does not read token
files, introduce credential storage or create model conversations. The native
client retains responsibility for its own authentication and runtime state.

## Consequences and validation

External economic comparisons use the actual billing resource where observable.
Local comparisons expose both tokens and time without imposing a speed gate.
Automatic provider coverage is the intended direction, not a claim of current
support. Each integration needs tests for its collection/parsing boundary,
missing/stale values and routing behavior before it is reported as supported.

The initial ADR recorded direction only. The first source is now implemented as
`ai_provider.codex_usage`: initialize a temporary owned stdio app-server, read
`account/rateLimits/read`, keep separate reported quota windows and observation
time, and clean up the owned process tree. Missing/invalid/unsupported responses
and timeouts remain unknown. The collector writes no snapshots; existing native
client state/logging remains managed by Codex. It does not consume reset credits,
send emails, initiate login or start threads/model turns.

Offline synthetic-client tests exercise protocol admission and actual process
cleanup, including spawned descendants. One authorized live read on 2026-10-10
09:08:32 UTC returned both Codex windows with verified cleanup. This proves that
installed-client read, not every client version or per-task attribution.

The existing execution CLI now automatically reads the supported Codex subscription
source immediately before its first attempt in an execution scope. The engineering
default is one bounded read per source per scope, reusing available or unknown
observations for repairs. Coding chat has one execution scope per owner turn.
Collection consumes the existing continuation deadline and is capped at 15 seconds
or the shorter remaining target timeout. Observations expose source/time and stay
separate from routing/exhaustion and saved handoffs. An explicit CLI transcript log
can capture displayed normalized progress through its existing logging mechanism.
Offline readiness remains offline; no background polling or quota store is added.
This implements the approved automatic, in-memory, observe-only direction; it does
not claim the owner selected a permanent collection cadence or freshness threshold.
The next implemented source is Copilot. Its native headless `account.getQuota`
read retains separate quota types, request counts, remaining percent and reported
reset dates, including the documented unlimited entitlement sentinel. BYOK
overrides remain unknown for subscription economics. The neutral provider-layer
dispatcher selects only supported access/billing-source pairs; API billing and
workspace credits are not inferred from subscription quota. Shared native process
ownership/deadline/cleanup code serves both protocol adapters. One configured-client
read on 2026-10-10 10:13:37 UTC returned three quota types with verified cleanup.
No new dependency, login mechanism, collector store or routing policy was added.
See [GitHub account quota](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing#account-quota-and-premium-interactions).

On 2026-10-10 the owner approved bounded isolated native-session quota diagnostics
for Kiro and Antigravity, following the recommendation to investigate automatic
coverage where no standalone account RPC was identified. Native clients may save
their ordinary session state. This expands the initial no-session investigation
boundary only: exclude repository content, tools, hooks and model turns; introduce
no login, credential discovery or new permission grants. Prove isolation before
running diagnostics and retain unsupported/unknown results when it cannot be
established. Approval is not evidence that either collector works and does not
change the execution or routing approval boundary.

Quota-aware routing, remaining provider readers and paired consumption measurements
remain subsequent slices. Source reference:
[official app-server rate limits](https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt).

## Isolated Kiro slice and Antigravity limitation

The approved investigation admitted Kiro CLI 2.24.0 with the V2 engine pinned.
Its temporary custom agent has empty tools, trusted tools, resources, hooks and
MCP servers, with `includeMcpJson: false`. A fresh directory outside repository
ancestry prevents project-content discovery; the collector refuses repository
or instruction-bearing temporary ancestors. Process-local `KIRO_NO_AUTO_UPDATE`
disables native updates. The existing native login/state remains client-owned.
Only `/usage` is submitted, with closed stdin and bounded owned cleanup. Other
versions remain unknown until the same isolation contract is established.
See [custom-agent isolation](https://kiro.dev/docs/custom-agents/troubleshooting/),
[MCP profile configuration](https://kiro.dev/docs/custom-agents/configuration-reference/#includemcpjson-field)
and [V2 hook placement](https://kiro.dev/docs/cli/v3/migration-guide/).

The installed output explicitly says `Estimated Usage`. The adapter preserves
plan-covered credits, plan credits, native percentage and reset date, marking
`measurement_kind: native_estimate`. It does not infer a remaining balance,
percentage semantics, reset timezone, price or per-task charge. Additional credit
packs/organization formats remain unknown. The shared automatic observer now
includes this supported Kiro subscription path without changing routing.
One final installed-adapter check at 2026-10-10 11:26:09 UTC reported estimated
50 covered / 50 plan credits, 100%, reset date 2026-11-01, with cleanup verified.
This is historical compatibility evidence, not a certified current balance.

Antigravity 1.3.0 documents print-mode `/usage` without a model turn, but that
does not establish startup isolation. Inspection of the installed binary found
common manager initialization before quota dispatch, including hook loading and
background workers. No Antigravity quota session was launched. Its allowance
remains unknown until a supported account-only path or a provably isolated startup
is established; no global configuration, credentials or permissions were changed.
The [official CLI changelog](https://github.com/google-antigravity/antigravity-cli/blob/main/CHANGELOG.md)
is evidence for no-turn print commands, not proof that no MCP/hook startup occurs.
