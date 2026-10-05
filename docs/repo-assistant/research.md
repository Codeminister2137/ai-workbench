# Public research tools, evidence and acceptance

[CLI guide](../repo-coding-assistant.md) · [Privacy and permissions](permissions.md)

## Research tool profile

`scripts/repo-assistant-research.ps1` selects `--tool-profile research` and
`--research-report PATH` for local provider-native orchestrated implementation.
The profile exposes only `fetch_url`, `read_research_report`, and
`write_research_report`; shell, generic editing, and delegation are unavailable.
The wrapper allows 40 native tool rounds per attempt and a 300-second request
timeout. Research requires a loopback Ollama server and an installed model whose
runtime and catalog both support tools. A model's availability does not establish
quality. The wrapper defaults to `gpt-oss:20b`, which passed the earlier local
native-tool plumbing acceptance. `-Model` can override it; catalog routing and
the installed runtime's tool capability must both pass preflight before auxiliary
inference or primary research starts. A rejected primary records a failed handoff
and skips auxiliary work, repair, and scrutiny.

Research requests use a 32,768-token context unless an explicit `--ollama-profile`
selects another size. Older tool excerpts/report drafts are compacted when the
serialized history grows beyond a byte guard; task instructions, receipts, tool
identifiers, and the latest exchange are preserved. This is an approximate size
guard, not a tokenizer guarantee. The model can refetch sources or read its report.
Transient provider response errors retry at most twice, without replaying tools.
Progress is flushed to the UTF-8 transcript throughout execution.

`read_research_report` returns at most 20,000 characters per page. A longer
report includes a continuation instruction with the next `offset`; read every
page before replacing the complete report. Offsets count characters, with line
endings normalized as in ordinary text reads. Result metadata includes the full
file's byte digest, page bounds and next offset, allowing callers to recognize a
changed report between reads. Reads and writes share a 1 MB file bound; externally
enlarged reports fail explicitly rather than silently losing their tail.

After structural repair succeeds, `ai_provider.research_refinement` repeatedly
reviews the configured report, sends findings to the tool-capable primary agent,
and validates each revision. A reviewer pass does not end improvement by itself.
Structural repair also receives the saved report and actual receipts, with
instructions to preserve correct content and source grounding while correcting
mandatory validation failures. Length alone never triggers structural repair.
The controller shares `--max-repair-cycles` with structural repairs (`-1` is
budget-bounded), reserves ten percent of the budget (at most two minutes) for
final review/handoff, and stops on errors or two consecutive attempts without
changed report bytes or new source URL/content-digest evidence. Identical
rewrites and repeated fetches with new timestamps do not count as progress.
Changed bytes or source digests do not establish semantic improvement; superficial
revisions can therefore continue until another guard or the budget stops the run.
It attempts improvement throughout the available budget rather than sleeping
to fill the requested duration.
The supervisor remains the hard elapsed-time guard for blocking calls; scheduling
and request bounds cannot guarantee that a blocked attempt leaves its reserve.
Research attempts also check an absolute deadline before every model turn/retry
and clamp each request timeout to the remaining attempt allocation. The initial
attempt leaves the review reserve; subsequent attempts use their repair allocation.
Refinement attempts and their preceding review findings persist under the
existing repair stage's `research_refinement` metadata, including in-flight state.

Research scrutiny receives the configured report excerpt and actual current-run
fetch receipts, without unrelated workspace files. Report/excerpt truncation is
explicit. Auxiliary reviewers have no retrieval tools: their URLs, dates, and
suggestions never become fetch receipts. Review still cannot establish claim
entailment without independently retrieved source bodies, so a pass is not a
factual-quality certificate.

Fetching uses existing CUSTOM permissions: `trusted_local` allows,
`read_only` denies, and `interactive`/`workspace_write` ask. Writes use WRITE
permissions. The profile requires `--privacy local_only --cost-policy local_only`
and rejects legacy actions, context delegation, outside-workspace files, skipped
validation, and external executors/fallback. Coding remains the default profile.

Public HTTP(S) GETs validate every DNS result and redirect destination, connect
to the validated address, and verify TLS. No credentials, cookies, ambient
proxies, or custom headers are supplied. Requested sites receive URLs/query
strings and ordinary request metadata; bounded source excerpts go to the local
model. Ports 80/443, text/JSON/XHTML, five redirects, 512 KB retained bytes,
12,000 returned text characters, and 40 links are supported. PDF, compressed,
authenticated, and JavaScript-rendered sources are unsupported. Report writes
are limited to the configured workspace Markdown target and 1 MB per write.

