# Repo Coding Assistant CLI

## Private preferences and alternate agents

Copy `user-config.example.toml` to ignored `user-config.toml` in the repo root,
or use `--user-config <path>`. Explicit CLI flags override user preferences,
which override shipped defaults. Explicitly named missing or invalid config
files fail before routing. The shipped cost ceiling is `prepaid_credits_allowed`;
the owner's local file uses `allowances_allowed`:

```toml
[defaults]
cost_policy = "allowances_allowed"
```

Enum members use uppercase names such as `CostPolicyTier.ALLOWANCES_ALLOWED`;
serialized values and variables use lowercase snake_case for both cost tiers.
Requesty remains a provider API route using `REQUESTY_API_KEY`. Paid catalog
routes require `prepaid_credits_allowed`. The separate
`requesty-free-gemma-4-31b` route uses `free_only` and verifies live zero pricing
before every inference request, including tool-loop turns and model overrides.
Missing or changed prices block inference; there is no paid fallback. Requesty
currently advertises 200 free requests per day for free models. This pricing
preflight is not an atomic service-side billing guarantee.

Run opt-in synthetic coding acceptance with
`uv run python scripts/alternate-agent-acceptance.py`. Select only the free
Requesty route with `--routes requesty-free-gemma-4-31b`. Live completion/tool
tests require `AI_PROVIDER_RUN_REQUESTY_FREE_INTEGRATION=1`; they assert reported
zero cost. Ordinary tests mock the API and do not spend requests. The tested
Gemma route reports no training but 30-day retention; acceptance sends only
synthetic fixtures. An inference key needs no Requesty admin permissions.

Antigravity, Copilot, and Kiro use official clients and native tools/sign-in.
Set `ANTIGRAVITY_COMMAND`, `GITHUB_COPILOT_COMMAND`, or `KIRO_COMMAND` to an
executable path, or install the client on PATH. Windows Kiro discovery also
checks `%LOCALAPPDATA%/Kiro-Cli/kiro-cli.exe`.
Only `--approval-policy trusted_local` is mapped for these three clients:

| Client | Native automatic approval |
| --- | --- |
| Antigravity | `--dangerously-skip-permissions` |
| Copilot | `--allow-all` |
| Kiro | `--trust-all-tools` |

Other approval modes are not mapped yet and fail before execution. These modes
grant broad native tool access without a project workspace sandbox; native
hooks/MCP servers and account permissions apply. Codex-specific image, search,
schema, MCP, output-file, and resume flags are rejected on alternate routes.
Native session retention remains client-owned; alternate ephemeral/resume
controls are not mapped yet.

```powershell
.\scripts\repo-assistant.ps1 --mode ask "Reply CONNECTED; do not call tools." `
  --execute --privacy external_allowed --route-id kiro-cli-default `
  --approval-policy trusted_local --skip-prompt-review
```

Other route IDs: `github-copilot-cli-default`,
`google-antigravity-gemini-3-1-pro`, and `requesty-openai-gpt-5-mini`.
Model slugs/entitlement may change: inspect the client's model list or use
`--model`. Kiro and Copilot default routes use native automatic selection.
Antigravity uses stream JSON input/output; Kiro uses ACP JSONL. Copilot supplies
the prompt through `-p` without shell interpolation. Its prompt appears in
process arguments but is omitted from command previews. Installed Kiro was
verified with existing sign-in; current headless docs describe `KIRO_API_KEY`.
Authentication and credits are separate from command availability. The catalog
ceiling does not enforce service-side overage settings. Live quota discovery
and automatic continuation remain follow-up work. See ADR-031 for sources.

This is a practical guide for using the local repo-aware coding assistant CLI
when the PyCharm AI Assistant / Codex quota is unavailable.

The main startup command is:

```powershell
.\scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

## Moving Work From PyCharm Chat To The CLI

For this repository's current local-only workflow, the CLI is ready to take over
routine coding-assistant work. It is strongest for bounded repository tasks:
planning, asking, reviewing, implementation with explicit local tools, Codex CLI
runs, diagnostics, transcript capture, and validation loops.

Use this default flow when starting a task:

```powershell
# 1. Inspect routing/context without contacting a model
.\scripts\repo-assistant.ps1 --mode plan "YOUR TASK" --file path\to\relevant.py

# 2. Ask for analysis or review without actions
.\scripts\repo-assistant.ps1 --mode review "YOUR TASK" `
  --file path\to\relevant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama

# 3. Implement only after the intended change is clear
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved change." `
  --file path\to\relevant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --native-tools --approval-policy interactive --start-ollama

# 4. Verify from the terminal
git diff
git status --short
python -m uv run pytest
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run pyright
```

Use the Codex route when you want behavior closest to this chat's coding model:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this repository and identify the smallest safe next change." `
  --privacy external_allowed `
  --route-id openai-codex-gpt-5-5 `
  --provider openai --model gpt-5.5 `
  --execute --skip-prompt-review
```

Use `--codex-search`, `--codex-mcp-tools`, `--codex-image`,
`--codex-output-schema`, or `--codex-persist-session` only when the specific
task needs them. They are opt-in because they change network behavior, expose
project-local tools to the Codex run, attach local files, constrain output, or
write Codex session state outside the repository.

Keep PyCharm AI Assistant chat for now when the work depends on IDE-only
context, this chat's managed app/document-control tools, or a material product
or architecture decision that needs discussion before implementation.

Current parity status:

- Ready for local repo coding workflows: yes.
- Ready for Codex CLI-backed coding workflows: mostly, with explicit opt-ins.
- Ready for GitHub, deployment, document-control, or broad connected-app work:
  intentionally no, because this repository is still local-only and those
  connectors require separate authorization decisions.

The workspace also exposes a stable command entry point:

```powershell
python -m uv run ai-assistant --mode plan "Review this module."
```

On Windows, `scripts\repo-assistant.ps1` remains the convenient wrapper because
it loads `.env`, starts the command from the repository root, and adds a
timestamped transcript under `artifacts/repo-assistant-<timestamp>/` when `--log-file` is not supplied.

The CLI supports explicit modes:

```powershell
# Show routing/context/delegation without contacting a model
.\scripts\repo-assistant.ps1 --mode plan "Review this module." --file path\to\module.py

# Answer or review without permitting file/command actions
.\scripts\repo-assistant.ps1 --mode ask "Explain this module." --execute
.\scripts\repo-assistant.ps1 --mode review "Find concrete issues." --execute

# Run a second model pass that scrutinizes the answer quality
.\scripts\repo-assistant.ps1 --mode ask "Investigate the next action for this repository." `
  --provider ollama --model deepseek-coder-v2:16b --execute --start-ollama `
  --scrutinize-response --log-file logs\repo-assistant-next-action.log `
  --ollama-log-file logs\ollama-next-action.log

