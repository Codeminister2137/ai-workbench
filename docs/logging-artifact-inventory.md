# Logging and artifact inventory

This is a bounded source review from 2026-10-14, supporting the
[logging review plan](logging-and-artifact-structure-plan.md). Paths below describe
existing behavior; they are not a selected replacement layout or retention policy.
No existing files, databases or references were moved or deleted during review.

## Writers, readers and purposes

| Surface | Existing location and writer | Reader and purpose | Observed limitation |
| --- | --- | --- | --- |
| CLI console transcript | Explicit `--log-file`; `repo_coding_assistant.main` opens it and `TeeOutput` mirrors stdout | Owner and investigation scripts read the console transcript | Opening the same path uses write mode and replaces its prior transcript; stderr is retained only when the caller explicitly prints or captures it |
| Exact model-input logging | `--log-full-prompt` requires a log file; `transcripts.print_model_input` / `print_external_agent_input` | Explicit evaluation/debugging | Generated model-input logging is opt-in; ordinary invocation headers already contain the owner's request and argv |
| External CLI event stream | Raw JSONL is written to an active transcript by `_write_external_agent_raw_jsonl` | Parser reports normalized results separately; raw transcript supports debugging | Event contents are opaque client output, not a verified safe-field projection; retention/redaction policy needs review before broader use |
| Plain chat | Default `data/repo-assistant-chats.sqlite3`, optional `--chat-db`; `SQLiteChatTranscriptStore` | Chat controller lists messages and rolling summaries for continuation | Durable conversation state, not disposable log output; its path must remain compatible |
| Coding conversation and ownership | Same default chat database, optional `--coding-session-db`; `CodingChatController`, `CodingSession`, process ownership store | Resume/reconcile commands, complete history and host outcomes | Multiple tables with different purposes share one database; operation receipts omit arguments/output and retain hashes/status |
| Orchestrated run state | Default `data/repo-assistant-runs.sqlite3`; `SQLiteOrchestratedRunStore` | Run/resume/status and research scheduler | Run state and research definitions are persistent contracts, not a folder-cleanup opportunity |
| Fixed local acceptance jobs | Configured job database; `AcceptanceJobStore`; `artifacts/acceptance-jobs/<identity hash>/` via `acceptance_runtime` | Runner reads immutable definition and worker result; owner reviews `result.json` | Hash directories preserve identity but need human task labels; result, receipts, logs and fixture are mixed at one level |
| Scheduled public research | `artifacts/scheduled-research/<identity hash>/`; `task_scheduler` builds report/log paths; acceptance tasks use an isolated worker `runs.sqlite3`, ordinary research uses the configured database | Completion checks read run state and `report.md` | Database identity participates in the hash; moving a database changes derived paths, so migration cannot be assumed transparent |
| Ad hoc public research | `scripts/repo-assistant-research.ps1` creates `artifacts/research-<topic>-<timestamp>/` defaults for `report.md`, `assistant.log`, `ollama.log` | Owner reads report; validators read report and fetch/write evidence | Timestamp/topic labels are more readable than hashes, but timestamps alone are not task identity or completion proof |
| Fallback stop handoff | `artifacts/fallback-handoffs/<uuid>.json`; `_save_fallback_handoff` writes a new metadata-only receipt | Owner reconciles partial work before continuation | No obvious latest entry point; bounded git status can be truncated and is explicitly marked |
| Council conversation | Default cwd-relative `data/council.sqlite3`; `ConversationStore` | Council reads ordered conversation messages/member/model metadata | Different working directories can produce different databases; this does not authorize relocating them |
| Recruiter outreach history | Configured `SENT_FILE`, default `sent_emails.txt`; `outreach_cli` appends after successful delivery | `_load_sent_emails` avoids repeated recipient handling | This is private operational state, not general logging; no outreach was sent during this review |
| Openings bridge | `openings_import` normalizes caller-supplied export rows; `openings_api` returns read-only pages | Job-search caller consumes typed vacancies | Inspected bridge owns no new file/database writer; export transport and the Openings app remain separate |
| Local handoff and reusable instructions | Ignored root `CURRENT_CONTEXT.md`; tracked `docs/prompt-library.md` | Owner and next coding session | Artifact-specific prompts are historical evidence, not an alternate active handoff |

