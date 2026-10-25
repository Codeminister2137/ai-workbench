# Current task — UNATTENDED until 2026-10-25T13:00:00Z / 14:00 CET

**Status: INCOMPLETE; ACTIVE WINDOW.** Owner selected A (restricted reviewed
non-sensitive input) and requested B (general repository protection) in plans.
Actual start 07:45:35Z / 08:45:35 CET; fixed deadline 13:00Z / 14:00 CET today.
Plan: `docs/plans/unattended-work-plan.md`. Stop admissions 12:45Z, reserve 15 min.
Current action: prepare a fresh two-phase Go/local-support CLI acceptance at
`artifacts/cli-clean-workflow-20261025h`, using e's protected coding/frozen-review
fixture with g's production-aligned auxiliary handling. No new live launch yet.
Preparation script: `artifacts/unattended-20261025-0745/prepare_h.py` (not run yet).
Record the current-source checkpoint, fresh hashes, full offline controls,
scripted workflow/audit and owned-process smoke before any live activation.

Startup rolling sleep PID 62192, receipt
`artifacts/unattended-20261025-0745/sleep-startup.json`, cancel sibling
`sleep-startup.cancel`. Latest verified due approximately 08:46Z / 09:46 local;
read the receipt for exact due time; renew next by 08:26Z and before long work.
Default sleep ten minutes after finishing, with verified timer replacement.
Owner command `.\cancel-sleep.cmd`; old October 23 stale receipt may still warn.

Implementation committed in `2532665`: `ai_agent.reviewed_task` is a one-request path
without implicit repo context/history/tools/shell. Explicit confirmation plus an
exact input digest are required. `reviewed_non_sensitive_sha256` is separate from
ADR-063's public/synthetic declaration. ADR-069 records owner intent; B is planned
in `docs/repo-assistant/restricted-input-plan.md`. 160 focused tests passed after
correcting synthetic fixture IDs and Windows newline setup; no product boundary
was loosened to make those tests pass. Full registered suite: 2892 workspace,
38 Council, 84 job-search passed; 3 skips. Ruff/check/format and Pyright clean.
First restricted synthetic live trial a sent one exact 253-byte task after two
metadata GETs, no tools/ambient history, then received HTTP 429. Error body safely
identified limit_source=upstream_provider_shared_pool and matching upstream
rate-limit signature. This is upstream capacity, not a privacy/admission failure.
No retry, paid fallback, purchase or successful-quality claim. Evidence:
`artifacts/unattended-20261025-0745/restricted-live-result.json`; scope consumed.

Independent concrete recording defect fixed: early `_run_coding_prompt_with_fallback`
ProviderError previously left persisted run/stages running while CLI printed failure.
Two pre-fix reproductions preserved in preparation-recording-before.log; the new
path records the already-known initial review/plan, failed implementation phase
with category/provider/cause label, skipped later work, failed handoff/run and
failed-request elapsed time. 70 focused checks and all 1152 registered CLI checks
passed; Ruff and Pyright clean. No real model was involved in this correction.

Go read-only readiness at 08:08Z: rolling 100% remaining, weekly 10% remaining,
monthly 55% remaining (private artifact go-readiness.json). No capacity-to-call
conversion is justified. Use original finite admission/Extra Usage disabled;
do not repeat a refusal or silently change route/billing. `python -m` emitted a
known runpy warning because ai_provider.__init__ imports go_source_info before
module execution; the metadata observation itself succeeded.

Fresh h planned deviations from inherited fixture: same 32 total calls/40 tools/
7200 seconds, phases20/12 calls and 4500/2400 seconds,300cleanup,600per request;
Go16000 output/local16384 output/context65536. Preserve full root instructions,
protected originals, oracle, actual tests/reports and owned cleanup. Port only g's
auxiliary classification, not its single-review workflow. Allow updates ONLY to
CURRENT_CONTEXT and active window plan during supervision; all executable code,
inputs, root instructions and HEAD seals stay exact. This is a prospective
fixture accommodation for tracked handoff files, not a production-policy bypass.

## Verified state

- Branch `feature/restricted-reviewed-input`, started from develop `3d7e020`;
  local `origin/develop` matched at startup (no fresh fetch).
  Initial working tree was clean. Yesterday's pending-push reminder was stale.
- OpenRouter free route and harness support are implemented. The attempted
  fallback-attempt recording change was reverted in `45380c2`; only switch-causing
  attempts belong in `fallback_attempts`. Terminal failures remain in the CLI's
  effective route/failure fields. Preserve the original consumed evidence.
- Fresh focused validation: **223 passed in 3.56s**, covering fallback acceptance,
  execution, free-provider fallback, error propagation and OpenRouter free guards.
  Python selected through PyCharm: C:/Users/Jakub/AppData/Local/Python/bin/python.exe.
- Baseline assessment corrected to distinguish completed bounded Requesty fallback
  from remaining clean integrated acceptance, scrutiny-fed repair and installed-
  client continuation. No historical run was replayed or regraded.

## Next imperative actions and completion condition

1. Keep A's consumed free trial preserved. Complete its docs/result bookkeeping,
   then prepare the next baseline acceptance slice; no reason to repeat the
   upstream-capacity failure. No purchase or broad privacy bypass is authorized.
2. Prepare the next concrete clean CLI workflow/scrutiny-repair acceptance slice
   using `docs/repo-assistant/baseline-gap.md`, `acceptance-criteria.md` and the
   preserved October 24 evidence. Prepare and verify offline before fresh named
   bounded inference. M5 allowance limits do not block this independent work.