# Recommended manual live acceptance check for broad repository analysis
.\scripts\repo-assistant-broad-analysis.ps1

# Foreground unattended run with a visible one-hour budget
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved next slice." `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama --away-minutes 60 --orchestrated `
  --approval-policy trusted_local

# Dry-run the staged unattended workflow without contacting a provider
.\scripts\repo-assistant.ps1 --mode plan "Implement the approved next slice." `
  --provider ollama --model qwen2.5-coder:14b `
  --away-minutes 60 --orchestrated `
  --approval-policy trusted_local

# Permit approved native tools or legacy actions for implementation
.\scripts\repo-assistant.ps1 --mode implement "Implement the approved fix." `
  --execute --native-tools --start-ollama

# Print local capability and provider readiness information
.\scripts\repo-assistant.ps1 --mode diagnose
```

`ask` is the default for backward compatibility. `plan` never contacts a
provider. `ask` and `review` reject action flags. `implement` requires
`--execute` plus either `--native-tools` or `--apply-actions`.

Use `--away-minutes N` when starting a foreground run that should keep working
while you are away. The flag prints `away_budget_*` fields in the transcript,
adds explicit unattended-run guidance to the model prompt, and, unless
`--timeout-seconds` is supplied, sets provider and external-agent timeouts to
`N * 60` seconds. Add `--orchestrated` to plan or run the staged unattended
workflow rather than only extending the timeout and prompt guidance. Orchestrated
runs create a local SQLite run record and planned stage rows in
`data/repo-assistant-runs.sqlite3` by default; use `--away-run-db PATH` to
override the local database path.

In `--mode plan`, `--away-minutes N --orchestrated` prints the intended
foreground stages, the primary route, the local/cheap auxiliary route policy,
and the approval boundary without contacting a provider. The stages are prompt
review, planning, auxiliary panel, implementation, validation, scrutiny,
bounded repair, and final handoff. This is not a background scheduler, daemon,
or job queue, but the SQLite records give later foreground stages and a future
resume/background runner a stable run ID and stage-tracking surface. External
Codex-style routes still report their timeout as an inactivity timeout because
model output resets the timer. For unattended implementation runs, choose the
approval boundary deliberately: `interactive` may pause for a prompt, while
`trusted_local` permits local read/write/shell actions under the repo
assistant's existing tool policies.

Executed orchestrated runs now update deterministic validation and final
handoff stages before the run is marked complete. The validation stage runs
`python -m pytest -q` by default, records command output previews and return
codes, and can be changed with repeated `--validation-command CMD` flags or
disabled with `--skip-validation`. Ruff and Pyright remain available through the
repository's pre-commit hooks; pass a pre-commit command explicitly when an
orchestrated run should include that broader gate. The final handoff stage
records the execution status, validation status, concise `git status --short`
output, response availability, blockers, risks, and next action fields in the
local SQLite stage details. Failed deterministic validation changes the final
run record to `completed_with_validation_errors` instead of clean completion.

The staged workflow exposes a default repair policy of three repair cycles. Use
`--max-repair-cycles N` to choose a different limit,
`--max-repair-cycles 0` to disable repair attempts, or
`--max-repair-cycles -1` to remove the cycle cap while still respecting the
`--away-minutes` wall-clock budget. When unresolved failures remain at the end
of the run, the final handoff is responsible for preserving the validation
details, blockers, and next action for the returning user.

Implementation repairs stop with `repair status=stalled` after two consecutive
attempts leave both workspace content and validation failure evidence unchanged.
This guard also applies to `--max-repair-cycles -1`. File additions, deletions,
and content edits count, including ignored `RESEARCH_*.md` reports. Changed
validation evidence resets the counter; ordinary duration changes do not.
Assistant claims and tool-call counts alone do not establish progress. Content
fingerprints are local, and logs, databases, caches, virtual environments, and
IDE bookkeeping are excluded so run tracking cannot sustain an ineffective loop.
Progress means observed change, not proof that the change is useful or correct.
Repair stage details record each classification, changed paths, and stop reason.

Repair and deterministic validation reserve ten percent of the away budget,
capped at 120 seconds, for local scrutiny and final handoff. Validation command
timeouts share the available allocation. Repair requests use at most half the
remaining repair allocation, leaving time for validation. These are scheduling
and request-timeout limits: native multi-turn execution, running tools, Ollama
startup, and external clients with inactivity timeouts can still overrun them.
This slice does not add process-wide hard cancellation. If time is exhausted,
scrutiny is explicitly recorded as skipped and clean completion is withheld.

Executed orchestrated implementations run local-only scrutiny after the last
validation/repair attempt, for both provider-native and external CLI routes.
The reviewer receives the original task, latest response, deterministic
validation evidence, observed changed paths, and bounded text excerpts from
changed files, including ignored reports. It uses the existing structured
scrutiny report format and honors the configured Ollama startup settings. It
does not run tools or silently escalate to a paid reviewer. Its findings cannot
override deterministic validation failure. Failed, invalid, skipped, or non-pass
review is visible in stage details and final handoff risks; a previously clean
status becomes `completed_with_scrutiny_errors` or
`completed_with_scrutiny_findings`. This is a bounded claims review, not a full
code audit, model-quality evaluation, or research-source verifier.

### Disposable research reports

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

Research uses a dedicated review prompt that separates source evidence from report
claims and the completion summary. Quoted source passages precede the candidate
report, with explicit coverage flags and unavailable-source URLs. Calibration
examples distinguish verified assertions from tentative inferences and honest
unknowns. A forty-case fictional DeepSeek prompt evaluation found more consistent
acceptance of honest unknowns, but no reduction in false factual approvals. Reviews still
invented supporting quotations and approved contradictions. Treat their grounding
judgments as fallible advisory findings requiring human verification; this is not
a demonstrated factual-accuracy improvement. The reviewer and its settings remain
unchanged. Evaluation details are recorded in ADR-037.

A subsequent local reviewer comparison used the same forty cases across four
installed models plus a Qwen 3 thinking-disabled variant, then twenty fresh cases
for the finalists. Qwen 3 14B with thinking disabled had the best observed
verdict/format consistency and short-review latency within the existing budget;
GPT-OSS 20B was the stronger alternative for source explanations and corrected
claim wording. Both handled the four/thirty-source full-report capacity fixtures.
These are task-specific recommendations from synthetic evidence, not accepted
defaults or a universal model ranking. Production selection and advisory policy
remain unchanged. Autonomous search/report-writing quality was not compared;
native research execution separately requires a tool-capable model. See ADR-037
for results, remaining explanation errors and the bounds of the comparison.

ADR-038 review contracts are available as an explicit research-only opt-in:
`--research-review-policy quality_first`. The legacy reviewer/settings remain the
default while the representative evaluation and held-out activation gates are
incomplete. Auto selects a supported deliberative preset for final grounding;
direct mode requires workload-specific evaluation evidence in the neutral policy,
or an explicit mode override. Short report length does not establish simplicity.
When eligible peers have equal catalog quality, selection prefers a reviewer
different from the primary model; same-model review is identified in the reasons.
This is a conservative capability rule, not a new measured model-quality ranking.

Use `--research-review-model MODEL` and `--research-review-mode
auto|default|direct|deliberative` to override the reviewer. Overrides require the
opt-in policy and never bypass local/free route checks. `default` explicitly
retains the model's native mode, including models without declared reasoning
controls. Catalog `metadata.review_deliberative` / `review_direct` booleans
declare preset eligibility, and the provider verifies installed capabilities
before inference. Missing metadata never invents support. The current mappings
support Qwen3 thinking true/false and GPT-OSS deliberative high effort; GPT-OSS
direct mode is unsupported and produces a clear error. There is no cloud fallback.
When `/api/show` advertises `thinking.values`, the requested explicit value must
appear with the same type; an unsupported value cannot silently use the runtime
default. Installed runtimes without that field retain the capability and
architecture checks.

`--research-review-output-tokens` defaults to 4096 and accepts 2048–8192;
`--research-review-timeout-seconds` defaults to 300 and accepts positive finite
values up to 300. Each call also respects `--timeout-seconds` and the actual run
deadline. The whole review, including capability inspection and at most one
stronger length retry, shares a deadline no later than 300 seconds. A retry can
double the generation allowance up to 8192 with the same mode and unchanged
evidence if time/context remain. Truncation, an empty visible answer, a late
response or failed format parsing never becomes a pass or a weaker-mode fallback.
Sampling remains matched at temperature 0.2 pending controlled tuning.

The opt-in final reserve is ten percent of the run capped at 300 seconds;
legacy/non-research retains the 120-second cap. Context remains 32768 unless
an explicit Ollama resource profile supplies it. The adapter reserves framing
and bounds input tokens conservatively by UTF-8 bytes by default. Optional
`--research-review-tokenizer-file` supplies one explicit local tokenizer JSON for
the selected quality-first reviewer. Compatible Qwen on/off profiles use the
complete rendered input count; unsupported combinations retain the byte bound.
The conservative bound can reject large evidence that an exact tokenizer could fit;
it never shrinks source/report evidence or enlarges an explicit context to force
admission. Mode, route, decision reasons, effective allowances and retry outcomes
reuse existing scrutiny-stage metadata; source bodies and prepared prompts gain
no new production persistence. A small pilot cannot satisfy the rollout gates.

The pure `ai_orchestrator.scheduling.admit_task` contract checks explicit start,
positive required allocation, remaining monotonic time, planned status and
caller-validated execution constraints. It neither runs nor changes a task's
status. Non-fitting tasks remain planned. The application-owned SQLite scheduler
and strict selected ordering are implemented under ADR-039; generic cancellation
remains outside its scope. Long tasks require an explicit start.

`scripts/research-review-evaluation.py` plans the approved local comparison from
an evaluation-only public-source corpus. It requires 24 cases across at least
six topic families, eight held out by whole family, and matching context/sampling
settings. Source excerpt digests are checked before execution. Expected findings
are kept out of reviewer requests. Corpus excerpts and results stay in ignored
local artifacts under ADR-038; private documents cannot be benchmark fixtures.
Preflight validates every case/source field consumed by execution, including audit
findings and complexity, so a malformed late case cannot waste earlier model calls.
Case IDs use 1–64 letters/digits/underscores/hyphens and are unique ignoring case
to protect Windows output files. Source IDs are unique within a case. Explicit
missing coverage remains valid through an empty segment list and coverage description;
its retrieval receipt cannot supply missing source text.

Plan without starting inference:

```powershell
python -m uv run --no-sync python scripts/research-review-evaluation.py `
  artifacts\research-review-preparation-20261003\corpus.json
```

