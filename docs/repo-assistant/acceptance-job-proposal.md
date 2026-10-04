# D3: accepted fixed acceptance-job contract

**ACCEPTED — offline implementation complete; live acceptance deferred.**
Owner accepted option 1 on 2026-10-04. See [ADR-043](../decisions/ADR-043-fixed-local-native-acceptance-jobs.md)
and the [CLI usage](../repo-coding-assistant.md#fixed-local-acceptance-jobs).
CLI foundation remains INCOMPLETE. This contract does not authorize live work.

## Finding and recommendation

`ai_orchestrator.scheduling.admit_task` already provides explicit-start, planned-only
and deadline admission. `ResearchTaskStore` supplies immutable definitions and
conditional claims in existing SQLite storage. `research_runner` supervises worker
trees, but finalizes research-specific stages; it is not a generic job supervisor.
Existing `fallback-acceptance.py` and `alternate-agent-acceptance.py` use broader
live grants and are unsuitable as unrestricted scheduler command payloads.

Recommend an initial **local native coding acceptance job only**, using existing
time admission, an additive acceptance table in the existing application database,
and a fixed project-owned harness. Keep research tables/workers unchanged. Implement
and test offline after approval; live execution needs a separately selected window.
Hosted overload/fallback jobs follow only after scoped client mutation and receipt
contracts are ready. Tool-free negative admission checks belong in ordinary tests.

## Accepted v1 definition

Reject unknown fields, unsupported revisions and invalid types before claiming work.
The definition is immutable; results and process receipts are separate records.

| Field | Contract |
| --- | --- |
| `schema_version` | Exactly `1` |
| `task_id` | Nonempty opaque ID; hashed for artifact paths, never used as a path segment |
| `job_kind` | Exactly `native_coding_tools_v1`; resolves a built-in harness, not an import path |
| `harness_revision` | Exactly `1`; mismatch refuses pending re-planning |
| `repo_root` | Existing absolute project root for catalog/artifacts; the built-in harness and interpreter come from the running project environment; the model receives only generated fixture content |
| `route_id`, `model` | Explicit catalog local-runtime Ollama route and model; no silent substitution, fallback or automatic model downloads |
| `runtime_version`, `model_digest`, `native_contract_version` | Pinned expected compatibility identity; must match installed metadata and positive evidence |
| `runtime_base_url` | Explicit credential-free loopback HTTP URL; must be unused before this job starts its exclusively owned runtime |
| `required_seconds` | Required finite positive allocation, including startup, requests, validation, cleanup and handoff |
| `request_timeout_seconds` | Finite positive timeout, clamped to remaining active time |
| `context_tokens` | Explicit positive integer, capped by declared model window; sent as runtime context |
| `output_tokens` | Positive integer reserved by admission and enforced by the request generation limit |
| `max_iterations` | Positive integer with harness v1 ceiling `4` |

Example bounded planning values: 300 seconds total, 60 seconds/request, 8192 context,
512 output tokens, four iterations. These are examples, not selected owner settings.
V1 fixes `local_only` privacy/cost and fixture-scoped `workspace_write` approval.
No shell, process, delegation, search or external tools are exposed to the model.
Definitions cannot supply prompts, shell commands, executables, environment values,
credentials, arbitrary CLI flags, plugins, external client/account routes or callbacks.

## Fixed fixture and acceptance

The harness creates a fresh directory under ignored `artifacts/acceptance-jobs/`
with fixed instructions, a small deliberately broken Python function and immutable
tests. The model may read fixture files and edit the one designated source file.
Enforce that path at the tool boundary, including outside-root/symlink refusal;
do not rely on prompt instructions alone. Reuse existing `BaseTool`, registry and
permission contracts, following the existing target-only research writer approach.

The host runs fixed baseline/postchange tests with the project-selected interpreter
and verifies instructions/test/other-file digests. The model cannot pick a command.
Success requires actual read/edit receipts, correct source behavior, unchanged
protected files, completed validation, cleanup and a durable final result. An exit
zero, authenticated runtime, textual tool request or model's success claim is
insufficient. Record estimated admission separately from provider-reported usage;
do not infer verified token capacity or comparative model quality.

## Lifecycle, storage and deadline

- Add `scheduled_acceptance_tasks` and acceptance result/process receipt records
  to the existing SQLite database. Version their payloads explicitly. Preserve
  existing research definitions, statuses, reports and interrupted-run receipts;
  do not migrate research rows into a generalized job schema in v1.
- Planning validates and stores a definition without creating fixtures, launching
  processes, contacting metadata endpoints or performing inference. Execution
  requires explicit selected IDs and an owner-selected finite window.
- Reuse planned/running/completed/failed/deferred states and conditional claims.
  Only planned jobs start. Selection remains sequential and stops on failure or
  insufficient allocation; never reorder, shorten or replay a terminal job.
- Reserve the final 15 seconds of each allocation for bounded cleanup/handoff.
  Startup, every request, validation and cleanup share the overall monotonic deadline.
  A remaining budget too small for the next operation stops work and records failure.
- Launch only the fixed worker, fixed validator and existing Ollama executable in
  hidden foreground-owned processes. Require the selected loopback port unused;
  never borrow or stop an independently started server. Record process identity
  before model work and check ownership before stopping it. No daemon/service install.
- The supervisor must stop the owned worker/validator trees and owned runtime on
  completion, timeout, interruption and startup failure, then verify exit and listener
  absence. If ownership or cleanup is uncertain, record failure and stop the sequence;
  do not kill a matching process name or claim successful backend cancellation.
- Restart leaves interrupted jobs for explicit reconciliation. No automatic resume,
  inherited mutation approvals or replay of uncertain effects. Re-running requires
  a new definition after inspecting the preserved result.

Receipts retain UTC timestamps, definition/harness/runtime identities, stage statuses,
bounded diagnostics, synthetic tool/effect receipts, usage source, exit codes,
deadline/cleanup observations and an imperative next action. Credentials and private
reasoning are excluded. Retain artifacts/records until explicit deletion.

## Alternatives and owner decision

1. **Recommended: local v1, additive tables, exclusively owned runtime.** Small
   initial execution boundary and verifiable cleanup; requires an unused selected
   local endpoint and additional owned-runtime supervision. Hosted acceptance waits.
2. Generalize research definitions and add hosted acceptance now. Broader coverage,
   but a larger persisted migration, client permission/account/privacy contract and
   cancellation surface. Current mutation parity gaps make this higher risk.
3. Keep scheduling research-only and run other acceptance manually in selected
   windows. Lowest implementation cost, but retains manual supervision.

Owner selected option 1. Offline implementation includes strict v1 payloads,
additive SQLite tables, the fixed fixture and retained Windows process-tree cleanup.
Unsupported platforms refuse before starting a runtime. The validator restricts
source syntax to a single pure arithmetic function rather than executing arbitrary
model-authored code. Receipts flush during work and survive worker interruption.
No executable acceptance queue entry or live run was created in this session.
