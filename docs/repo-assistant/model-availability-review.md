# Model availability review — October 28, 2026

This is a code/contract review, not a fresh provider availability observation.
The owner requested this after the Modal measurement, C6 work and Operator
release preparation. No generation probe, automatic route change, scheduled
monitor, new dependency or service was introduced.

## Existing evidence and its limits

| Source | Existing reader or evidence | What remains unknown |
| --- | --- | --- |
| OpenRouter | `openrouter_endpoints.py` supplies dated `EndpointInventory` records, including provider endpoints and source-reported uptime. | Account entitlement, credit admission and request success; public endpoint health does not prove access for this account. |
| OpenCode Go | `go_source_info.py` supplies dated `ModelInventory` and account-wide allowance windows. | Extra Usage enforcement, per-model remaining balance and a successful coding workflow. A listing and a quota window are separate observations. |
| Codex, Copilot, Kiro | Native account adapters supply bounded account-only quota observations with owned process cleanup. | Whether a particular configured model is recognized and entitled. Executable/auth readiness and a static catalog cannot establish that. |
| Ollama | `ollama_models.py` lists installed/running models; `local_capabilities.py` can inspect an existing runtime without starting it. | Sufficient capacity and usable task quality. Installed and running are different states. |
| Meta | The adapter and static route exist; this session's private model-list observation found the configured model. | A reusable `SourceInfo` collector, current credit headroom and real Responses tool-workflow acceptance. A model list is not billing evidence. |
| Modal runtime | Catalog configuration and retained deployment/measurement receipts. | Current readiness while the owned app is stopped. HTTP health/model probes may start compute and must stay inside an admitted compute window. |

Existing contracts in `ai_provider.source_info` already separate model inventory,
endpoint observations, account allowance and response usage. Reuse these records;
do not create a second provider registry or infer allowance from inventory.

## Bounded correction made during review

The OpenRouter reader previously accepted negative performance or impossible
uptime values, could raise on an enormous integer, and described an entirely
malformed provider list as `no_endpoints_advertised`. It now preserves invalid
numbers as unknown, removes nonfinite numeric prices from JSON-safe observations,
and reports an unusable nonempty list as the existing metadata failure. A truly
empty advertised list retains its existing meaning. Valid rows in a partial list
remain available. These are metadata correctness fixes; routing is unchanged.

## Recommended next implementation slice

Add an on-demand advisory report that joins the existing records by configured
route, retains each observation's source/time/reason, and exposes inventory,
endpoint, entitlement, allowance and workflow evidence separately. For sources
without a supported observation, show unknown. Begin with Go and OpenRouter,
then add source-specific readers behind the same contracts.

Keep that first report advisory. A report is reversible and useful for diagnostics;
making missing/stale metadata block routing could prevent otherwise valid work.
Freshness thresholds and any future routing enforcement require an owner decision.
This review does not establish those thresholds or authorize a routing-policy change.