To explicitly start that selected task in a sufficiently long window, add
`--execute --available-minutes 110`. The runner reserves ten minutes for handoff
by default, counts preparation against the window, and requires the full
90-minute task allocation. A 90-minute overall window with that reserve is
refused without starting models. Each serial review rechecks its full configured
call allocation; a non-fitting next call stops this experiment with an incomplete
summary. This fixed experiment runner does not implement a general scheduler queue,
storage contract, skip policy or hard cancellation for arbitrary jobs.

The three variants are Qwen3 deliberative/direct and GPT-OSS native-default.
Variant order rotates by case, and development calls precede holdout. A fresh
output directory protects previous evidence. The runner records prepared requests
and raw local responses before parsing, including malformed responses and bounded
retries. `CALLS_COMPLETE` means all planned calls were attempted; format failures
still give a nonzero exit, and visible-answer quality audit remains pending.
Source attribution, claim scope, corrected confidence labels, critical false
approvals, baseline regressions and latency must be audited before considering
D4 activation. Software checks or shorter development pilots cannot satisfy it.

The prepared October 3 corpus uses correlated variants of six public-source
families and reports shorter than the production length guideline. A separate
22.6k-character report with 16.8k excerpt characters was refused at 32k context
under conservative byte admission. The approved tokenizer diagnostic subsequently
counted the same full-evidence requests at 11,304-11,889 input tokens and matched
all 72 matrix runtime input counts for the inspected templates. The opt-in production
counter is now implemented and replayed offline against recorded Qwen capacity
requests. Live acceptance of the integration remains deferred.

The October 3 matrix attempted all 72 cells; 71 parsed and one GPT baseline format
failed. Deliberative/direct/GPT focal agreement was 24/24, 23/24 and 21/24 including
that failure. Direct made a critical false approval on a heldout transaction-scope
claim. Citation/confidence/correction defects remain, so D4 keeps the policy opt-in.
These correlated short reports do not establish general factual reliability.

An isolated offline counter is available with the approved optional dependency:

```powershell
uv sync --group research-token-count
uv run --no-sync --group research-token-count python scripts/research-token-count-prototype.py `
  --tokenizer-file artifacts\research-token-count-20261003\Qwen--Qwen3-14B\tokenizer.json `
  --request-file artifacts\research-token-count-20261003\capacity-qwen3_deliberative-request.json `
  --template-file artifacts\research-token-count-20261003\qwen3-14b-template.txt