The built-in deterministic gate reads the report locally without network or
AI calls. Every report write returns actionable completion-check feedback to the
model, and the final gate runs again before review and handoff.
It requires all eight report sections promised by the wrapper and nonempty
section content. Headings and source declarations inside code examples or HTML
comments do not count as evidence or toward the advisory length guideline.
Here, "visible" means report text after removing HTML comments, fenced code
blocks, and horizontal rules, then trimming outer whitespace; it is not a rendered
Markdown character count. The 7,000-character guideline is advisory: tool feedback
and the standalone validator suggest reviewing substantive coverage below it,
but length alone never fails completion or forces repair. Do not add filler.
It is a completeness heuristic, not a factual-quality measurement. The standalone
validator's `--min-chars N` customizes its advisory guideline; both validation paths
enforce mandatory section, source, and receipt checks independently of length.

Research exposes `search_web` with free-only Tavily, Brave, and SearXNG fallback
(ADR-036). Standard `--search-provider auto` tries eligible routes in that order;
missing credentials and setup requirements are recorded as skipped. The successful
route persists through repairs. Each provider is tried at most once per query;
quota/auth failures disable it for the run. Genuine empty results do not trigger
fallback. `--no-search-fallback` or `[fallback] enabled=false` disables switching.
Full submitted queries, skips/failures, provider, UTC time, response digest when
available, and discovered URLs persist in `search_receipts`. These records and
snippets cannot substitute for fetching linked sources with `fetch_url`.
Research search options cannot be applied to the coding profile; incompatible
options fail before execution rather than silently ignoring a tracking preference.

`--search-privacy reduced_tracking` (wrapper `-SearchPrivacy reduced_tracking`)
restricts discovery to SearXNG, including on failure. Its default endpoint is
`https://search.mectov.my.id/search`, configurable via `--searxng-endpoint`.
Public SearXNG reduces upstream identity tracking but its operator still receives
query text and IP. `--search-privacy disabled` or `--search-provider none` removes
discovery; explicit source fetching remains available. Search preferences are
independent of local-only inference. Never submit secrets or private workspace
content to any search provider.