3. Follow the active ledger and timer checkpoints through the fixed deadline;
   continue independent work when a candidate needs a decision or allowance.

Completion requires the selected OpenRouter behavior to be implemented/validated
or explicitly deferred by the owner, and concrete next CLI acceptance preparation
with honest evidence limits. General CLI baseline acceptance remains incomplete.

## OpenRouter investigation completed — data-boundary design remains open

Latest owner direction: investigate credits, privacy terms and actual payloads;
"As long as we're not sending really private data, or api keys, it's fine for now."
This is conditional acceptance of ordinary non-sensitive repository content, not
a requirement that every allowed byte already be public. Do not ask the owner to
repeat that tolerance; determine how the complete workflow can honor it.

Official sources rechecked and dated findings added to
`packages/ai_provider/docs/source-state.md`, October 25 section. $10 purchased
credits raises advertised free quota to 1,000/day (20/minute); estimated card
checkout about $10.80 before taxes using the official $0.80 minimum fee, subject
to checkout verification. Credits can expire after 365 days. No purchase made.
Free-plan routing documentation conflict persists. Selected free route still has
one Google AI Studio endpoint; Google ZDR enforcement excludes it. General Google
terms differ for EEA/UK/Swiss users, but actual gateway upstream-account/region
terms remain unestablished. Actual account privacy opt-ins were not inspected.

Concrete data-boundary gap: default prompt context can include AGENTS and the
handoff; coding-chat/fallback add visible history. Authorized workspace reads can
read `.env`, shell commands inherit the process environment, and tool output is
added to subsequent messages without secret filtering. No evidence of actual
credential leakage was found or claimed. A local dummy-only capture proves both
fake file and fake printed-environment values reach the next composed request;
two captured requests, no networking, temporary workspace removed. Evidence:
`artifacts/openrouter-privacy-review-20261025/offline-observations.json` and README.

Current recommendation: defer purchase and keep ordinary OpenRouter use refused
until complete task inputs and subsequent tool/history data meet the owner's
condition. A credential-free reviewed task scope can enable limited work sooner;
general repository access requires a broader content/command boundary. Isolation
of files alone is not an OS sandbox if arbitrary shell access remains.

### Earlier options (historical, no owner selection yet)

ADR-063 requires every complete composed request (instructions, history, schemas,
tool results and continuations) to be explicitly public/synthetic and approved for
possible retention/training. Low-risk classification alone is insufficient. A
one-time initial-prompt flag cannot automatically attest later agent-loop data.

Options presented in the attended conversation:
- Leave ordinary use disabled while preparing explicit public/synthetic use:
  preserves privacy and costs nothing; delays general free capacity.
- Approve a CLI attestation design: no purchase, enables wholly public/synthetic
  tasks; requires per-request/continuation classification and operator burden,
  and does not enable general private repository work.
- Investigate credit purchase and privacy terms: costs money and may raise free
  quota; credit purchase is a proxy and does not itself establish entitlement.
- Continuing past CONFIGURATION errors is orthogonal: may improve availability
  but could mask configuration defects and does not unlock the route itself.

The complete-input public/synthetic contract below describes existing ADR-063,
not the owner's newly clarified non-sensitive-data tolerance. A concrete design
must represent that tolerance honestly rather than falsely labelling private-but-
non-sensitive material public/synthetic. Do not change the legacy attestation's
meaning or silently grant arbitrary shell/read access as a privacy guarantee.

## Attended return and power state

The prior unattended window began 2026-10-24 17:20Z / 19:20 Warsaw and had a fixed
20:00Z / 22:00 Warsaw deadline. It was interrupted by the reported usage limit;
exact last execution and interruption duration are unknown. Last saved plan
checkpoint: 17:45Z. Later commits exist; do not equate that checkpoint with stop.
The preserved startup receipt records sleep_requested at 19:50:00Z and
sleep_api_returned_success at 21:53:49Z. This does not independently prove the
Windows suspend/resume transition. No retrospective completion sleep is scheduled.

On attended return, `.\cancel-sleep.cmd` broadcast cancellation but reported a
missing acknowledgement from the October 23 stale scheduled receipt (PID 47516).
Both that PID and yesterday's helper PID 63220 are absent; process inspection
found no running matching sleep/acceptance worker. Preserve stale receipt, do not
forge a sleep_cancelled acknowledgement. Why the October 23 helper exited is
unknown; the five-second cancellation check intentionally reports missing acks.
Future all-timer cancellation can still report that historical receipt.

## Continuing boundaries and context

Free first when quality/privacy/capabilities permit (ADR-068); no paid overage,
new private payloads, billing/model switches, raw prompt/private reasoning logging
or credential exposure. Local auxiliary review/scrutiny remains the default
(ADR-025); standing comparable bounded Go acceptance authority remains, with fresh
named bounds and live admission. Extra Usage was owner-confirmed disabled.

Relevant private plans: `docs/plans/repo-assistant-cli-parity-plan.md` and
`docs/plans/opencode-go-integration-first-20261022.md`; tracked roadmap and baseline
assessment establish newer completed integration work. M5 installed-client parity
was blocked yesterday by Copilot/Kiro capacity; recheck metadata before relying on
those observations for a fresh live run. Do not rerun offline C1-C6 merely for M5.

Historical handoff, full October 24 evidence paths and original pending decision
brief are preserved in `docs/session-history.md`. Yesterday's private window plan
is retained at `docs/plans/unattended-work-plan.md`, marked interrupted/expired.