```

Diagnostic assets are local ignored artifacts, not bundled model data. The script
downloads nothing and performs no inference. Request counting accepts only the
inspected two-message model/template/tokenizer fingerprints and supported thinking
controls; Qwen requires an explicit boolean (native-default probes mismatched),
and GPT additionally requires `--runtime-date YYYY-MM-DD`. Arbitrary rendered
UTF-8 input can instead use `--rendered-prompt-file`. Padding/truncation are disabled,
complete input digests are recorded, and the output remains `PROTOTYPE_ONLY` with
runtime compatibility unverified by the script itself. Separate recorded runtime
comparisons supply the evidence; a diagnostic count alone cannot admit production input.

Production exact counting additionally requires Ollama 0.32.5, tokenizers 0.23.2,
the inspected GGUF blob and template digest, the pinned tokenizer digest, two plain
system/user messages and explicit Qwen on/off. Unknown versions/assets/templates,
extra model history/system instructions/adapters, missing dependency/file and
Qwen native default use the conservative bound. GPT remains conservative because
its runtime date/timezone agreement is unverified outside the recorded session.
The diagnostic can still count GPT with a supplied date. No private runner endpoint
or automatic download is a production dependency.

The tokenizer path is relative to the invoking working directory unless absolute.
The option requires `--tool-profile research --research-review-policy quality_first`.
For a future explicitly started Qwen-deliberative run, append
`--research-review-tokenizer-file artifacts/research-token-count-20261003/Qwen--Qwen3-14B/tokenizer.json`.
The wrapper forwards this through its existing extra CLI arguments. Stage metadata
records `input_bound_method` and any `tokenizer_fallback_reason` without saving
prompt/source bodies. Version inspection, counting and retries share the review
deadline; fallback never trims evidence or increases context. Software replay is
not live acceptance, and runs remain planned while local compute is unavailable.

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
  --research-review-tokenizer-file artifacts/research-token-count-20261003/Qwen--Qwen3-14B/tokenizer.json
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

Native execution rejects a legacy JSON tool request returned as plain text when
no tools were executed. Such a response is a failed implementation, rather than
evidence that a command ran or a file was created. Text is never promoted to a
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

### Local Chat Transcripts

`--mode chat` starts the first persistent local chat workflow. It stores ordered
provider-neutral messages in SQLite so later turns can resume the same chat:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain the selected module." `
  --mode chat --execute `
  --provider ollama --model qwen2.5-coder:14b
```

By default transcripts are stored in `data/repo-assistant-chats.sqlite3`. Use
`--chat-db PATH` to choose another local database, `--chat-session last` to
resume the latest chat for the repository, or `--chat-session <session-id>` to
resume a specific session. `--chat-list` prints recent sessions without
contacting a provider.

When a resumed chat grows beyond `--chat-history-budget-chars`, the default
`--chat-context-mode rolling_summary` stores a local rolling summary for older
turns and sends that summary plus the recent raw transcript tail. The CLI prints
whether a summary was used or updated, how many raw messages were sent, how many
were omitted, and the assembled character count. Use
`--chat-context-mode hard_fail` to fail instead of summarizing when the budget is
exceeded, `--chat-context-mode full_history` or `--chat-history-budget-chars 0`
to send the full local transcript, and `--chat-recent-message-count N` to choose
how many recent non-system messages are kept raw.

Chat transcripts may contain the request and selected repository context because
they preserve the provider-neutral messages that were actually sent to the
model. Keep them local and private.

For external-agent routes such as Codex CLI, `--timeout-seconds` is treated as
an inactivity timeout. Model output resets the timer. During execution, the CLI
prints bounded `external_agent_activity` and `external_agent_status` lines so a
foreground run shows that work is still happening without dumping raw JSONL.
The diagnostics block then prints parsed event counts, usage, delegation
status, failure reasons, and concise stderr summaries. Hidden reasoning-summary
events remain type-only and raw JSONL stays in the transcript-only section. The
CLI prints the exact
`external_agent_command_line_json` before execution and adds the effective
approval policy and Codex sandbox to the prompt so the external agent does not
infer a read-only environment when the requested sandbox is `workspace-write` or
stronger. Fresh and resumed Codex exec commands both forward the repository root
with `--cd` and the selected sandbox with `--sandbox` as `codex exec` options
before any resume subcommand. It also includes the repo-assistant system prompt
in the external agent stdin prompt so external routes receive the same
high-level repo-aware contract as provider-native routes. If a timeout or
process error occurs after
partial output, the CLI
summarizes parsed JSONL events and keeps raw JSONL in the transcript-only
section rather than dumping it to the console. Known noisy Codex model-refresh
stderr is filtered out of the main stderr summary. When a transcript log is
active, complete external stderr is saved beside it as `*.stderr.log` and the
transcript prints that path.

Local execution paths use equivalent bounded activity prefixes:
`local_agent_activity` for local provider/native tool-loop model calls,
`delegated_agent_activity` for local context extraction, `scrutiny_activity`
for response scrutiny, and `local_tool_activity` for native-tool or legacy
action follow-up work.

By default, transcript logs do not include the complete assembled model prompt.
Use `--log-full-prompt` with `--log-file` when building evaluation data that
needs exact instructions and repository context. For provider API routes, this
records the exact system prompt and user prompt. For external-agent routes such
as Codex CLI, this records the exact stdin prompt passed to the agent. These
sections may contain `AGENTS.md`, `CURRENT_CONTEXT.md`, selected source files,
and the original request, so keep them local unless reviewed.

Every run also ends with `=== Run metrics ===`. These fields are intended for
comparing CLI changes, model behavior, and local settings over time:

- `total_wall_seconds` and `process_cpu_seconds`;
- `python_memory_current_bytes` and `python_memory_peak_bytes`;
- `primary_elapsed_seconds` and `scrutiny_elapsed_seconds`;
- provider-reported primary and scrutiny token usage when available:
  `*_usage_source`, `*_input_tokens`, `*_output_tokens`, `*_total_tokens`;
- provider-reported latency when available: `*_provider_latency_ms`.

Token and provider-latency fields are `None` or `unavailable` when the backend
does not report them. The memory metrics are Python-process memory observed by
the CLI, not total GPU, Ollama server, IDE, or external-provider resource use.

When using `scripts\repo-assistant.ps1`, transcript logging is on by default.
Each run without an explicit `--log-file` writes to
`artifacts/repo-assistant-YYYYMMDD-HHMMSS/assistant.log`. The canonical broad-analysis
script groups `assistant.log` and `ollama.log` under
`artifacts/repo-assistant-broad-analysis-YYYYMMDD-HHMMSS/` by default. Pass
`--log-file` or `-LogFile` when you intentionally want a fixed path.