Set `TAVILY_API_KEY` for a free Researcher account. Usage is checked before every
Basic query; unknown/paid plans, pay-as-you-go allowances, and exhausted credits
are rejected. No provider-generated answers or raw extraction are requested.
For Brave, set `BRAVE_SEARCH_API_KEY` only alongside confirmed account setup:
`BRAVE_SEARCH_FREE_ONLY_CONFIRMED=1` means zero paid monthly usage allowance and
auto-reload disabled; `BRAVE_SEARCH_STORAGE_ALLOWED=1` means the account permits
saving returned data in transcripts. The standard Brave API terms restrict result
retention; do not set this confirmation without applicable rights. The API cannot
verify these declarations. Unconfigured Brave is skipped, not charged.
See [Brave's billing and retention FAQ](https://api-dashboard.search.brave.com/documentation/resources/help-feedback).
The research wrapper loads an existing ignored `.env` through uv; direct Python
invocations use process environment. Keys never appear in receipts or tool output.

The source map accepts Markdown tables, numbered lists, bullets with continuation lines, source
subsections, or separate prose entries. Declare an HTTP(S) URL for each source,
retrieval as `fetched` or `not fetched`, and an ISO `YYYY-MM-DD` access date for
fetched sources. Dates must exist on the calendar and cannot be in the future.
Sources not fetched may state `not accessed` instead of inventing a date.
Optional source IDs use unique `S1`, `S2`, etc.; cite these as `[S1]`, or cite the
declared URL directly. For example:

```markdown
| ID | URL | Accessed | Retrieval |
| --- | --- | --- | --- |
| S1 | https://provider.example/docs | YYYY-MM-DD | fetched |
```

Replace the example URL/date with actual source metadata. Candidate facts use
`verified`, `inferred`, `unknown`, or `stale-risk` labels. Each candidate entry
must cite a declared source unless it is explicitly `unknown`; `verified`
requires a supporting source declared fetched. The verifier checks each candidate
table row, numbered/bulleted list entry, subsection, or prose entry and rejects unresolved
source IDs and URLs cited outside the source map. The risks section must state
unknowns or uncertainties explicitly, including when none remain.

The built-in gate additionally checks every claimed fetched URL/access date
against successful fetch receipts from this run and requires the current report
digest to match a report-write receipt. Receipts persist immediately in existing
implementation-stage SQLite metadata and survive provider failure and repairs.
They contain URLs, time, status, byte digest/length/truncation, and report-write
metadata, rather than fetched page bodies. Retrieval evidence does not establish
source authority, citation entailment, factual truth, or model quality.
Use `--research-max-sources N` (wrapper `-MaxSources N`) for a tool-enforced per-run
maximum. It is unset by default. Distinct successfully fetched final URLs count;
failed requests and repeated reads do not consume new slots. Redirect aliases
resolve before enforcement; at capacity a new final URL is rejected before its
body is read. Resolving redirects can still make HTTP requests, so this is not a
network-request maximum. The same policy/accounting applies across repairs and
refinements. Natural-language limits alone remain model instructions.

Local reviews also receive bounded in-memory source excerpts matched to their
latest receipts. The latest thirty sources retain at most 12,000 UTF-8 bytes each;
review text shares a balanced budget of up to 16,000 bytes, redistributing space
left by short sources. JSON escaping and framing can reduce this budget to fit
the existing request-byte bound without shrinking the report/receipt windows.
Extraction/body truncation, omitted URLs, and unavailable text are
explicit. HTML scripts/styles are excluded by the existing extractor. Excerpts
are untrusted source data, and missing coverage cannot establish falsity. Findings
remain advisory and guide refinement; there is no new semantic completion gate.
Existing review outcomes and structural/receipt checks retain their behavior.

No new source-body persistence is added. Excerpts disappear when the run object
or process ends; receipts do not reconstruct text. Existing logs print bounded
tool-result previews and model replies, while review findings persist in stage
metadata. These existing outputs can contain model-selected quotations; memory-only
retention does not promise quotation-free logs or reports. Reviewer prompts and
the excerpt cache are not newly saved. See ADR-037 for the accepted boundary.

Standalone `scripts/validate_research_report.py PATH` checks structure and
declarations only. Add `--run-db PATH --run-id ID` to check current-run receipts
as well. Failed checks produce repair diagnostics; unsuccessful executed research
runs return nonzero. Honest not-fetched/unknown entries remain accepted.
The PowerShell wrapper runs a foreground supervisor that enforces `-AwayMinutes`
across startup, model/tool calls, validation, repair, and review. At the deadline
it stops its worker and owned descendants, preserves the saved report and receipts,
and records a timeout handoff in the existing database. Timeout returns exit code
124; other failures remain nonzero. An independently running Ollama server stays
running. This guarantee applies to the wrapper / `ai_provider.research_runner`,
not direct `ai-assistant` invocations or general coding runs. Keep the PC awake
for the desired run duration.

If the worker exits unexpectedly before durable finalization, the supervisor
marks its unfinished stages/run as failed, skips unstarted stages, and records a
failure handoff and transcript marker. Saved report bytes and receipts survive.
A zero worker exit cannot count as success while the recorded run is unfinished.
An existing terminal handoff is preserved. Interrupting the supervisor stops its
worker and records failure rather than claiming a budget timeout. If no run was
created, the supervisor does not invent a database or run record.
If review fails before another artifact change, the controller preserves that
failure and stops refinement; it does not repeat the same failed review as a
final pass. A structurally valid saved report can still have a failed overall run
when its model review did not complete.

From the repository root, with `uv` available and the model installed:

```powershell
.\scripts\repo-assistant-research.ps1 `
  -Model gpt-oss:20b -AwayMinutes 110 -Topic model_catalog_metrics `
  -SourceUrl 'https://docs.ollama.com/capabilities/tool-calling','https://docs.ollama.com/capabilities/thinking' `
  -Request 'Research model catalog capabilities and useful comparison metrics. Follow relevant primary-source links, distinguish verified facts from inference and unknowns, and propose the smallest useful catalog update.'
```

`-SourceUrl` supplies starting pages; the model can discover sources with
`search_web` and follow fetched links. `-SearchProvider` selects the primary
(`auto`, `tavily`, `brave`, `searxng`, `none`); tracking preference uses `-SearchPrivacy`.
The wrapper prints its report path, transcript path, and run ID. Default outputs
are grouped under ignored `artifacts/research-<topic>-<timestamp>/`: `report.md`,
`assistant.log`, `ollama.log`, and the run's `runs.sqlite3`. Custom report/log paths
remain supported. Shared chat/run state stays in `data/` when a per-run database
is not explicitly selected. The general launcher also groups transcript and
Ollama logs under `artifacts/repo-assistant-<timestamp>/`.
The wrapper uses local inference and does not require loading cloud credentials.

Acceptance scripts preserve their synthetic workspaces and results under
`artifacts/<acceptance-run>/`; these directories contain fixture source/tests,
configuration, and result metadata as well as logs. They are generated evidence,
not application source or accepted architecture. Historical files were moved with
a manifest and database backups under `artifacts/artifact-migration-20261002-165323/`.
Original report-write receipts remain unchanged. Recorded `report_relocations`
map original paths to moved reports with the same digest; receipt validation
requires both that mapping and the original matching write receipt. Historical
transcripts retain their original paths. One open legacy `logs/ollama-serve.log`
remains until its running Ollama process releases it; no server was stopped.

An opt-in plumbing acceptance run is available:

```powershell
uv run python scripts/research-acceptance.py --model gpt-oss:20b --away-minutes 10
```

Acceptance additionally requires at least one executed refinement after structural
validation. Increase `--away-minutes` when local reviewer/model latency prevents
that sequence fitting the budget. This remains a two-source plumbing check.

Use `--plan` to inspect a future acceptance without starting Ollama, calling
providers, reading tokenizer assets, or creating artifact directories/run records.
Reviewer flags share the research CLI's policy and bounded-setting validation.
The short-run defaults remain legacy review, ten minutes, and three repair cycles.
For the approved sustained acceptance, plan the explicit reviewer/tokenizer settings
and use `--max-repair-cycles -1` to permit refinement within the full time budget:

```powershell
uv run --no-sync python scripts/research-acceptance.py --plan `
  --model gpt-oss:20b --away-minutes 110 --max-repair-cycles -1 `
  --research-review-policy quality_first --research-review-model qwen3:14b `
  --research-review-mode deliberative `
  --research-review-tokenizer-file C:\path\to\qwen-tokenizer.json
```

This emits `PLANNED` JSON with prospective paths and worker arguments, including
the unchanged public research prompt. It validates configuration, not installed
model compatibility or tokenizer availability. Run paths are regenerated at execution.
Keep this long run planned while PC resources are unavailable. A later explicit
start requires the complete 110-minute allocation plus separate handoff time;
do not reduce its budget to fit. Execution uses the installed optional
`research-token-count` dependency group for verified token counting; incompatible
or missing assets retain conservative admission.

It fetches two official pages, writes a report, and checks persisted receipts.
A successful short run establishes usable execution plumbing, not model quality
or success on arbitrary requests. The representative comparison is now audited.
A fully allocated 110-minute acceptance was explicitly started on October 3 but
stopped early on conservative review admission after saving a structurally valid
report. No refinement occurred; sustained acceptance remains incomplete.

Every run prints an `execution_status` line. It distinguishes planned runs,
completed responses, completed runs with tool/action errors, and failed
orchestration. A response is not reported as a fully successful implementation
when an approved tool or action returned an error.

`--scrutinize-response` is an opt-in second provider call for `ask` or `review`.
It evaluates the completed answer against the original request and repository
context, then prints a structured verdict, score, issues, recommended next
action, and revised response. It uses a derived local-only child task profile by
default, so scrutiny does not silently reuse an expensive or allowance-backed
primary route. It does not edit files or execute actions. The
CLI parses and validates Markdown-compatible report headings with the required
labels, including case and underscore/space variants for known labels, or a JSON
object with the same required keys, before marking scrutiny as completed. It
emits normalized `scrutiny_verdict` and `scrutiny_score` lines for log
inspection. A malformed scrutiny report is reported as
`scrutiny_status: invalid`; a non-pass verdict leaves the primary answer intact
but marks the run as
`execution_status: completed_with_scrutiny_findings`. The additional report is
included in the same `--log-file` transcript, so this is the recommended
broad-repository response-quality command.

The same policy applies to future auxiliary calls: context extraction,
summarization, prompt refinement, test-case generation, and response critique
should prefer local or cheaper models unless the task is important enough to
justify an explicit stronger route. Primary model routing remains governed by
the task profile, privacy class, quality threshold, selected route, and
cost-policy tier.

For repeated manual live acceptance checks, use
`scripts\repo-assistant-broad-analysis.ps1`. This is not a unit test: it makes
two real provider calls and the final answer remains subject to human
evaluation. The script is the canonical, evolvable version of the command; its
default prompt, provider/model, timestamped transcript/runtime logs, full-prompt
evaluation capture, and quality flags are kept together.
Pass `-Prompt`, `-Model`, `-LogFile`, or `-OllamaLogFile` when a test needs a
different value without duplicating the workflow:

```powershell
.\scripts\repo-assistant-broad-analysis.ps1 `
  -Prompt "Review the latest provider change and identify the smallest next milestone." `
  -LogFile logs\provider-change-analysis.log
```

When adding a CLI feature that should be part of the standard broad-analysis
workflow, update `scripts\repo-assistant-broad-analysis.ps1` rather than
creating a separate one-off command. Keep this runbook synchronized with that
script; `CURRENT_CONTEXT.md` may point here as a short handoff, but it is not
the durable source of the command.

Executed implementation-mode provider routes use the provider-native
tool-calling loop by default:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --mode implement --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

Native mode uses the shared `ai_provider` tool-call contract and
`ai_agent.AgentLoop`. `--native-tools` is still accepted for explicitness and
compatibility. Use `--no-native-tools` to opt into the older text-only provider
response path. Use
`--approval-policy read_only|interactive|workspace_write|trusted_local` to
choose the model-neutral local action policy. The default is `interactive`.

Native coding receives a system prompt for actual provider-native calls. Native
execution rejects an unexecuted JSON tool request returned as plain text, even
after earlier tools ran. Earlier effects remain visible in tool receipts and
must be inspected before continuing. Iteration-limit failures preserve observed
message history and report a non-retryable failure. Text is never promoted to a
native tool call. In orchestrated runs, `--start-ollama` also applies to the
auxiliary review before implementation, using the configured startup command,
timeout, resource profile, and log path.

- `read_only`: allow read/search tools, deny local writes and shell commands.
- `interactive`: allow read/search tools, ask before local writes and shell
  commands.
- `workspace_write`: allow workspace file writes, but deny legacy shell actions
  and continue asking before provider-native shell/custom tools.
- `trusted_local`: allow local read/write/shell tool actions without asking.

When provider-native tools are active, the transcript prints secret-free policy
diagnostics before the assistant response. The diagnostic block includes the
active approval preset, the read/search/write/shell/custom action mapping,
whether interactive approval can be requested, and whether `delegate_task` is
available to the primary agent.

The primary native agent also receives `delegate_task`, a bounded delegation
tool for handing focused support work to a derived local/cheaper child route.
The child agent can inspect files, run the standard coding tools, and write
small code changes when the active approval policy permits writes. Nested
delegation is disabled so runs remain bounded and reviewable. Delegated task
results are returned to the primary agent as a bounded handoff containing child
status, iteration count, tool-result counts, a short tool-result summary, and
the child final response.

For Codex CLI routes, the current local CLI exposes sandbox modes and a
top-level approval flag rather than the full managed ChatGPT approval surface:
`read_only` maps to Codex `--sandbox read-only`, `interactive` and
`workspace_write` map to `--sandbox workspace-write`, and `trusted_local` maps
to Codex `--sandbox danger-full-access`. `interactive` forwards
`--ask-for-approval on-request`; the noninteractive presets forward
`--ask-for-approval never`. Git metadata writes such as `git add` and
`git commit` require `trusted_local`; use `--approval-policy trusted_local`
when the requested external Codex run should stage or commit changes. The CLI
rejects explicit commit-like Codex requests under weaker presets before
contacting the model. `--apply-actions` remains available as the legacy
fenced-JSON action protocol and now uses the same approval policy presets.

That wrapper loads `.env` for the run and starts the Python CLI.

The CLI prints phase headers so metadata and the model response are easy to
scan. To preserve a complete local transcript for later analysis, opt in with
`--log-file`; transcript files may contain the request and repository context,
so keep them local:

External-agent JSONL stdout is summarized in an `=== External agent diagnostics
===` block while the raw JSONL is kept in the transcript only. The final
assistant answer is printed after diagnostics, run status, and metrics so user
summaries do not have raw failures or activity previews appended below them. If
the external agent writes stderr, the console shows a concise stderr summary and
an `external_agent_stderr_file` path for the full filtered stderr. Non-zero
external-agent exits also print an explicit `external_agent_failure_reason`, so
stderr is supporting diagnostic detail rather than the only failure explanation.

```powershell
.\scripts\repo-assistant.ps1 `
  "Review the selected file." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama `
  --log-file logs\repo-assistant-latest.log
```

Logged transcripts start with a `=== CLI invocation ===` section containing the
UTC timestamp, current working directory, argv as JSON, and the original request
text. The rest of the file mirrors the CLI output, including route metadata,
assistant response, action-loop output, scrutiny output, normalized scrutiny
status, and final `execution_status`.