The provider-neutral `ai_orchestrator` planning package loads catalogs and produces
neutral plans; inspected persistence/execution belongs to its optional provider
integration. Moving writers into the planning package would change that boundary.
Provider adapters themselves do not create run directories in the inspected paths.

## Concrete readability problems

An acceptance directory's `result.json` contains useful status and cleanup, but
its hash name does not communicate the task. A console log can be successful at
connection or planning while later acceptance fails. Separate fixture, scripts,
normal reports, databases and diagnostics must remain distinguishable; filename
suffix or presence alone cannot establish authorship, completion or quality.

Transcript write mode can destroy a prior transcript when a caller reuses its
path. Changing that behavior to append or refuse is a compatibility decision,
because callers may intentionally overwrite. No change was made. Private chat
and operational databases also need explicit retention decisions, independent
from generated diagnostic logs. Raw external JSONL needs a field-level retention
review; this inventory did not inspect private contents or claim redaction.

## Initial error-propagation source trace — 2026-10-17 (historical)

This started the wider owner-requested review. It is source evidence, not a complete
failure-injection audit or a selected public error schema. Existing logs can still
identify some providers by their message text; the finding below is about which
structured facts cross each boundary, not a claim that every error is opaque.

| Boundary | Current evidence | Review finding / next check |
| --- | --- | --- |
| Ollama HTTP to provider exception | `adapters/ollama.py` wraps HTTP failures with provider, category, retryable flag, original exception and exception chaining; message includes provider/status | Reported server error detail is not in the normalized message. Test safe body-detail preservation and closure without leaking echoed prompts or reasoning. The private pilot's bounded diagnostics are not a production-wide repair. |
| Provider exception to agent loop | `ai_agent/loop.py` attaches transient partial messages and re-raises the same `ProviderError` | Cause/provider metadata remain available here. Verify this invariant across composed native/fallback paths and keep transient continuation out of durable diagnostics. |
| Native execution failure to CLI closeout | `repo_coding_assistant.py` catches `ProviderError` and passes `str(exc)` as `failure_reason`; orchestrated stage details also receive this string and available fallback details | Structured exception metadata is not passed through this closeout parameter. Check effective route/service attribution, including fallback, rather than assuming the initially printed plan identifies the failing service. |
| CLI closeout to coding-chat history | `coding_chat.py` stores failure reason/status/return code and optional route/fallback attempts from `CodingTurnResult` | Do not dump raw exceptions into persisted history. Determine the smallest safe attribution/cause information needed; a material contract or persisted-format change needs owner selection before implementation. |
| Foreground child process to status | `processes.py` returns process handle/PID, status, return code, bounded output and truncation markers | Useful process evidence already exists. Verify callers preserve it and distinguish a worker failure, failed tool command and later cleanup failure. |
| External client diagnostics | `external_reporting.py` separately reports event failure and hints, and suppresses command arguments in timeout reasons | Verify partial output, parser failures and external-service attribution across client-specific wrappers; bounded text alone is not proof of field-level redaction. |

Next bounded review: deterministic failure injection through provider/native/CLI/
coding-chat boundaries, identifying what is safely retained and what requires a
contract decision. Preserve existing public categories, fallback/privacy rules,
storage paths and historical artifacts while investigating. This review does not
approve a new schema, logging service, raw-prompt capture or broad refactor.

The first targeted local injection confirmed the agent-to-closeout gap: two
synthetic `ProviderError` instances with identical generic messages and different
provider identities retain their exception identity, chained cause, provider,
category and retryability through the real agent loop, but yield identical CLI
closeouts when route/fallback details are absent. The observed `CodingTurnResult`
contains the failure string and no provider/category fields. This used real loop/
closeout code with injected clients and an empty fallback-details fixture; it is
not an end-to-end routing or service failure test. Provider-specific message text
or effective-route metadata can still identify services in other cases.

The terminal turn runner replaces the closeout observer's placeholder return code
with the actual execution return code, so the placeholder alone is not a confirmed
status-propagation defect. Existing loop/closeout/coding-chat checks pass (74 tests).

## Verified CLI error attribution — 2026-10-18