When `--start-ollama` is used, Ollama server output is written to
`artifacts/ollama-runtime/ollama-serve.log` by default when calling the Python CLI
directly; the PowerShell launchers supply their run's `ollama.log`.
Change it with `--ollama-log-file`.
The CLI also reports whether the Ollama API is reachable after startup. The
`artifacts/` directory is ignored by Git; legacy/custom `logs/` is also ignored.

To collect a local machine/provider report without sending anything to a model:

```powershell
.\scripts\repo-assistant.ps1 --local-capabilities
```

The report includes OS, CPU count, total/available RAM, detected GPU names and
memory where Windows exposes it, Ollama availability/version, model storage,
and installed/running Ollama models. It is intended as the first stable
onboarding and diagnostics contract for a future app UI or database.

Use `--ollama-profile gaming`, `--ollama-profile balanced`, or
`--ollama-profile full` when the CLI needs to start Ollama with a different
local allocation:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this file." `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama --ollama-profile gaming
```

The profiles currently configure Ollama's default context length to 4,096,
8,192, or 32,768 tokens respectively, while keeping one model and one request
slot active. They control memory pressure and concurrency, not a precise
percentage of GPU utilization. A profile only applies when this command starts
Ollama; stop/restart an already-running Ollama server before changing profiles.

Repository context is deliberately bounded by default: the CLI includes at most
5,000 characters total and 2,500 characters from any one file. Large
`AGENTS.md`, `CURRENT_CONTEXT.md`, or selected source files are shortened from
both ends with a truncation marker, preventing the local model's context window
from being consumed by repository instructions alone. Increase the limits for
a focused task when needed:

```powershell
.\scripts\repo-assistant.ps1 `
  "Analyze this module in detail." `
  --file packages\ai_provider\src\ai_provider\contracts.py `
  --context-budget-chars 12000 `
  --context-file-budget-chars 8000
```

Use `--context-budget-chars 0` only when targeting a model with a known larger
context window.

For a primary request that needs more repository context than the primary model
should receive directly, enable bounded local context delegation:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this implementation and identify concrete issues." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --provider ollama --model qwen2.5-coder:14b `
  --delegate-context --execute --start-ollama
```

This sends a bounded, line-numbered copy of the loaded context to a local
Ollama model first. The summary must cite supplied sources using
`[source:path:line]` references before it is injected into the primary prompt.
Uncited summaries are discarded. Local delegation is restricted to bounded
support work; architecture and implementation decisions remain with the
primary model. Use `--delegation-context-budget-chars` to adjust the local
context budget. Without `--execute`, the option only reports that delegation is
planned and does not contact a model.

If Windows blocks direct script execution, use this form instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\repo-assistant.ps1 "YOUR REQUEST" --provider ollama --model qwen2.5-coder:14b --execute --start-ollama
```

The underlying Python CLI lives at:

```text
packages/ai_provider/src/ai_provider/repo_coding_assistant.py
```

The coding orchestration helpers used by that CLI live in
`packages/ai_provider/src/ai_provider/coding_assist.py`. The older
`packages/ai_provider/examples/coding_assist.py` path remains a compatibility
export, and the example repo-assistant path remains available during the
migration.

Provider-layer failures are reported with `status: failed` and
`execution_status: failed`; the command returns a non-zero exit code instead
of emitting a success-shaped response.

## External Coding Agent Routes

The catalog includes subscription/client-backed coding-agent routes alongside
provider API routes:

- Codex CLI: `openai-codex-gpt-5-5`, access method `codex_cli`;
- Google Antigravity: `google-antigravity-gemini-3-1-pro` and
  `google-antigravity-gemini-3-8-flash`, access method `antigravity_cli`;
- GitHub Copilot placeholder: `github-copilot-cli-default`, access method
  `copilot_cli`;
- Kiro placeholder: `kiro-cli-default`, access method `kiro_cli`.

Codex execution is wired first. The CLI discovers the Codex command from
`CODEX_COMMAND`, then PATH, then the PyCharm bundled Codex binary. Example:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this repository and identify the smallest safe next change." `
  --privacy external_allowed `
  --route-id openai-codex-gpt-5-5 `
  --provider openai --model gpt-5.5 `
  --execute --skip-prompt-review
```

Codex is invoked as `codex exec --json` with repository cwd, stdin prompt,
workspace sandbox, and ephemeral session state by default. The CLI parses the
JSONL event stream enough to report the final answer, command/tool/file-change
event counts, web-search event counts, failure status, and usage payloads when
Codex emits them. Raw JSONL is preserved in transcript logs under
`=== External agent raw JSONL ===` for debugging and evaluation without dumping
the full event stream to the terminal.

Use `--codex-persist-session` when intentionally starting a resumable Codex
session. This omits `--ephemeral`, allowing Codex to write its normal session
state outside the repository. Resume with `--codex-resume last` or
`--codex-resume <session-id-or-name>`, which invokes `codex exec resume --json`.
Use `--codex-output-last-message path\to\last-message.txt` when you also want
Codex's `--output-last-message` artifact. The CLI creates the parent directory,
passes the path to Codex, and uses the file as a final-answer fallback when the
JSONL stream does not contain a final-answer event.
Use `--codex-output-schema path\to\schema.json` to pass Codex an explicit JSON
Schema via `--output-schema` for structured final responses.
Use `--codex-search` to enable Codex web search for one run. This is deliberately
off by default because it allows external web/search activity in addition to
sending the selected repository context to Codex. The verified local Codex CLI
expects search as a top-level flag, so the repository CLI invokes
`codex --search exec ...` rather than the unsupported `codex exec --search ...`.
Use `--codex-mcp-tools` to inject this repository's project-local MCP server
into one Codex route via Codex `-c` config overrides. This exposes
`read_file`, `list_dir`, `find_files`, `grep_search`, and the local-only
`delegate_task` bridge for that run without requiring global MCP registration.
Use repeated `--codex-image path\to\screenshot.png` flags to attach local image
files to the initial Codex prompt. This is useful for screenshots, diagrams, or
visual regressions; the prompt should still state what Codex should inspect and
what output you want.

Non-Codex external-agent routes are discovered but not executed yet. Diagnostic
mode checks common command names without reading tokens or config contents:
Antigravity via `ANTIGRAVITY_COMMAND`, `agy`, or `antigravity`; GitHub Copilot
via `GITHUB_COPILOT_COMMAND` or `copilot`; and Kiro via `KIRO_COMMAND`,
`kiro-cli`, or `kiro`. Execution adapters for those routes must map each
client's native permission, session, output, and capability behavior before they
can be enabled safely.

`--mode diagnose` and `--local-capabilities` include Codex diagnostics when a
Codex command is discoverable: command path, version, login-status text,
`exec --json` support, MCP list output, plugin list output, a structured plugin
summary, and the relevant config path. The report does not read or print auth
files, config contents, or tokens.

The same diagnostics also include an `authorization` registry summary. For the
Codex CLI bridge, this maps local command discovery, login status, plugin
summary, and MCP status into the shared `ai_agent.authorization` contracts.
Read scopes cover secret-free local diagnostics. Write scopes are modeled for
Codex workspace execution, resumable session state, plugin install/remove, and
MCP registration, but those actions still require their existing explicit CLI
flags and approval-policy gates.

Use `--codex-plugin-install PLUGIN@MARKETPLACE --execute` to explicitly install
one or more Codex plugins through `codex plugin add`. The flag may be repeated:

```powershell
python -m uv run ai-assistant `
  --codex-plugin-install openai-developers@openai-curated `
  --codex-plugin-install codex-security@openai-curated `
  --execute
```

Use `--codex-plugin-remove PLUGIN@MARKETPLACE --execute` to explicitly remove
installed plugins through `codex plugin remove`. Plugin management cannot be
combined with a prompt request. The CLI reports before/after `codex plugin list`
output, prints the exact command for every operation, and emits
`codex_plugin_expected_status_json` for the requested selectors. Install runs
fail when a requested plugin is not installed in the parsed after-list; removal
runs fail when a requested plugin still appears installed.

The plugin command only installs or removes local Codex plugin bundles. It does
not authorize external services, complete OAuth, approve app permissions, enable
write actions in connected services, or import/sync marketplaces. Review any
plugin apps, MCP servers, and hooks separately, then start a new Codex CLI
session before relying on newly installed skills or tools.

For plugin parity checks, treat parsed `codex plugin list` / `codex mcp list`
output as the source of truth. A live Codex model response may self-report
plugin visibility, but that is weaker evidence and can be misleading when the
prompt asks about the runtime's own tools or skills.

Initial approved Codex plugin set for this repository:

- `openai-developers@openai-curated`
- `codex-security@openai-curated`
- `superpowers@openai-curated`
- `plugin-eval@openai-curated`
- `build-web-apps@openai-curated`

See `docs/codex-plugin-review.md` for the point-in-time review of deferred
plugins and why they were not installed in the first batch.

Use `--codex-mcp-setup` to expose this repository's selected local inspection
and delegation tools to Codex through MCP:

```powershell
python -m uv run ai-assistant --codex-mcp-setup
```

The setup command writes local `.codex\config.toml` for project-scoped Codex
config. The file contains this checkout's absolute workspace path and is ignored
by Git; rerun the setup command for each local checkout. It does not change
user-level Codex MCP configuration by default. For single repo-assistant runs,
prefer `--codex-mcp-tools`; it passes the same project-local server definition
to Codex via per-run `-c` overrides.

To also register the server persistently with the official Codex MCP CLI, pass
the explicit global-registration flag:

```powershell
python -m uv run ai-assistant --codex-mcp-setup --codex-mcp-register-global
```

That command runs `codex mcp add repo_assistant_tools -- ...`, so
`codex mcp list` can see the server outside this project-scoped config. Use it
only when you intentionally want to update the broader Codex environment.

The exposed MCP server is intentionally limited to read/search tools plus
bounded local delegation: `read_file`, `list_dir`, `find_files`, `grep_search`,
and `delegate_task`. It does not expose write or shell tools. Tool calls are
bounded to the configured workspace root. `delegate_task` routes to a local-only
child agent with the same read/search tool surface, nested delegation disabled,
and no MCP write or shell capability.

The PyCharm-bundled Codex CLI verified in this repository is `codex-cli
0.137.0`. On 2026-09-26, `gpt-5.5` completed a low-risk JSONL execution through
ChatGPT sign-in, while `gpt-5.1` returned an upstream invalid-request error for
this account. Keep both facts in mind when selecting routes.

If a Codex CLI run fails with `401 Unauthorized` or `Missing bearer or basic
authentication`, the repo assistant reached the Codex executable but Codex's
local session was rejected by OpenAI. This is different from missing
`OPENAI_API_KEY`: Codex CLI routes normally use the Codex/ChatGPT login, not
the repository `.env` API key. Run Codex login diagnostics, refresh the local
Codex login through the CLI or PyCharm/Codex, or set `CODEX_COMMAND` to a
separately authenticated Codex CLI. Until that is fixed, use local Ollama or a
direct hosted provider route with the relevant API key.

To refresh Codex authentication through the repository CLI, run:

```powershell
.\scripts\repo-assistant.ps1 --codex-login
```

For device-code authentication, run:

```powershell
.\scripts\repo-assistant.ps1 --codex-login-device
```

These commands call the official Codex CLI login flow and may open a browser or
print a device-code link. They mutate local Codex auth state, cannot be
combined with a prompt, and do not read or print token values. The PowerShell
wrapper does not create a transcript log for these auth-refresh commands.

This is not full parity with the Codex IDE/ChatGPT environment: app/plugin
tools, document-control tools, IDE-private state, and this chat's managed
approval surface are not automatically available through `codex exec`.
Antigravity, Copilot, and Kiro are represented for route planning and
diagnostics, but their execution adapters remain disabled until their official
noninteractive command contracts and local executable paths are confirmed.

The accepted parity direction is recorded in
`docs/decisions/ADR-024-codex-cli-parity-authorization-and-dev-tool-policy.md`.
Codex remains the baseline capability target, but approval policy, tool
authorization, and development tool contracts should stay model-neutral so
alternate executors can use the same policy.

### Codex Capability Matrix

| Capability | This ChatGPT/Codex session | Repository CLI via Codex CLI | Current status |
| --- | --- | --- | --- |
| Repository instructions | Root `AGENTS.md` and runtime instructions are loaded by this session. | The repo assistant includes bounded `AGENTS.md`/`CURRENT_CONTEXT.md` context in the stdin prompt; Codex CLI also has its own `AGENTS.md`/config behavior. | Implemented, with bounded prompt context. |
| Shell/file coding work | Managed tools can inspect and edit the shared workspace. | `codex --ask-for-approval never exec --json --sandbox workspace-write --ephemeral -` runs inside the repo root for noninteractive workspace-write runs. | Implemented for Codex route. |
| Machine-readable execution events | Tool calls are available to this runtime. | JSONL stdout is parsed for final answer, command/tool/file-change events, failures, and usage. | Implemented with tolerant parsing. |
| Raw transcripts/event logs | Conversation and tool output exist in the managed session. | CLI transcript logs preserve invocation metadata, full prompts when requested, run metrics, and raw Codex JSONL. | Implemented as local files under `artifacts/<run>/` by default. |
| Final-answer artifact | The managed session displays the final answer in chat. | `--codex-output-last-message` writes Codex's last assistant message to an explicit local file and uses it as a JSONL fallback. | Implemented as opt-in local file output. |
| Structured final response | This runtime can constrain some outputs through tool/runtime mechanisms. | `--codex-output-schema` passes an explicit JSON Schema file to `codex exec`. | Implemented as opt-in schema file input. |
| Approval/sandbox policy | Managed by the active ChatGPT/Codex runtime. | `--approval-policy` selects model-neutral presets for native tools and legacy actions. Codex routes map `read_only` to `--sandbox read-only`, `interactive`/`workspace_write` to `--sandbox workspace-write`, and `trusted_local` to `--sandbox danger-full-access` for commit-capable local runs. Codex approval is forwarded as top-level `--ask-for-approval`. | Implemented first preset slice; Codex CLI still lacks exact managed approval UI parity. |
| MCP tools | Available here through the current managed runtime. | `--codex-mcp-tools` injects the local `repo_assistant_tools` MCP server for one Codex run; `--codex-mcp-setup` can also write project config. The server exposes read/search repository tools plus bounded local `delegate_task`. | Implemented for selected local read/search tools and local-only delegation. |
| Plugins/apps | This session has installed app/plugin tools exposed by ChatGPT. | Diagnostics list Codex plugin marketplace/install status and structured plugin counts. Explicit install/remove is available through repeated `--codex-plugin-install` / `--codex-plugin-remove` with `--execute`. | Initial approved plugin install set implemented; future connectors one at a time behind reusable authorization. |
| Document/app-control tools | Available here when connected document sessions expose tools. | Not inherited automatically by `codex exec`. Development-relevant bridges may be added as needed, with read/write capability designed together and writes gated by policy. | Accepted direction in ADR-024; implementation deferred until a concrete development workflow needs it. |
| Web/search | This runtime may have managed browsing tools. | `--codex-search` invokes `codex --search exec ...` for one explicit Codex CLI run. Default runs omit search. | Implemented as explicit opt-in only. |
| Images/multimodal input | This runtime can receive images when tools/context allow it. | Repeated `--codex-image PATH` flags forward local images to `codex exec --image PATH`. | Implemented as explicit opt-in image attachments for Codex CLI routes. |
| Multi-turn resume | This chat preserves conversation state. | Default runs remain ephemeral. `--codex-persist-session` starts a resumable session, and `--codex-resume last|<session-id>` resumes one through Codex CLI. | Implemented as explicit opt-in Codex persistence. |

## CLI-First Roadmap

The current CLI is the execution foundation for the project. The next steps
are intentionally CLI-first:

1. stabilize the existing one-shot request, review, tool, delegation, and
   diagnostics behavior;
2. expose explicit `plan`, `ask`, `review`, `implement`, and `diagnose` modes;
3. add CLI-level integration tests for routing, delegation, permissions, and
   verified final status;
4. move the implementation behind a stable `ai-assistant` package command while
   retaining this PowerShell launcher;
5. build interactive chat as a thin multi-turn interface over that stable
   execution service.

The next parity-specific roadmap is:

1. define model-neutral approval policy presets;
2. introduce a reusable authorization boundary for Codex/GitHub/app connectors;
3. add development-relevant tool bridges only as concrete workflows require
   them;
4. design read and write capability contracts together, even when writes remain
   disabled by default;
5. approve external connectors one at a time.

Chat is deliberately deferred until the CLI has a predictable execution and
approval contract. Persistent memory, background jobs, web/search integrations,
and autonomous external actions are also out of scope for the current CLI
milestone.

It is intentionally smaller than the PyCharm AI Assistant tab. It can load repo
context, call Ollama/OpenAI/Requesty, and optionally run explicit local file and
command actions proposed by the model. It does not have IDE integration,
persistent memory, a dashboard UI, web/search, background jobs, or autonomous
external actions.

## Where To Run Commands

Use either:

- the PyCharm Terminal tab; or
- a normal Windows PowerShell window.

Both are fine. The important part is the current directory.

Run commands from the repository root:

```powershell
cd C:\Users\Jakub\PycharmProjects\AI-projects
```

You can confirm you are in the right place with:

```powershell
git status --short
```

If that command works and shows this repository's status, you are in the right
directory.

## What Is Already Set Up

Already implemented in this repository:

- repo-aware CLI script;
- automatic loading of root `AGENTS.md`;
- automatic loading of root `CURRENT_CONTEXT.md` when present;
- selected file context through `--file`;
- manual provider/model selection for `ollama`, `openai`, and `requesty`;
- local Ollama startup helper through `--start-ollama`;
- explicit execution through `--execute`;
- optional source-grounded local context delegation through `--delegate-context`;
- optional action loop through `--apply-actions`;
- repo-internal files and command working directories are allowed automatically;
- outside-repo files and command working directories ask first unless
  `--allow-outside-files` is passed.

No separate install step is currently needed beyond using the existing repo
environment with `uv`.

The normal startup script is already set up:

```text
scripts/repo-assistant.ps1
```

Use that script for day-to-day commands. It loads `.env` if present and then
starts the Python CLI.

## Local Ollama Use

This is the simplest path. It does not need an API key.

Use one of the local models already installed in Ollama, for example:

- `qwen2.5-coder:14b`
- `qwen3:14b`
- `deepseek-coder-v2:16b`
- `gpt-oss:20b`

Dry run without contacting a model:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain the selected file briefly." `
  --file packages\ai_provider\src\ai_provider\contracts.py `
  --provider ollama --model qwen2.5-coder:14b `
  --skip-prompt-review