The resumption audit corrected the earlier composed-trace claim: the private
`trace_errors.py` calls AgentLoop in a separate case, but does not invoke native
execution wrappers in its named native/chat case. It connects synthetic
FallbackSession callbacks to closeout/chat and does not reopen SQLite. Its edited
version also contains a mismatched result key; its historical JSON receipt cannot
validate later edits. Preserve that evidence without treating it as native
integration acceptance.

The owner subsequently selected optional structured diagnostics and readable
terminal attribution, with a bounded safe handoff projection. See
[ADR-060](decisions/ADR-060-structured-cli-error-attribution.md). This supersedes
the historical native-to-closeout/chat gaps in the table above for the covered
ProviderError catch paths. It does not complete the wider error review.

- CLI failure summaries now show the caught error's provider/category/cause_kind;
  absent values are unknown. Effective route is separate and is not evidence of
  the reporting provider or underlying service cause.
- CodingTurnResult and existing transcript JSON metadata retain these optional
  identifiers and a handoff projection. Only recognized status/reason/failure_kind/
  quality_policy and a bounded failed_route_id survive. Observations, objectives,
  raw causes, save-error text and arbitrary keys are excluded. History reprojects
  older experimental records before sending the new metadata to subsequent turns.
- No SQL schema migration is required for additive JSON keys. Existing records
  without new fields remain readable; provider categories/routing are unchanged.
- `tests/repo_assistant/test_error_propagation.py` exercises the actual CLI,
  native wrappers, AgentLoop, FallbackSession, terminal observer/return code and
  reopened SQLite. Transport/client admission/readiness are synthetic. Cases:
  direct failure, overload then secondary timeout, exhaustion, unknown attribution
  and successful recovery. Separate checks cover privacy sentinels, bounds and
  older records; `test_cli_basics.py` covers the ordinary request catch path.

Limits: cause_kind is a type, not a root-cause diagnosis. Existing failure_reason
text is unchanged. Earlier fallback attempts retain route/status, not a complete
chain of their causes. Provider-body diagnostics, tools/workers/scrutiny paths
remain wider-review work. The discarded historical HTTP500 body remains unknown;
no inference, live-service or model-quality acceptance follows from these tests.

## Layout proposal for owner review

Recommendation: retain current roots and durable database paths. First add a
human-readable entry point to a representative existing run, keeping its current
diagnostics and fixture paths. This improves navigation with fewer broken readers
and historical links. Its cost is that existing filename conventions remain mixed
until producers can be aligned in small approved slices.

Alternative: migrate all producers to a common `artifacts/runs/<label>/` layout
with separate report/diagnostic/fixture directories. This offers stronger uniformity,
but needs configuration, derived-hash path, script, reader and historical-link
migration plus an explicit policy for private databases. It would cost more and
creates avoidable compatibility risk before a representative layout is accepted.

A reviewable first example could retain an existing acceptance directory:

```text
artifacts/acceptance-jobs/<existing identity>/
  README.md           task label, outcome, actual effects, checks, limits, next action
  result.json         existing structured runner result, unchanged contract
  worker-result.json  existing model/effect observations
  runtime.log         existing runtime diagnostics
  worker.log          existing worker diagnostics
  fixture/            preserved synthetic inputs and effects
```

The README and a latest-run link are proposals, not implemented conventions.
Do not add another status database or infer permission for historical migration.
The owner must select the convention and any path/retention changes before rollout.

## Review limits and next slice

The 2026-10-15 follow-up prepared browseable failed/passed CLI examples and a
per-file metadata inventory in the local unattended-window evidence. The failed
example separates an unapplied edit and safety stop from source correctness; the
passed example labels simulated exhaustion and actual fallback effects. Original
paths, databases and historical receipts remain unchanged. Owner selection of the
entry-point/latest-run convention and separate reuse/retention policies is still
required before producer rollout; the active handoff links the concrete examples.

This inventory covers the main current writers/readers, not every example,
private pilot script, sidecar, model-download log or consumer. Next: obtain the
owner's layout choice using the prepared examples and their file/reader inventory.
Separately resolve transcript path-reuse behavior and external raw-event retention; neither
is silently changed by a readability review.