```

Ask the local model for an answer:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this file and suggest the smallest maintainable fix." `
  --file packages\ai_provider\src\ai_provider\contracts.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

Allow the assistant to use local repo tools:

```powershell
.\scripts\repo-assistant.ps1 `
  "Inspect the selected tests and implement the smallest fix if needed." `
  --file tests\test_repo_coding_assistant_example.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --apply-actions --start-ollama
```

## OpenAI Use

OpenAI is not automatically authorized by the repository. You need an API key.
See `docs/environment.md` for the `.env` policy and setup details.

One-time local setup:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` yourself and set `OPENAI_API_KEY=...`.

Run:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this code and propose the smallest maintainable change." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --privacy external_allowed `
  --provider openai --model gpt-5-mini `
  --cost-policy billing_allowed --execute --apply-actions
```

Notes:

- `--privacy external_allowed` is required for hosted providers.
- `--cost-policy billing_allowed` is required for OpenAI direct API routes in
  the sample catalog because they can incur metered API billing.
- Do not commit API keys.
- The wrapper script loads `.env` for the run.

## Automatic Usage-Limit Continuation

Coding runs automatically try an authenticated, compatible route on the same
billing tier after an allowance/quota limit. An explicit Codex route/model
selects the first attempt; fallback may change it. Task privacy, required tools,
minimum quality and latency remain constraints. Higher quality grades are
preferred, but a standard-grade route can replace a high-grade route when the
task only requires standard quality. No paid escalation or lower-tier switch
occurs automatically. Exhausted billing buckets are skipped for that run.

Before the primary run, primary and eligible fallback native clients receive
non-inference authentication checks. An interactive terminal offers sign-in for missing accounts. In a
noninteractive terminal, sign-in instructions are printed and those routes are
excluded. Available fallbacks are reported before execution. An unverified
primary login stops startup before task execution. A stored login or
successful preflight does not guarantee future entitlement or remaining quota.

Continuation preserves existing edits and uses the original objective plus
observed progress counts. The replacement inspects current files and validates
the final artifacts. Raw tool arguments/outputs and private native session state
are not transferred. A replacement remains selected for repair attempts.
Orchestrated implementation records include its route and attempt history.
Other errors retain existing failure handling. If no ready comparable route
remains, the CLI reports `fallback_exhausted`, preserves edits, and returns
failure without prompting during execution.

Only `trusted_local` currently permits cross-client fallback to Copilot,
Antigravity, and Kiro; their other approval mappings remain unavailable.
Required client-specific capabilities/options also restrict eligibility.
Provider-native coding and one-shot coding modes participate; external-client
chat and recovery after process restart remain deferred.

The default can be disabled in private `user-config.toml`:

```toml
[fallback]
enabled = false
```

Run `uv run python scripts/fallback-acceptance.py` for a synthetic Codex-limit
simulation followed by a real Copilot continuation. This consumes a Copilot
allowance request; it does not deliberately exhaust Codex or use paid APIs.
See ADR-032 for the policy and known continuation limits.

## Requesty Use

Requesty is also not automatically authorized by the repository. You need a
Requesty API key.
See `docs/environment.md` for the `.env` policy and setup details.

One-time local setup:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` yourself and set `REQUESTY_API_KEY=...`.

Run:

```powershell
.\scripts\repo-assistant.ps1 `
  "Review this code and propose the smallest maintainable change." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --privacy external_allowed `
  --provider requesty --model openai/gpt-5.1 `
  --execute --apply-actions
```

## Adding More Context

Pass `--file` more than once:

```powershell
.\scripts\repo-assistant.ps1 `
  "Explain how these files work together." `
  --file packages\ai_provider\examples\repo_coding_assistant.py `
  --file tests\test_repo_coding_assistant_example.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

The CLI always tries to include root `AGENTS.md` and `CURRENT_CONTEXT.md`
automatically. You do not need to pass those manually.

## Permission Boundary

Default behavior:

- selected files inside the repo are read automatically;
- assistant actions inside the repo are allowed automatically;
- selected files outside the repo ask first;
- assistant action paths or command working directories outside the repo ask
  first;
- provider calls happen only with `--execute`;
- local file/command actions happen only with `--apply-actions`.

Avoid `--allow-outside-files` unless you deliberately want to allow outside-repo
paths without a prompt.

## Important Precautions

- Review `git diff` after any run that used `--apply-actions`.
- Start with local Ollama for private or sensitive code.
- Use hosted providers only when you are comfortable sending the selected
  context to that external provider.
- Keep API keys in environment variables, not files.
- Do not pass broad directories or secrets as context.
- The action loop can write files and run commands inside the repo. Treat it as
  a coding assistant, not as a fully trusted autonomous agent.

Useful checks after a run:

```powershell
git diff
git status --short
python -m uv run pytest tests\test_repo_coding_assistant_example.py
```

## Quick Command Templates

Local answer only:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --start-ollama
```

Local with file/command actions:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --provider ollama --model qwen2.5-coder:14b `
  --execute --apply-actions --start-ollama
```

OpenAI with file/command actions:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --privacy external_allowed `
  --provider openai --model gpt-5-mini `
  --execute --apply-actions
```

Requesty with file/command actions:

```powershell
.\scripts\repo-assistant.ps1 `
  "YOUR REQUEST" `
  --file path\to\file.py `
  --privacy external_allowed `
  --provider requesty --model openai/gpt-5.1 `
  --execute --apply-actions
```
## User-started research task scheduling

The foreground scheduler reuses the orchestrated run SQLite database. Planning
and listing contact no provider and load no model. Definitions store their full
prompt locally; list output shows only IDs, state and allocations.

```powershell
uv run --no-sync python -m ai_provider.task_scheduler plan public-python --prompt "Research public Python cancellation contracts" --model qwen3:8b --required-minutes 90
uv run --no-sync python -m ai_provider.task_scheduler list
```

When local compute is explicitly available, a selected sequence can be started:

```powershell
uv run --no-sync python -m ai_provider.task_scheduler run public-python --start --local-compute-available --available-minutes 110 --handoff-minutes 10
```

The example is an execution command, not authorization to start it during a
model-free implementation session. Put `--database PATH` before the subcommand
to select another application database. Tasks run sequentially in supplied order;
the first non-fitting task or failed worker stops the sequence. No waiting task
is shortened, reordered or started automatically. Each allocation includes
preparation; the supervisor receives its remaining task deadline. The ten-minute
default handoff reserve is outside the execution window.

Only existing supervised research workers are supported, with local-only Ollama,
free-only billing and trusted-local research tool controls. The scheduler does
not start an Ollama service. Existing public retrieval/search permissions and
receipt controls still apply. Stopping the owned worker tree does not guarantee
an independent Ollama server stops computing. Distinct concurrent scheduler
invocations are not a global queue; claims protect each definition from duplicate
execution. Task completion is execution status, not a factual-quality certificate.

Use `defer TASK --reason TEXT` for a planned task. After verifying a stale running
worker has stopped, use `fail-interrupted TASK --reason TEXT` to record failure;
that command does not kill processes. Terminal definitions are not automatically
retried or resumed; plan a new ID for another attempt. Historical run/stage records
are preserved when the additive task table is initialized.

Research supervisor failure finalization also survives a broken progress-output
consumer: queued run IDs are still parsed, durable handoff state is recorded, and
the original exception is preserved. An optional final status log is written
before attempting to display it. This does not turn an interrupted worker into a
successful research result.
