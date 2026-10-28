# Session History

## 2026-10-28 — local Operator release gates and availability review

The owner authorized useful development spending covered by existing approved
hackathon credits/allowances for the remaining hackathon, with no owner-funded
charges or overage. This supersedes earlier proposed session/cumulative dollar
ceilings; finite per-run bounds and actual credit-only admission remain required.
Recording, public Operator pushes and submission remain separately unapproved.

Prepared a private local Operator clone from external-actions branch 3213b3d.
Local commit 68e684b reconciles stale release-checklist wording with current
owner authorization; its patch remains private and unapplied to the sibling.
Fresh locked-source and independent-wheel runs each passed 142 tests and 69
subtests, with 8 skips. Wheel/sdist builds and known-secret/private-identifier
scans passed. No recording, public push, submission, hosted deployment or judge
grant occurred. Historical hosted/Docker evidence was not rerun against this
candidate. Exact release scope and judge delivery remain owner decisions.

Reviewed cross-source availability using existing neutral records. Corrected
OpenRouter invalid numeric observations and malformed-list handling without
changing routing. The [review](repo-assistant/model-availability-review.md)
maps existing readers, unknowns and the recommended advisory next slice.
Validation: 754 provider tests, Ruff and Pyright pass; the registered final
workspace check passed 3,037 root tests / 24 skips, 38 Council and 84 job-search.

Further private C6 preparation adds fixed-origin bounded forwarding, exact-byte
automated assessment controls and Windows outer process-tree ownership. Nineteen
admission/forwarding/checkpoint controls and three actual process controls pass.
All C6 workflow model/reviewer outputs remain scripted. Current account facts
and a reviewed activation seal are still required; no live C6 run occurred.

## 2026-10-28 — shared Responses support and C6 offline foreground rehearsal

During the owner-authorized window ending15:00Warsaw/Budapest,implemented shared
Responses tools and stateless native continuation (ADR-073). Source,streaming,
failure,origin isolation and actual file-tool loops pass;739provider tests and
Pyright pass. Registered full validation after updating the tools-incapable fixture
passes3,022root/24skips,Council38and job-search84. Earlier instruction-budget
overflow was caused by repeated Git wording;semantic consolidation preserves the
new branch policy within the existing64kdefault. Failed evidence remains private.

Fresh private C6 preparation drives one actual foreground CLI through two turns,
a labelled quota-triggered protocol switch,and the same running owned process.
Independent session/history/instruction/protected-input/index/cleanup checks pass;
foreign-path and frozen-write controls contain their attempts. Model,auxiliary and
scrutiny outputs are scripted;source/companion are host reference data. Live C6
remains incomplete;credit-only admission facts and a fresh live controller are
still required. No model call or production quality promotion is claimed.
Evidence:`artifacts/cli-c6-continuity-20261028af/ASSESSMENT.md`.

## 2026-10-28 — bounded Modal task measured; coding failed and app stopped

After the owner supplied current credit headroom, ran one fresh synthetic
Workbench normalization task. Readiness took120.312seconds; its only model call
took11.5458seconds and reported673input/170output tokens. The model printed
proposed tool calls as text; zero tools ran, source stayed unchanged and independent
validation failed. No inference retry or host-authored recovery was substituted.
The measurement slice is complete with a failed coding outcome, not accepted
general coding/tool quality.

The trial stopped its inference app. Immediate inventory was still stopping, so
the receipt withheld cleanup success; later read-only inventory verified stopped
and zero tasks. Approximate GPU-only costUSD0.032 from observed app lifetime and
account rate; exact total remains unknown and excludes no costs by assumption.
Evidence:private `artifacts/modal-workbench-20261028b/ASSESSMENT.md` and receipts.

An earlier attempt a stopped at the first startup503 before inference. Diagnosis
confirmed Modal Servers reject requests until a replica is ready; b declared a
bounded503readiness wait and preserved response bodies. Both attempts and verdicts
remain unchanged. Seven offline lifecycle controls and six adapter tests pass;
deployment lint passes. Source now enables Hermes tools and caps scaling at one
container; runbook/provider-state notes distinguish readiness from inference retry.

Next C6 is at an existing owner decision:trial-only route-limit trigger versus a
new in-session route command versus omitting cross-route coverage. A private
labelled proxy is recommended; no C6 inference or disputed implementation started.

## 2026-10-28 — enforce working branches before edits

Owner corrected direct development on develop. Created
`fix/modal-workbench-acceptance-20261028` at `b7ad1b1` and carried all uncommitted
task edits across; develop was not advanced. AGENTS and workflow guides now
require a focused branch before any repository edit, including documentation and
mechanical fixes, unless the owner explicitly authorizes a task-specific direct
edit exception. Removed the contradictory small-fix exception and corrected the
local handoff's instruction to work directly on develop.

Owner also supplied current Modal dashboard credit figures privately. The
remaining-credit blocker is resolved; the workspace net-spend setting remains
unknown and was not changed. Credit admission uses a finite compute bound with
verified headroom rather than silently imposing the recommended zero-spend setting.

## 2026-10-28 — Modal Workbench task prepared offline

Owner selected Modal measurement, C6 continuity, Operator release gates and model
availability work in that order, on develop. Before deploying, investigation found
that the Qwen server lacked vLLM automatic tool-choice/Hermes parsing flags. Added
the documented flags and updated deployment/provider references. This host change
is not live tool-calling acceptance.

Private preparation `artifacts/modal-workbench-20261028a/` contains fresh finite
bounds and a scripted Workbench AgentLoop read/edit/validate rehearsal: 400
independent normalization cases pass, including Unicode and input preservation.
Focused Modal adapter tests: 6 passed; deployment Ruff/format and full Pyright pass.
Five offline lifecycle controls cover cleanup after failed deployment/task, credit
refusal and refusal to report success while the app remains active.
Read-only account metadata was collected without inference or deployment; it does
not establish remaining eligible credit or the workspace net-spend limit. Owner
dashboard facts are pending before live admission under the no-owner-funds rule.
Existing standalone Modal SDK is usable without a dependency installation.

No live task, deployment, recording, public push or submission was performed;
slices 2–4 have not started. The original C6 preparation remains unchanged.

## 2026-10-28 — Modal inference endpoint deployed and verified

Branch `feature/go-cli-completion-acceptance-20261025`; commits `cb3eca5`
(Workbench→Remote AI Operator external-actions bridge) and `1d66ad7`
(Modal vLLM deployment). Working tree clean; full root suite **2979 passed,
9 skipped**; Ruff/format clean.

Completed slices:
- Added `deploy/modal/qwen25-coder-7b/modal_app.py` + README to serve
  `Qwen/Qwen2.5-Coder-7B-Instruct` on an L4 GPU with vLLM 0.21.0.
- Created Modal secret `modal-runtime-api-key` (`MODAL_API_KEY`/`VLLM_API_KEY`)
  and wrote the key to local `.env`.
- Deployed to `https://kubajaworski999--ai-projects-qwen25-coder-7b-instruct-server.us-east.modal.direct/v1`,
  verified `/health`, `/v1/models` and a `/v1/chat/completions` probe.
- Worked around FlashInfer JIT compile failure with `VLLM_USE_FLASHINFER_SAMPLER=0`.
- Wired the live `base_url` into the catalog route
  `modal/qwen/qwen2.5-coder-7b-instruct`.
- Added `modal` to a new `modal-deploy` dependency group.
- Stopped the app after verification to preserve credits.

Also completed earlier in the same feature branch: Meta Model API route,
Modal runtime billing-source split, and the neutral Workbench↔Remote AI
Operator `/api/external-actions` contract with UI support.

Open / blocked:
- Remote AI Operator hackathon release (video, public push, form submission)
  remains **BLOCKED** on explicit owner release authorization.
- Hosted judge Meta grant/access mechanism still needs owner decision and a
  finite allowance.
- C6 process-continuity live trial and `meta-baseline-gates-v1` remain ready but
  not started.

## 2026-10-28 — branch cleanup and push to develop

Merged the stale `feature/go-cli-completion-acceptance-20261025` branch into
`develop` (merge commit `3f0f2b8`), fixed post-merge pyright/type issues
(`031803e`: httpx dependency, test enum literals, response/client protocols),
configured pyright `venvPath`/`venv`, and pushed `develop` to `origin/develop`.
`feature/go-cli-completion-acceptance-20261025` deleted locally.

## 2026-10-26 — attended closeout after usage-limit interruption

Unattended window started14:41:41Z/15:41:41CET with fixed19Z/20local deadline.
Last confirmed checkpoint16:34:41Z; interrupted full-test log lastwrite16:36:04Z.
Automatic approval review then rejected the next command because usage was exhausted;
the command did not execute. No work is claimed for the gap. Owner resumed attended
work at20:23local; clock verified19:23:51Z. Immediate slice was validated and closed;
no additional paid trial was started. Wider C6/M4/frozen-review work remains incomplete.

Host fixes retain bounded prior native receipts for repair and initial/repair history
for re-review, reset observations between invocations, deliver process receipts, skip
NUL-bearing/invalid UTF-8 search content and support base-relative recursive globs.
Four additional cases include real SQLite and owned-child effects. Focused84passed;
final registered3,077passed/3skipped,Ruff/format/Pyright pass. Original ab/ac/ad results
and27,560historical files/509protected ad inputs/index remain unchanged. Logs:
`artifacts/repair-search-process-attended-full-20261026.log` and
`artifacts/repair-search-process-pyright-20261026.log`.

Current window sleep receipt records cancellation18:30:08Z/19:30:08local, helper94312
absent. Attended CancelAll signalled all timers; an old October23 receipt lacks its
acknowledgement, but all eight registered helper PIDs are absent. Original receipts
are preserved; no new timer or physical sleep transition is claimed. The old stale
registration remains a documented tooling follow-up, outside this immediate slice.

## 2026-10-26 — ad C5 effects verified; original bound stop before report

Fresh ad on76bbd3c:9Go/1local,21returnedproposals/20executed tools,82.14seconds.
Actual semantic navigation, nonmutating preview/exact plan apply changed two intended
sources; eight model cases, host rerun, semantic oracle and applied hashes pass.
Next proposal crossed original20-tool initial cap; no report/required scrutiny/
frozen review.509protected inputs/27,560history/index and owned cleanup verified.
Consumed incomplete,not extended/replayed/regraded. Search returned runtime SQLite
content and recursive glob missed tests; both separately reproduced for host repair.
Assessment: `artifacts/cli-semantic-postflight-20261026ad/final-assessment.md`.

## 2026-10-26 — host semantic scrutiny evidence correction

C5 preparation reproduced scrutiny dropping real Jedi navigation, preview and apply
receipts. Host correction forwards these tools and selected bounded plan/path/hash
metadata, including partial errors and explicit omitted-file counts. Real Jedi
nonmutating preview/two-file apply/reused-plan refusal and bounded metadata cases
pass; full registered3,073passed/3skipped,Ruff/format/Pyright pass. No permission,
rename lifetime, provider or public API change. Live capability proof remains open.

## 2026-10-26 — ac frozen review stopped within task scope guards

Fresh ac on981072b:6Go/1local,19returned proposals/17executed tools,92.40seconds.
The fixture rejected run_command outside frozen-review authorization before batch
execution; exact command intent unknown because only argument digest retained.
No candidate report/required scrutiny.507inputs/26,500history/index and owned cleanup
verified;host4regression cases pass. Actual public HTTP200/body112744bytes/SHA256
and private-network zero-connection refusal verified,without provenance-delivery
completion. Original consumed result retained. Assessment:
`artifacts/cli-public-postflight-20261026ac/final-assessment.md`.

## 2026-10-26 — stopped ab and host scrutiny-evidence correction

ab observed active CPython3.14.4 versus a fake workspace hint,one real pytest pass,
expected RuffF821 and Pyrightassignment-type return1. Required scrutiny questioned
the version missing from its evidence and treated host execution status as candidate
text. Repair exhausted24-tool cap:10Go/2local,26returned proposals20executed6rejected,
174.83seconds.516frozen inputs/24,374history/index and cleanup verified. Accepted
final report/re-review absent;original candidate/reviewer/stages preserved,not resumed.
Host source correction retains recent runtime/fetch receipts,last successful fetch
before refusal,and separates host evidence from raw candidate text. Four regressions
exercise actual tools/budget pressure/real prompt composition. Final full3,071pass/
3skip,Ruff/format/Pyright pass. This is implementation evidence,not automatic reviewer
accuracy or live scrutiny-fed repair. C4 model-free officialPython-json fetch succeeds
with112744retainedbytes/digest and private-network refusal;fresh frozen fix review/
C4live question is next. Active unattended window/deadline remain in the private plan.

## 2026-10-26 — unattended start and native-Go portable-skill case aa

Owner authorized a new unattended window14:41:41Z/15:41:41CET until19Z/20local;
20minutecloseoutreserve and rolling sleep fallback recorded in the private active
plan. Prior usage-limit interruption is not work. Fresh sealed aa was unconsumed,
successful smoke confirmed,current entitlement/privacy/quota refreshed before launch.
Actual native-Go single-shot CLI selected review-repo-change with checked Git/tool
prerequisites,complete root/nested instructions and six-tool read_only authority.
Both staged/unstaged seeded regressions were identified with correct concreteexamples;
no model test execution/writes occurred or were claimed. Required scrutiny passed.
Six Go/two local calls,eightproposals,114.98seconds;511frozeninputs/22249history/index
unchanged;rawreport/hostreceipts and ownedcleanup verified. Three passing host checks
cover identity/prerequisites only. Reviewprecisionqualified: "any discount>0" overlooks
50%/zeroprice equality; host discloses exact condition,without replacing rawreport or
claiming automatic CLI correction. Selected C2 delivery/authority is verified,not
unqualified reviewer accuracy or fullM2/M5. Next independent candidate:C3 runtime and
real test/lint/type diagnostics. Evidence: artifacts/cli-skill-postflight-20261026aa/.

## 2026-10-26 — z synthetic coding and cold frozen review completed

Fresh z uses production a373098 and a small status-counting task, distinct from
consumed span/link/notice trials. The model implements one-pass normalized counts,
adds three meaningful companions, executes 16 cases and delivers a supported report.
A second cold worker retains the original task/report in one saved conversation,
reviews exact host-accepted frozen bytes read-only, executes the same 16 cases and
delivers a supported substantive review. Required scrutiny passes both phases with
no format issues. Independent reruns and separate host oracles pass. No live repair,
host source recovery, replacement reports, bounds extensions or regrading occurred.
Sixteen Go/four local calls, 24 proposals, 520.94 seconds; all 508 protected inputs,
16,811 historical files and scratch index unchanged; raw reports/scoped metadata,
two exited workers and owned runtime/listener cleanup verified. Source stays fixture-
only. Narrow coding/current-report/cold-review acceptance is complete; general CLI/
M4/capability/fallback and successful live scrutiny-fed repair remain incomplete.
Evidence: artifacts/cli-status-continuity-20261026z/ and cli-status-postflight-20261026z/.

## 2026-10-26 — y frozen review of current host corrections completed

Fresh y reviewed the reference-preview correction and native reply-ceiling notice at
405cb52. Ten Go/two local calls, 19 proposals, 234.40 seconds; required scrutiny passed
without format limitations. Model execution and independent host rerun passed all
182 selected cases. All 509 frozen inputs, 15,231 prior evidence files, fixture index,
raw report/host metadata and owned cleanup verified. Semantic assessment supports
current source/test/effect claims. Two proposed commands were refused before execution;
the report's one executed test run is accurate. No live repair was needed or claimed.
Full registered root checks: 3,067 passed/3 skipped; Ruff/format/Pyright pass.
Evidence: artifacts/cli-budget-review-20261026y/ and cli-budget-postflight-20261026y/.
The source fixes remain host recovery/implementation; w/x remain consumed incomplete.
General paid CLI/M4/capability acceptance and successful live scrutiny-fed repair
remain incomplete. No push/merge, private payload, billing change or trial extension.

## 2026-10-26 — action-budget visibility after consumed x

x used ten Go/two local completions and 15 read/search/Git proposals in 94.62seconds,
exhausting the correctly aligned ten-round initial limit without edits/tests/report.
Required scrutiny failed on the absent response; frozen review was not reached.
All 506 protected inputs and 13,106 prior evidence files and owned cleanup verified.
The host implements the six-line static native reply-ceiling notice with three
actual-request cases and an updated exact-system assertion.180 focused cases pass.
This is host-written code; x remains consumed incomplete. Evidence:
artifacts/cli-action-budget-postflight-20261026x/. Fresh frozen review is still due.

## 2026-10-26 — reference recovery after consumed w

w stopped incomplete at its declared host ten-primary-reply initial cap. Ten Go/
one local calls, 15 proposals, 203.14 seconds; model tests failed three of 51 cases,
then the model corrected the candidate but did not revalidate/report/reach required
scrutiny or frozen review. Host audit preserved all 505 protected inputs and 9,937
historical files and verified owned cleanup. Later host-only 51 tests passed.
The root adopts the one-line reference-marker fix with six independent host cases,
explicitly as host recovery. See artifacts/cli-reference-postflight-20261026w/.
The fixture configured 17 production rounds but capped initial coding at ten replies;
future fresh coding must align those bounds. No consumed result was resumed/regraded.

## 2026-10-26 artifact links and real preview defect

Corrected Windows chat-link guidance to slash-prefixed absolute local targets and
removed a stale current-roadmap pending-decision statement. Client rendering remains
unconfirmed. Reproduced a separate real CLI defect: 200-character preview truncation
split long inline Markdown destinations while the full report retained them.

Fresh u attempted model coding then cold-restart frozen review. A too-narrow host
AST guard rejected private preview helpers, so u stopped incomplete before tests,
final report or review. 8 Go/1 local calls, 15 proposals, 282.74 seconds; 504 protected inputs,
5,743 historical files and owned cleanup verified. The original candidate/five tests
remain unchanged. Host-only tests found three escaped/angle-path gaps. The final
root implementation a2bb69c is a smaller host-written seven-line fallback with eleven
host regressions; it is not a promoted model solution or retrospective u acceptance.

Fresh v reviewed the current host fix under new sealed bounds. 25 guards, scripted
report correction/revalidation/re-review, 39 selected cases, negative digest calibration,
smoke and current admission passed before paid inference. Live v: 7 Go/2 local, 11 proposals,
152.99 seconds; 39 tests and required scrutiny passed. Independent checks confirmed 507
inputs/8,364 historical files unchanged, raw report retention and owned cleanup. Minor
prose-count errors are qualified in its postflight assessment; original reports remain.
Current full validation passed 3,058 tests with three skips; Ruff/format/Pyright passed.
No push/merge.
Broader M4, capabilities and successful live scrutiny-fed repair remain incomplete.

## 2026-10-26 scoped host observations and fresh closeout acceptance

The owner approved ADR-070's host facts plus repository/tool-action report scope.
Commit e999366 implements it in closeout delivery, raw conversation metadata/history
and required-review context. Commit 361e033 clarifies focused native inspection
without changing reads or trimming required instructions/history.

Broader frozen questions r and s stopped incomplete: r exhausted estimated context
after whole-file reads; s exceeded its initial tool reserve. Their inputs, original
results and cleanup evidence remain preserved. Neither was resumed or regraded.
The current baseline assessment records exact causes, usage and independent checks.

Fresh t reduced the question to the closeout envelope and four protected cases.
Preparation passed 25 guards, scripted report-only correction/revalidation/re-review,
a negative digest calibration and smoke checks before current privacy/quota admission.
Live t used four Go/two local calls and ten proposals in 102.33 seconds. The primary
report, tests, source identity and effect scope were independently checked. Required
frozen scrutiny passed with disclosed report-format limitations under ADR-066; all
506 inputs and 4,174 historical files stayed unchanged and owned cleanup was verified.
The raw response is retained exactly; display applies existing duplicate-heading
normalization. A mistaken independent display-identity assertion was corrected with
its original failure retained, without changing the trial or any model response.

The narrow completion/report-fidelity question is established. General CLI parity,
broader continuity/capability milestones and live scrutiny-fed repair remain open.
Final registered validation passed 3,047 tests with three skips; Pyright reported
zero errors, and source lint/format checks passed. No merge or push was performed.

## 2026-10-25 public-layout review and reporting decision boundary

Frozen review o passed mechanical/required-scrutiny gates but incorrectly claimed
the six tests checked imported-source byte identity; a host guard performed that
comparison. Fresh p made three identity comparisons visible in the protected tests,
with a deterministic mismatched-copy rejection, but live p stopped at a pre-execution
directory guard before tests/report. The exact rejected path was discarded; the
combined guard cannot establish whether it was an escape or an unlisted in-root path.
Its failed-batch proposal count was also missing. All inputs and owned cleanup were
preserved. These consumed outcomes were not replayed or regraded.

Fresh q restored normal directory navigation in a history-free public Git archive:
499 committed files, six declared probe/config inputs, no ignored private files or
original Git/recovery history. New receipts preserve proposal counts and safe path
classification. Its 25 guards and scripted report-only correction/revalidation/
re-review passed. Live q used six Go/two local calls and 16 primary tool proposals
in 272.83 seconds. Nine tests passed; 505 inputs and 1,000 historical evidence files
were unchanged, required scrutiny passed and owned cleanup was independently checked.
Technical findings and test/manifest attribution were supported. The final report's
unqualified no-network sentence still lacks an explicit actor boundary.

The owner was presented with two concrete prospective closeout examples: strict
host-wide effect claims, or explicit host facts with agent-action scope. The latter
was recommended for clarity without another model/service, but remains a proposal.
No reporting/acceptance contract was changed, no consumed result promoted, and no
further paid trial started while that material decision was pending.

## 2026-10-25 frozen review n and negative reporting scope

Fresh ordinary tool-enabled review n supported the host invocation-scope patch;
required local scrutiny passed, six frozen inputs stayed unchanged, three tests
passed and owned cleanup was verified. It used eight Go/two local calls, ten tool
proposals and 296.08 seconds. Its original controller completed mechanically.
Independent assessment qualified report fidelity because the report claimed no
network calls although inference used provider traffic. No model-authored edit or
optional network-tool call was observed; those narrower claims are supported.

The prospective instruction correction scopes negative side-effect claims in all
primary prompt modes and response scrutiny. It introduces no new privacy, transport,
approval, persisted-data or verdict policy. Original evidence remains consumed;
external detection does not prove the ordinary workflow caught the claim.

The reporting correction passed 104 focused tests, full registered suites with
3,043 passes/three skips, Ruff and configured Pyright. Live semantic acceptance
remains a separately bounded question.

## 2026-10-25 continuity m and scrutiny evidence scope

Fresh three-process trial m preserved the saved conversation through diagnosis,
clarified coding and frozen inspection. Correct model-authored source and five
companions passed 11 tests and 1,593 independent oracle cases; protected and frozen
inputs were preserved. Required local scrutiny falsely attributed coding-phase
changes to frozen review, and the saved draft overclaimed runtime bookkeeping
preservation. The workflow stopped incomplete. Its 14 Go/four local calls,
20 tool proposals and 480.20 seconds stayed within the original bounds; owned
worker/runtime cleanup was verified. Original evidence remains consumed.

Investigation exposed ambiguous production evidence scope. The prospective fix
labels invocation-start fingerprints separately from Git state, marks missing
baselines unknown, identifies current-attempt receipts and states runtime
bookkeeping exclusions. Three regression cases cover actual supplied review
prompts for unchanged, changed and unavailable baselines. No raw m prompt was
logged; the exact inference cause remains unknown. No verdict policy change or
retroactive acceptance is implied.

The framing correction passed 63 focused tests, a final 40-test scrutiny rerun,
full registered suites (3,040 passed, three skipped), Ruff and configured Pyright.

## 2026-10-25 saved-session teardown correction

Fresh Go trials j/k diagnosed the cleanup defect but stopped at private fixture
guards before final coding reports and required frozen reviews. Original results
remain consumed/incomplete, with owned cleanup verified. Independent postflight
found lost exception chaining in k's candidate. The subsequent production fix and
eleven real-session/owned-child regressions are host-authored, separately attributed
from those trials. Terminal cleanup failure no longer skips foreground teardown;
uncertain cleanup persists interrupted state and restores active caller contexts.

The fix passed 82 focused tests, targeted Ruff lint/format and Pyright. Fresh full
registered validation passed 3,037 tests with three skips. A separately bounded
one-call static Go review found no concrete change-induced defect in six frozen
public files, which remained unchanged. That review used no tools or auxiliary/
scrutiny stages and treated supplied test results as host observations. It does
not replace the missing phases of j/k or establish general workflow parity.

The owner resumed attended work after a usage interruption. The unattended
window was superseded; its sleep receipt acknowledged cancellation and no helper
was running. An older stale registration caused a missing-ack warning. The prior
full test log ended without a result; it was preserved and fresh validation began.
No test pass or work during the interruption is inferred from that partial log.

## 2026-10-25 bounded Go coding/review completion

Fresh trial i completed the small orchestrated coding and read-only frozen-review
question within its original 32-call/40-tool/7,200-second allowance: nine Go calls,
four local support calls, 19 tools and 630.83 seconds including owned cleanup.
Independent assessment accepted both current reports, five unchanged original
tests, three additive companions, eight passing tests per phase and 3,616 oracle
cases. The review auxiliary proposed a tool in its tool-free pass; production
rejected it without execution and preserved the auxiliary-error status. Required
validation and final scrutiny passed. No live repair was needed or established.

The scoped completion/report-fidelity gate is complete; the broader roadmap is
incomplete. Existing live fallback evidence remains separate. Original h and i
receipts were preserved without replay or regrading. Assessment and cleanup
evidence are under `artifacts/go-completion-postflight-20261025i/` and original
trial evidence under `artifacts/cli-clean-workflow-20261025i/`. No production code,
provider selection, service, dependency, approval policy or billing source changed.

## 2026-10-24 allowance-derived fallback ordering; Kiro fallback target exhausted

Fallback ordering became an explicit, configurable chain. `fallback_candidates`
gained `priority`, `excluded_route_ids` and `allow_cost_escalation`; the user
config gained `fallback.priority`, `fallback.exclude` and
`fallback.allow_cost_escalation`; the CLI gained `--fallback-priority` and
`--fallback-exclude`. Priority reorders candidates only: privacy, capability and
quality filters still apply, and the task cost policy still rejects any tier it
does not permit. Fifteen tests were added; the full suite passes 2832/9 skipped.

The default order was derived from a read-only allowance inventory
(`artifacts/allowance-inventory-20261024/`) rather than from quality alone:
Codex (authenticated, weekly 31% used), Kiro (authenticated, coverage-only
allowance), OpenCode Go (unknown, executor-compatible), Copilot (client not
configured, chat bucket exhausted), Antigravity (not installed). Two hazards were
recorded instead of inferred away: Kiro reports plan coverage, not remaining
balance, and OpenRouter free has account allowance but no catalog route.

The live fallback trial `artifacts/fallback-acceptance-20261024-123206/` recorded
a genuine cross-source switch (`simulated-codex -> kiro/auto`, attempts
`codex_cli, kiro_cli`) but the Kiro target refused in its own protocol stream:
"The monthly usage limit has been reached". `passed` remained false and was not
regraded. Slice B is therefore attempted and recorded but not completed.

## 2026-10-14 free-source integration and methodology closeout

Guarded, opt-in OpenRouter integration and Gemini historical transport contracts
were completed offline. Gemini individual access is retired and refused; the
OpenRouter production Free-plan privacy refusal remains unchanged. Neither route
was promoted to a default or certified for general coding quality.

Direct synthetic checks and full CLI acceptance were kept separate. Cohere's
CLI trial produced an incorrect solution; NVIDIA's produced a correct source
edit but omitted required companion tests and did not complete review. Preserved
independent checks and cleanup establish those limited outcomes, not model ranks.

The owner accepted offline adapter/settings conformance and cumulative numeric
usage work next, retaining strict authoring/correction/freeze evidence alongside
a distinct bounded iterative test/repair acceptance. Findings and 18 research
links are preserved in [the methodology record](repo-assistant/agent-methodology-findings.md).
Future research does not displace baseline CLI or its next supervision priority.

Fresh closeout validation passed 2300 tests, with 3 skipped; Ruff, formatting and
Pyright passed. Prior dirty work was retained in focused commits. Detailed local
trial receipts, consumed grants and current account observations remain private.

This file preserves historical session handoffs from `CURRENT_CONTEXT.md`.
It is an archive — do not use it to direct new work. For current state and
next actions, read `CURRENT_CONTEXT.md`.

---

## Session — Job Search vertical slice & research acceptance analysis (2026-10-06 17:04–19:30 CEST)

The owner authorized Option B (Job Search automation) as the next application
track and authorized running the live research acceptance test using local
GPU/Ollama resources.

### Job Search Vertical Slice (Phase 1 & 2 Complete)

Implemented domain contracts and verification architecture in
`apps/job_search/job-email/`:

- `models.py`: Normalized `JobVacancy`, `CandidateProfile`, `SkillEvidence`,
  `CVVariant`, `ApplicationPackage`, and `SendReceipt`.
- `deduplication.py`: Deterministic entity name/title normalization and
  duplicate key generation to prevent duplicate applications.
- `evidence.py`: Evidence verification enforcing the rule that applications
  never invent or upgrade qualifications. Unbacked claims raise
  `ProhibitedClaimError`.
- `preparation.py`: Assembles verified application packages, tailored
  messages, and selects appropriate CV variants.
- `approval.py`: Enforces explicit human approval workflow. Mutating an
  approved package revokes approval, requiring fresh review.
- `sender.py`: Delivery abstractions decoupling preparation from sending.
  `DryRunEmailTransport` and `YagmailEmailTransport`. Raises
  `UnapprovedApplicationError` if delivery of an unapproved package is
  attempted.
- `test_job_search.py`: Comprehensive test suite. 9 passed in 0.04s; Ruff
  lint and format passed; Pyright 0 errors.

### Research Runner Acceptance Run Analysis

- Local Ollama server started with gpt-oss:20b.
- Scheduled acceptance task ran; at turn 3, serialized messages exceeded the
  strict context input budget due to multiple large fetches.
- Fixed adaptive compaction for recent tool content in
  `packages/ai_provider/src/ai_provider/research_execution.py`.
- Unit test added in `tests/test_research_tools.py`.
- Validation: 84 passed, 1 skipped; Ruff and Pyright passed.

---

## Session — CLI foundation audit and bounded work (2026-10-06)

Branch `feature/cli-readiness-and-tool-parity`. Owner confirmed offline-only
scope. Authorized unattended bounds: 2026-10-06 14:46–17:46 UTC.

ADR-046 option B added explicit `--validation-python` for built-in pytest
only. Tests added for default, explicit, custom, skip/research,
blank-command, and alternate-route readiness behavior.

C3/M5 focused validation: **136 passed, 1 skipped**. Ruff lint and
formatting passed; Pyright 0 errors. A Ruff import-order issue was corrected
in `test_validation_interpreter.py`.

Updated `AGENTS.md` and `docs/workflow.md`: routine, bounded,
repository-local checks within approved scope do not require repeated chat
readiness requests; unexpected physical terminal approval still requires
attended owner action.

Added `--list-skills`: offline JSON diagnostic listing supported local skill
sources and checking common-tool/Git prerequisites. Combined CLI foundation
suite: **150 tests, 1 skipped**; Ruff/format and Pyright passed.

Owner chose C3 option B rationale: predictable interpreter selection without
silent guessing, advancing IDE independence. Recorded as ADR-046.

---

## Session — durable decision briefs and announced terminal approvals (2026-10-06)

Strengthened `AGENTS.md` and `docs/workflow.md`: each material decision
brief must explain why the decision matters, present viable alternatives with
pros and cons for each, and provide a clear technical recommendation.
Required pre-call announcement for terminal commands that may prompt for
approval. Added user-facing notice template and mirrored rule in
`docs/repo-assistant/permissions.md`. Documentation-only.

---

## Session — remaining CLI foundation actions (2026-10-06)

Added `python_navigate`: read-only native/shared coding tool for Python
definitions and references using the already-approved optional Jedi
dependency. Validates workspace source, excludes non-Python/out-of-workspace
results, caps output at 100 results.

Focused coverage: 64 passed, 1 skipped. Ruff, formatting, Pyright passed.
`git diff --check` passed.

One unrelated stale `test_antigravity_coding_remains_excluded` assertion
deselected: it still expects the older "not verified" message while the
current implementation reports the missing scoped `permissions.allow` grant.

Investigated completed 2026-10-04 research acceptance. Fixed controller to
classify a successful-but-empty refinement attempt as explicit failure.

Remaining blockers: physical terminal shell-approval acceptance; Antigravity
project-settings UI; Codex retry deferred until 2026-10-10 08:35; research
quality acceptance needs fresh compute window.

---

## Session — durable closeout rule and shared fallback matrix (2026-10-06)

Made explicit and durable: in Copilot Chat this surface, never call
`task_complete`; finish with the normal visible assistant response.

Completed M1 offline shared-tool/approval matrix: inspection and coding
profiles across Codex, Copilot, Kiro, and Antigravity; all four approval
presets for coding. Focused matrix: 32 passed.

---

## Session — M1 executable readiness diagnostic (2026-10-06)

Added `executable_status` with `available`, `unavailable`, and
`not_applicable` states. Checks configured local paths/PATH only; does not
execute a client. Focused readiness/fallback tests: 42 passed.

---

## Session — deterministic CLI summary contract (2026-10-06)

Implemented CLI-owned closeout wrapping chat, provider, native-tool,
external-agent, and fallback responses in one visible `## **SUMMARY**`
envelope. Agent output preserved under `Agent report`. Prompt instructions
tell agents not to emit a duplicate summary.

Focused affected-route/fallback tests: 108 passed. Added regressions proving
unavailable Git is refused and selected skill instructions survive a
usage-limit route switch (44 passed). Final workspace gate: 1,295 passed, 2
skipped; Council: 21 passed. Changes remain uncommitted.

---

## Session — HTTP host lifecycle and foreground transport fixes (2026-10-05/06)

Fixed lifecycle: host close revokes all scopes, shuts down tracked sockets
and the listener, does not wait for blocked request threads, and still waits
for an already-active tool operation to finish. Added regression coverage for
partial headers/body, late request bodies after revocation, and draining an
active operation. Focused transport tests: 15 passed.

---

## Session — M1 offline feature compatibility audit (2026-10-06)

Extended offline `--fallback-readiness` to match normal shared-tool
normalization. An explicit `--skill` implies shared inspection and read-only
approval; selected skill sources and their existing prerequisite contracts
are validated. Added regression: `--codex-search` is reported as unsupported
for alternate shared-tool adapters.

M1 deterministic acceptance is complete offline. Final validation: readiness
suite 84 passed; full workspace 1,372 passed, 2 skipped; Council 21 passed.
Roadmap now records M1 as complete offline only.

---

## Session — live client acceptance (2026-10-06)

Copilot CLI 1.0.90 and Kiro CLI 2.24.0 both passed simulated Codex-limit
fallback with shared coding edits, distinct run IDs, same-handle process
polling, verified child cleanup, and unchanged protected fixture files. Both
passed `review-repo-change` skill through shared inspection/read-only tools.

Codex: usage-limit response before any tool call; deferred until 2026-10-10
08:35 (TZ unspecified).

Antigravity: headless mode auto-denies MCP requests; requires matching allow
rule in `settings.json`. Project permission only available via Antigravity
project settings UI, which is not installed. Owner approved exact
project-scoped MCP grants; next action is to configure in UI when available.

---

## Session — SDK acceptance and test-workflow (2026-10-05)

SDK mcp 2.3.0 and locked dependencies installed (via hash-checked requirements
file due to running ai-agent-mcp.exe Windows launcher lock). Official
SDK/foreground transport interoperability passes with HTTP 204 deletion.

Completed test investigation and implementation. Baseline 1125 passed/7
skipped in 158.63s; scoped fixtures and dedicated boundary tests implemented.
`scripts/run-tests.py` added with explicit provider/orchestrator/agent/cli/
research/council/live groups.

Full offline workspace: 1133 passed/1 skip in 56.14s; Council 21 passed.

---

## Session — foreground transport, IDE bridge, live process continuation (2026-10-05)

Implemented authenticated foreground MCP JSON-response HTTP host.
Per-invocation bearer scopes bind task/workspace/preset, MCP sessions,
deadline and receipts. Revoked access never carries into fallback.

Read-only IDE bridge implemented in `ai_agent.ide_bridge`. Three common
wrappers: `python_environment`, `file_diagnostics`, `symbol_info`.
`data/pycharm-mcp.json` is Git-ignored.

Live Copilot 1.0.91 and Kiro 2.24.0 continuation both passed: synthetic
initial Codex quota, real second edit under fresh run, actual process_status
on same in-flight child, protected fixture unchanged, verified child cleanup.

---

## Session — option A semantic rename, C3 diagnostics (2026-10-05/06)

Owner selected option A (optional Jedi-based preview/apply). Implemented:
pinned optional Jedi 0.20.0/Parso 0.8.7; native and shared coding tools;
owner-local five-minute plan state; complete-diff WRITE approval;
stale-plan and symlink refusal; digest-checked atomic per-file apply and
explicit partial-effect receipts.

Owner rationale: advance IDE independence. PyCharm remains permissible while
migrating. Recorded as ADR-045.

Added read-only `python_runtime` tool to native and shared coding profiles.
It reports interpreter, version, workspace `requires-python`, `.venv`
candidate, and `uv.lock` presence.

Orchestrated default `python -m pytest -q` now invokes the current process's
exact `sys.executable`. Windows command parsing now strips surrounding quotes
from quoted PowerShell path arguments.

Final offline gate: 1,290 workspace passed/2 skipped; 21 Council passed.
Ruff, formatting, Pyright, lock check, `git diff --check` all pass.

---

## Session — four-hour unattended implementation window (2026-10-05)

Ten implementation commits saved. Key areas: IDE/session/process lifecycles,
shared public docs fetch, provider stream/error contracts, source
header/body deadline cancellation, invalid provider counters handling,
continuation pages for complete research report reads, usage summarization,
research refinement empty-attempt fix, semantic rename investigation.

Final code gate: 1,266 root passed/1 skip; Council 21 passed. Ruff/Pyright
passed. Sleep performed at 2026-10-05 12:48:38 Warsaw (Kernel-Power event42).

---

## Session — shared coding approvals (ADR-041) and synthetic fallback (2026-10-05)

Completed shared terminal mutation slice (ADR-041). Opt-in `--shared-tools`
coding uses existing inspection/file/shell tools. Shared MCP calls enforce
`PermissionManager`. Every external invocation receives a fresh run ID and
task/workspace scope.

Completed deterministic synthetic shared-coding fallback after partial tool
effect without replay.

Live D3 fixed acceptance passed: GPT-OSS 20b/Ollama 0.32.5, 300 seconds,
read/edit verified. Real Copilot 1.0.91 and Kiro 2.24.0 continuation passed.

---

## Earlier sessions (2026-09-27 — 2026-10-04)

Earlier session records are available in git log messages on commits before
`17955e9`. Key milestones:

- `32104c8` Add authenticated foreground MCP host and local IDE bridge
- `477e0d5` Complete IDE acceptance and streamline workspace test checks
- `a891f0f` shared fallback/scopes/deadlines
- `51a73d6` scoped shared coding approvals and session receipts
- `f86aca5` CLI defaults (D1 complete offline)
- `72c2d81` fixed acceptance jobs (D3 complete offline, ADR-043)
- Initial orchestrator, provider, agent, and Council foundation commits

---

## Session - CLI usability and immediate handoff repair (2026-10-13)

The attended CLI work corrected actual byte-count reporting, added model-authored
assertion coverage after host-guided recovery, and repaired narrow startup-warning
classification and validation/delegation diagnostic wording. Host checks passed
2,182 tests with three skips; Ruff, formatting and Pyright passed. Model test tools
ran 19 scoped tests successfully. The subsequent local factual review failed
acceptance; daily CLI quality remains incomplete. Interrupted cleanup evidence was
reconciled separately, rather than rewritten as an observed historical transition.

Repeatedly prepending new checkpoints to the entire old CURRENT_CONTEXT.md caused
historical state to accumulate despite this archive. The full 101,393-byte local
snapshot is preserved in ignored evidence at
artifacts/attended-bytecount-assertions-20261013/current-context-before-20261013-1545.md.
It contains private session context and is deliberately kept out of tracked history.
CURRENT_CONTEXT.md was replaced with immediate state, remaining decisions and a
candidate ledger. Future updates should replace its current sections in place and
archive concise material history here, retaining private evidence locally.

The owner authorized a continuous 3.5-hour work window from 15:45 to 19:15 Warsaw
(13:45 to 17:15 UTC), with independent tasks selected when a candidate blocks.
Sleep is conditional on completion and the fixed deadline. No merge or promotion
was authorized; outbound model review remains a separate scoped decision.

## OpenRouter free-first integration (2026-10-14)

After Gemini individual sign-in refused due to verified service retirement, the
owner approved prioritizing the already requested OpenRouter free API connection.
Implemented distinct free-only provider identity/provenance and an opt-in catalog,
reusing the shared chat/tool loop and fallback admission. Every call verifies exact
free model/prices/tools and observed daily remaining requests; zero price caps,
required parameters and deny-data-collection filters are mandatory. No paid retry,
deposit, default change or quality promotion. Qwen candidate endpoint availability
unverified (public listing empty); no live key check or inference ran. Gemini grant
remains unused and does not transfer. Original tests/effects preserved in offline
host-tool checks, including interruption after quota exhaustion. Canonical full
validation2268 passed/3 skipped; affected Ruff/format/Pyright and diff checks passed.
Final source check found Free-plan data-policy-routing entitlement contradicts
unqualified routing documentation. Free/unknown-tier metadata therefore refuses
inference; existing non-free-tier account mocks validate free-model transport.
No account funding or privacy-policy weakening is implemented.
Current handoff owns next attended metadata check and fresh bounded acceptance.

---

## 2026-10-23 attended + unattended session context (archived from CURRENT_CONTEXT.md)

Archived 2026-10-23. This block was the append-only historical tail of CURRENT_CONTEXT.md.
It is preserved verbatim as history; the live handoff now stays in CURRENT_CONTEXT.md.
# CURRENT — UNATTENDED window ACTIVE (until 13:00 Warsaw / 11:00 UTC 2026-10-23) [HISTORICAL]

**Active unattended plan:** `docs/plans/unattended-work-plan.md` (scrutiny value
assessment → CLI process review → scoring mechanism A implementation; conditional
scrutiny suspension; mandatory closeout). Startup sleep fallback deadline
2026-10-23T11:00:00Z; owner cancel command `.\cancel-sleep.cmd`.

## Unattended window 2026-10-23 — scrutiny assessment + capability bands + CLI process review

All three assigned tasks are **COMPLETE**; one decision is queued for the owner.

- **Scrutiny value assessment — complete; suspension brief QUEUED.**
  `artifacts/unattended-20261023-0928/scrutiny-assessment.md`. The in-workflow
  false-claim check is uniquely valuable and calibration-proven, but the current
  *hard gate on a local model's exact 6-heading format* is
  net-worse-or-no-improvement in production (today's false downgrade;
  `acceptance-criteria.md:124` records that no scrutiny catch has been
  established in production). Owner must choose **A** advisory-only,
  **B** skip for high-tier primaries, **C** remove — and define "high tier".
  Recommendation: **A** (keeps the false-claim check, drops only the format gate).
- **Capability scoring — implemented (Decision A, made more granular).**
  `packages/ai_provider/src/ai_provider/capability_bands.py` + 30 tests in
  `tests/test_capability_bands.py`. Six bands per source (`Frontier`, `Strong`,
  `Solid`, `Competent`, `Weak`, `Very weak`); cutoffs calibrated on the
  2026-10-22 snapshots (Aider `12/25/50/70/80` on `percent_correct`, SWE-bench
  `24/40/55/70/75` on `percent_resolved`) then frozen so a refresh moves a row
  only when its score changes. Band scale + 18-route band table published
  recommendation-only in `model-catalog.md`; `interface.md` documents the
  module; mapping doc cross-referenced. Routing, `model_catalog.toml` and
  `ModelCatalogEntry.quality` untouched (that field is a *declared requirement*,
  deliberately a different vocabulary from the evidence band).
- **CLI process review — complete.**
  `artifacts/unattended-20261023-0928/cli-process-review.md`. Stack is current
  (stdlib, deterministic validation as the real gate, real tool loop); the
  weakness is three control-plane *reporting* defects. **F1** scrutiny decides by
  format (same issue as the queued brief). **F2** `prompt_review`/`planning` are
  declared in `ORCHESTRATED_STAGE_PLAN` but never started by any code path, so
  they persist as `planned` forever — the tracker is created after orchestration,
  so their work cannot be attached to a stage record. **F3**
  `final_handoff.changed_files` (`run_tracking.py:415`) uses `git status` with no
  baseline and reported **44 files for a 1-file edit** — a false claim, exactly
  what scrutiny exists to catch; `repair_state.workspace_fingerprints` /
  `changed_paths` already provides the baseline-aware fix. **F4** the two local
  review stages took 24 s of the 40 s Option A run. **F5** controller
  `validate.py` exclusion list misses the state DB. **No code changed by the
  review** — F1/F3 need owner decisions.
- **Validation (2026-10-23 08:12–08:13 UTC):** full `pytest -q` → **2704 passed,
  9 skipped**; `scripts/run-tests.py council job-search` → 84 passed;
  `ruff check .` and `ruff format --check .` clean (323 files); `pyright` →
  0 errors, 0 warnings. `tests/test_capability_bands.py` had to be registered in
  `scripts/run-tests.py` GROUPS (provider) — its first full run failed 5
  `test_test_suites.py` cases on `Update GROUPS: unassigned=['tests/test_capability_bands.py']`.
- **Everything remaining needs the owner:** the scrutiny suspension form; the
  F1/F3 fixes; `model-capability-data-plan.md` open question 2 (mapping scope —
  Go catalogue, OpenRouter free routes, or both) and question 3 (where the
  two-tier L2+L3 grading record lives); and step 6 (feed the prior into
  `model_catalog.toml`), which that plan's own constraints gate on a separate
  owner decision.

## Prior session — Option A live baseline acceptance run executed + capability-scoring research done

## Option A live baseline acceptance — executed 2026-10-23

Owner authorized Option A (2026-10-23): one representative bounded live run on
`opencode-go/go-kimi-k2.7-code`, controller-gated with an explicit grant.

- **How it was launched (genuinely controller-gated).** Built a fixture
  (`math_ops.py` seeded `add` returns `a - b`; `test_math_ops.py`; `AGENTS.md`),
  ran `bounded-acceptance-controller.py prepare` → `coherence` (exit 0) →
  `launch --grant "owner-optionA-2026-10-23"` (status ready). Then invoked the
  exact known-good orchestrated agent command from `opencode-go-acceptance.py`
  against the **controller's own fixture** (not a duplicate), with
  `--max-action-rounds 10`, `--max-repair-cycles 2`, 600s wall-clock. Credential
  loaded via the repo's `alternate-agent-acceptance.py`-style `.env` loader
  (functional equivalent of `uv run --env-file`; `uv` is neither on PATH nor
  importable). Ollama `deepseek-coder-v2:16b` served the auxiliary/scrutiny stages.
- **Primary-model behavior (kimi): COMPLETED.** Native-tool trace: find_files →
  read_file (saw `a - b`) → edit_file → run_command(pytest). Fixed `add` to
  `a + b`. Draft claim "all 3 tests pass" is evidence-supported; **no material
  false claim**. 7 provider calls, ~10.4K tokens, ~40s, `reported_cost=None`.
- **Independent frozen review (host): PASS on the task.** Re-read `math_ops.py`
  (`return a + b`, correct), frozen files unchanged, re-ran pytest → **3 passed**.
- **Workflow outcome: completed with unresolved scrutiny (contained).**
  Deterministic validation passed; scrutiny (local Ollama) failed —
  `missing scrutiny heading(s): REVISED_RESPONSE`. Workflow reported
  `completed_with_scrutiny_errors` and honestly withheld acceptance
  (`completion=not_established; scrutiny=unresolved`) — the designed 2026-10-19
  containment working. Not a clean 3-part pass because scrutiny errored.
- **Two robustness findings (non-task, recorded):** (1) scrutiny-stage fragility —
  local reviewer non-deterministically omits the required heading, downgrading a
  correct run; (2) controller `validate.py` over-strict — flags the
  repo-assistant's own `data/repo-assistant-runs.sqlite3` state DB as an
  unexpected file (exclusion list only covers `__pycache__/`/`.pytest_cache/`).
- Evidence: `artifacts/opencode-go-baseline-acceptance-20261023-002033/`
  (`FROZEN-REVIEW.md`, `assistant.log`, `transcript.log`, `fixture/`,
  `controller/`). No git changes; `master` untouched; no push.

## Capability-scoring mechanism (Decision 2) — research done, brief pending

Owner asked for internet research before deciding the scoring MECHANISM. A
background research subagent returned a source-cited survey of how other
projects grade models for selection/routing (RouteLLM, LMArena, OpenRouter,
HF/AA leaderboards, Braintrust, Aider, SWE-bench). Key consensus: nobody averages
incommensurable benchmarks (Aider `percent_correct` vs SWE-bench
`percent_resolved`); the dominant pattern for incommensurable sources is
keep-per-source/categorical band; no system routes automatically on public
leaderboard scores; local first-hand evidence overriding the public prior is
near-universal. A decision brief with the mechanism options + recommendation
(per-source categorical band) is being presented to the owner.

## Group 1 conformance — OpenCode Go adapters + Anthropic Messages bug fix, 2026-10-22

Continued the documentation-conformance review (deferred ledger item 1) on the
three OpenCode Go protocol adapters and the generic Anthropic Messages base.

- **Conforms:** Go Chat endpoint (`/go/openai/v1/chat/completions`) matches docs
  exactly; `User-Agent: ai_projects/0.1.0` satisfies the "own agent, not a generic
  SDK name" rule; `x-opencode-session` always sent (stable id via
  `request.metadata["opencode_session"]`); Messages always sends `max_tokens`.
- **Two working departures recorded (unchanged, live-confirmed 2026-10-22):** Go
  Responses/Messages use base `/go/v1/...` where docs document
  `/go/openai/v1/responses` and `/go/anthropic/v1/messages`; and the
  `_RESPONSES_MODELS`/`_MESSAGES_MODELS` sets route some models (qwen3.8 family,
  minimax-m3, deepseek-v4.1-flash/pro) to a different protocol than the current
  docs table. Every affected model returned `ok` under the implemented routing in
  `docs/artifacts/go-all-model-probe-20261022-rerun.json`; endpoint paths are pinned
  by `tests/test_opencode_go_protocol_adapters.py`. Left as-is: they work, and
  switching to the documented canonical paths is unverified without live inference.
- **One demonstrated bug found and fixed** in the shared
  `packages/ai_provider/src/ai_provider/adapters/anthropic_messages.py` (inherited
  by `opencode_go_messages.py`): it forwarded system messages as
  `{"role": "system", ...}` inside `messages`, which the Anthropic Messages API
  rejects — system must be the top-level `system` parameter (`messages[]` accepts
  only `user`/`assistant`; verified against the official schema). Since
  `coding_assist.py` builds `AIMessage(MessageRole.SYSTEM, ...)` and the factory
  routes Messages-protocol models (`claude-haiku-5-5`, `minimax-m2.7`) to this
  adapter, any system prompt on those models would have 400'd. Fixed by hoisting
  system messages to top-level `system` (joined by blank lines). New regression:
  `test_messages_client_hoists_system_prompt_to_top_level`. The OpenAI-compatible
  and OpenAI Responses adapters were checked and are unaffected (Chat Completions
  and the Responses `input` array both accept a `system` role natively).

Findings recorded in
[docs/documentation-conformance-plan.md](docs/documentation-conformance-plan.md);
ledger item 1 status updated in
[docs/plans/deferred-baseline-work-20261022.md](docs/plans/deferred-baseline-work-20261022.md).

**Validated:** `scripts/run-tests.py full` **2674 + 38 + 84 = 2796 passed, 3
skipped, 0 failed**; `ruff check .` clean; `ruff format --check .` 321 files;
`pyright` 0 errors. No live inference; `master` untouched; no push.

**Item 1 now complete (Group 1 provider adapters):** the owner approved the
optional full sweep. Field-by-field review of the two large generic adapters:
the OpenAI-compatible Chat Completions adapter conforms (no change); the OpenAI
Responses adapter had a second demonstrated bug — it hardcoded
`finish_reason=STOP` and ignored the documented `status`/`incomplete_details`
fields, hiding `max_output_tokens` truncation and content filters. Fixed by
mapping `status`/`incomplete_details.reason` to `FinishReason`
(`completed`/absent → STOP, `incomplete`+`max_output_tokens` → LENGTH, other →
UNKNOWN), matching the Chat Completions convention. Regression:
`test_responses_finish_reason_maps_status_and_incomplete_details`. Group 1 is
now complete. Groups 2-4 (orchestration/agents, council/job-search, repo
tooling) remain if wanted.

**Item 5 (source-state refresh) done (targeted):** appended the official
documented Go endpoint table (re-fetched 2026-10-22) and the recorded working
path divergence to `packages/ai_provider/docs/source-state.md`, cross-linked to
the conformance plan. Other providers were already dated 2026-10-21/22; no
contradiction needing owner attention found.

Both ledger items 1 and 5 are now complete. Remaining open ledger items: none
(2, 3, 4, 6 were already complete). The live CLI baseline acceptance remains the
top-priority item blocked on owner authorization; the capability-data scoring
rule remains an owner decision boundary.

## Fresh CLI baseline acceptance evidence — 2026-10-22

Deterministic validation for the EL/EQ/EU follow-up completed on a clean working
tree. No live model inference was used for this slice. Evidence recorded in
`artifacts/cli-baseline-acceptance-20261022ev/`.

### Validation

- Full registered suite (`scripts/run-tests.py full`): **2768 passed, 3 skipped, 0 failed**.
- Provider group (fresh combined EP checks): **534 passed, 0 skipped, 0 failed**.
- Agent group (shell/PID fixture coverage): **383 passed, 2 skipped, 0 failed**.
- `ruff check .`: passed.
- `ruff format --check .`: 315 files already formatted.
- `pyright`: 0 errors, 0 warnings, 0 informations.

### Follow-up status

- EL/EQ shell/PID fixture work is integrated (`ad2ba78`) and validated.
- EP public-input privacy exception is integrated (`acba93e`) and validated.
- ADR-064 unresolved MCP warning is integrated (`f90b58a`) and validated.
- Protected Greek Unicode literals in `tests/test_ai_agent_tools.py` are verified
  present and uncorrupted.
- Working tree remains clean; `master` untouched; no push to `origin`.

### Owner decisions recorded 2026-10-22

1. **Live CLI baseline acceptance route:** OpenCode Go, `kimi-k2.7-code`. The
   route is recognized, the adapter fix resolves the HTTP 400, and the staged
   orchestrated workflow runs end-to-end against `kimi-k2.7-code` with scrutiny
   passing. I added two reusable isolated-fixture harnesses:
   - `scripts/opencode-go-acceptance.py`: single-task implement-mode harness.
   - `scripts/opencode-go-coding-chat-acceptance.py`: two-turn coding-chat
     continuity harness (turn 1 asks the agent to explain a defect and wait;
     turn 2 instructs it to fix and test; it remembers context and completes).
   Verified runs:
   - Simple implement-mode run: **passed** (model edited `math_ops.py`, ran
     `pytest`, reported success; 5 provider calls, ~9.1K total tokens, ~11 s).
   - Orchestrated run with `--orchestrated`: **all stages completed** —
     auxiliary panel (Ollama `deepseek-coder-v2:16b`), primary implementation
     (OpenCode Go), deterministic validation (`pytest` passed), scrutiny
     (verdict `pass`, score 9), and final handoff. Total wall time ~49 s.
- Two-turn coding-chat continuity run: **passed** (statuses [0, 0], source
     changed, tests passed, ~40 s). The agent correctly waited on turn 1, then
     fixed and tested on turn 2 using the same session.
   - Consolidated baseline evidence run via
     `scripts/opencode-go-baseline-evidence.py`: **overall passed** — both the
     staged implement harness and the two-turn coding-chat harness succeeded in
     one invocation. Fixtures deliberately lack `data/pycharm-mcp.json`, so the
     runs exercise the IDE-host-independent path.
   - Added deterministic `tests/test_opencode_go_route.py` covering catalog
     identity, recommender selection, fallback-readiness reporting, and the
     IDE-host-independent shared coding tool registry for `kimi-k2.7-code`
     without live inference.
   The earlier repo-level `workspace_write` run failed only because
   `shell: ask_user` requires interactive approval; it still generated the
   requested `test_publish_pid_overwrites_whitespace_stale_file` regression test,
   which passes in the agent group.
2. **MCP "identified but never retried" semantics:** stay a visible warning per
   ADR-064; warnings can be investigated later. No code change.
3. **Capability-prior scoring rule:** implement **B (recommendation-only grade**
   in the catalog) first, with the eventual goal of **C (selection input)** once
   priors are proven. Local CLI evidence (L3) continues to override the prior.

Live CLI model-quality, continuity, fallback and representative daily-use
acceptance remain future owner-authorized bounded work.

## OpenRouter public-input privacy exception (EP) — promoted 2026-10-22

The last uncommitted slice is now committed and merged. Working tree is clean.

### Commits

- `acba93e` — `feat: explicit public-input privacy exception for OpenRouter free access`
  (owner-approved ADR-063: `PUBLIC_OR_LOW_RISK` + literal boolean
  `metadata["public_or_synthetic"] = True`; request-aware `_verify_request_model`
  hook in the shared OpenAI-compatible adapter; only the uncertain Free-plan
  privacy-filter entitlement is relaxed, while exact `:free` identity, zero
  prices, tool capability, valid quota, zero price caps and
  `data_collection=deny` all remain).
- `c1179ba` — `docs: document OPENCODE_API_KEY in .env.example` (completes the
  Go integration's env surface; the owner's edit was preserved byte-for-byte
  through the pre-commit stash/restore cycle).
- `48bd059` — merge of `feature/cli-readiness-and-tool-parity` into `develop`.
- `2fdae2f` — `docs: record OpenRouter request-contract conformance and dated refresh`.
- `5379f26` — `fix: restore the repository-wide pyright gate in the Go tests`
  (10 pyright errors introduced by `ed9776d`; see the type-check gate repair
  section below).
- `588c7ce`, `657b212` — merges into `develop`.

**No push to `origin` was performed. `master` was not touched.**

### Verified

- Focused OpenRouter suite: 113 passed.
- Full registered suite via `scripts/run-tests.py full`: **2702 passed**
  (workspace 2580 + council 38 + job-search 84), 3 skipped, 0 failed.
  The EP slice's two prior failures (empty-PID interrupt fixtures) are
  resolved by the atomic PID publication in `ad2ba78`; this run is the fresh
  combined EP check the handoff asked for.
- `ruff check` / `ruff format --check` clean on the 3 changed code/test files;
  `pyright` 0 errors on them; `git diff --check` clean.
- Repo-wide `ruff check` (308 files formatted) and repo-wide `pyright` pass
  after the type-check gate repair below.

### Live access

Still unverified. No OpenRouter request was sent in this slice.

## Type-check gate repair — 2026-10-22

Repo-wide `python -m pyright` **failed with 10 errors** in the two Go test
files added by `ed9776d` (`tests/test_go_source_info.py`,
`tests/test_opencode_go_adapter.py`). The repository was verified pyright-clean
at `4611dfa` (the commit before the Go integration) in a detached worktree, so
these were introduced by that slice, not pre-existing. The earlier handoff claim
that "pyright passes on all new/modified files" was therefore **inaccurate** for
these two files.

Fixed without changing test semantics (annotation/typing only):

- `HTTPError(..., {}, None)` → `Message()` (the stub requires
  `email.message.Message[str, str]`; matches the existing convention in
  `tests/test_openrouter_usage.py`).
- `allowance.reason` narrowed with an explicit `is not None` before the
  substring check (the original `in` on a `str | None` would raise at runtime).
- `auth_method="api_key"` → `AuthMethod.API_KEY`;
  `cost_policy_tier="allowances_allowed"` → `CostPolicyTier.ALLOWANCES_ALLOWED`;
  `"billing_allowed"` → `CostPolicyTier.BILLING_ALLOWED`.
- `ModelInventory(models=[...])` → tuple, matching the declared
  `tuple[ModelInventoryItem, ...]`.
- Stream event narrowed with `isinstance(events[0], AIStreamDelta)` before
  reading `.content`, preserving the existing final-event assertion.

After the fix: repo-wide pyright **0 errors**, ruff check/format clean, Go
adapter/source-info/protocol focused tests 43 passed.

## Documentation-conformance slice — OpenRouter request contract, 2026-10-22

Group 1 (provider adapters/shared contracts) of
[the conformance plan](docs/documentation-conformance-plan.md). Official
provider-routing, pricing and limits references re-read 2026-10-22.

- **Conforms.** The `provider` object the free adapter sends
  (`require_parameters: true`, `data_collection: "deny"`, zero `max_price` for
  `prompt`/`completion`/`request`/`image`) matches the documented field names,
  types and price attributes. The `GET /api/v1/key` fields it reads
  (`is_free_tier`, `free_model_daily_requests.{used,limit,remaining}`) match
  the documented response shape. Existing offline regressions already lock
  those guards, so **no code changed**.
- **Recorded deliberate departure.** OpenRouter documents a separate
  `provider.zdr` boolean that restricts routing to Zero-Data-Retention
  endpoints. It is a stronger claim than `data_collection: "deny"` and a
  request-level `zdr` can only *add* enforcement. The adapter does not request
  it, because the Free-plan data-policy entitlement is unresolved and
  requiring ZDR could leave the free route with no eligible endpoint. Changing
  this is a **material privacy/routing owner decision** — not taken.
- **The Free-plan conflict is unchanged** (checked 2026-10-22): the pricing
  feature table lists "Data Policy-Based Routing" as **No** for Free, while the
  same page's privacy FAQ says "Zero Data Retention routing is available on
  every plan". The local guard therefore remains a refusal, not evidence of
  provider denial.
- `is_free_tier` is a credits-purchased proxy, not a data-policy entitlement
  statement; the guard relies on it only as evidence of a paying account.
- Dated findings appended to
  [packages/ai_provider/docs/source-state.md](packages/ai_provider/docs/source-state.md).

## ADR-064 — Unresolved MCP recovery is a visible warning, not a failed run

Owner approved option C (2026-10-22) for **both** unresolved call identity and
a same-tool retry under a new call id. Implemented offline; live external-agent
behaviour unverified.

### Contract

An MCP failure that call identity cannot resolve is demoted from a run-level
failure to a visible warning **only when the run independently proves
completion**: no fatal non-MCP marker, a `turn.completed` without a failure
marker, a final answer produced after the MCP failure, and no pending or open
MCP call at the end of the stream. Then `failure_reason` stays `None`, the
reasons move to the new `ExternalAgentEventSummary.mcp_warnings` field, and the
CLI prints one `external_agent_mcp_warning: <reason>` per unresolved failure. A
completed-with-warning run exits 0; an incomplete or fatal run still fails and
exits non-zero.

Fatal errors are never demoted, an identified failure with its own matching
recovery is unchanged, and the shared-tool receipts remain the source of truth
for what actually happened.

### Files changed

- `packages/ai_provider/src/ai_provider/external_agents.py`: new
  `mcp_warnings` field; demotion gate at the end of `parse_external_agent_jsonl`.
- `packages/ai_agent/src/ai_agent/external_reporting.py`: prints
  `external_agent_mcp_warning:` lines.
- `docs/decisions/ADR-064-visible-warning-for-unresolved-mcp-recovery.md` (new)
  plus the `docs/decisions.md` index entry.
- `docs/repo-assistant/research.md`, `docs/repo-assistant/chat.md`: the visible
  warning line is documented.
- Tests: `tests/test_external_agents.py` (re-specified two tests, added five),
  `tests/repo_assistant/test_external_reporting.py` (two new),
  `tests/repo_assistant/test_external_fallback_outcome.py` (new file,
  auto-registered by the `tests/repo_assistant/test_*.py` group glob).

### Deliberately re-specified existing tests

Two existing tests changed outcome class from failure to warning, as the
approved decision requires. Their original invariant is preserved as warning
retention, and the change is not a silent edit:

- `test_mcp_same_tool_and_arguments_without_call_identity_are_not_recovery` →
  `test_mcp_same_tool_retry_with_new_call_id_is_reported_as_warning`.
- `test_mcp_unrelated_success_retains_distinct_failures` →
  `test_mcp_unresolved_failures_are_retained_as_separate_warnings`.

### Reported consequence to be aware of

The approved general rule also covers a third case that was not separately
named: an identified MCP failure that the agent **never retried**, in a run
that otherwise completed. That is also reported as a warning. The warning text
distinguishes nothing here — every unresolved reason is retained verbatim. If
the owner wants the "never retried" case to stay a failure, the demotion
condition needs one extra clause; the current implementation does not
distinguish it.

## L1 slice 1 — OpenRouter route availability (first-party API), 2026-10-22

First slice of the model-capability data plan (L1: availability/performance
from provider APIs, before any leaderboard scraping). Offline-implemented and
live-smoke-tested.

### What was built

- `packages/ai_provider/src/ai_provider/source_info.py`: new neutral contracts
  `EndpointAvailability` (one provider endpoint) and `EndpointInventory` (the
  per-model envelope with a `summary()`). Provider-neutral so every source
  normalizes into one shape and no consumer branches per source; unreported
  values stay `None`.
- `packages/ai_provider/src/ai_provider/openrouter_endpoints.py`:
  `read_openrouter_endpoint_availability(model_id)` reads the **public**
  OpenRouter endpoints API `GET /api/v1/models/{author}/{slug}/endpoints`.
  No key required, no prompt, no model call, no credential-file discovery.
  `python -m ai_provider.openrouter_endpoints "<model>"` prints the closed
  observation.
- Tests: `tests/test_openrouter_endpoints.py` (21 cases), registered in the
  `provider` group of `scripts/run-tests.py`.

### Live findings, 2026-10-22

- `latency_last_30m` and `throughput_last_30m` were **null** in every
  response. Not yet a usable latency signal.
- `context_length` and `quantization` **differ per endpoint** for the same
  model (65,536–1,000,000 tokens; `bf16`/`fp16`/`fp8`/`fp4`/`nvfp4`/
  `unknown`). A route's real capability depends on which provider serves it.
- `supported_parameters` differs per endpoint; a provider may not support the
  tool-choice modes the CLI needs.
- A `:free` variant lists only free endpoints, and **a free variant with no
  free provider serving it returns an empty endpoint list**. Dated snapshot:
  `thinkingmachines/inkling-small:free` 1 provider (`nvfp4`, 1,048,576 ctx,
  100% uptime), `google/gemma-4-31b-it:free` 1 provider (262,144 ctx, 99.79%),
  `cohere/north-mini-code:free` 1 provider (256,000 ctx, 100%), while
  `openai/gpt-oss-120b:free` and `qwen/qwen3.8-27b:free` advertised **no**
  endpoint — i.e. those free routes cannot currently be used even though the
  models are still advertised. This is exactly the actionable L1 finding the
  plan wanted, obtainable before spending a request.

## L2 slice 1 — SWE-bench capability prior, 2026-10-22

The "judge their capabilities" half of the owner's request. Offline-implemented
and live-verified.

### What was built

- `packages/ai_provider/src/ai_provider/source_info.py`: new neutral contracts
  `CapabilityScore` (one published result, **always with its agent scaffold
  attached**) and `CapabilityPrior` (per-split envelope with `summary()`).
- `packages/ai_provider/src/ai_provider/swe_bench_scores.py`:
  `read_swe_bench_scores(split)` reads the public SWE-bench leaderboard data.
  No key, no prompt, no model call. 16 test cases, registered in the
  `provider` group.
- Tests: `tests/test_swe_bench_scores.py`.

### The crux, now measured rather than assumed

- SWE-bench Verified: 180 rows, **89 published model names → 84 comparable
  keys**, **77 distinct agent scaffolds**. A row is a **(model, scaffold)**
  pair, so a score is never a model-only claim. Published names are not
  normalized ("GLM 4.5" and "GLM-4.5" are the same model), which is exactly
  the "data uniformity" problem the owner raised.
- Coverage of our routes: **17 of 36 Go routes** have a family match, always
  across a version gap; **19 of 36 have none** (all four Qwen routes, Grok
  4.6/4.7, all four MiMo, LongCat 2.0, Beam, both Muse Spark, Omen Alpha,
  both Hy previews, Step 5 Preview); **0 of the 17 OpenRouter free variants**
  have a match.
- **Aider polyglot covers more of our routes**: 52 distinct model ids under
  **one consistent harness**, including the gateway-served open-weight models
  SWE-bench misses — `gpt-oss-120b`, `kimi-k2`, `qwen3-32b`,
  `gemma-3-27b-it`, `grok-3/4` — plus `deepseek`, `gemini`, `claude`, `gpt`.
  Because the harness is constant, its scores are comparable model-to-model.
  **Revised recommendation: Aider becomes the primary L2 source, SWE-bench
  the secondary one** (the plan originally had it the other way round).
- **The hard limit of internet data:** no public leaderboard covers our
  newest route ids (Qwen 3.6+/3.7+/3.8+, Kimi K2.7, GLM 5.1-5.3, Grok
  4.6/4.7, MiMo 2.5/2.6, LongCat 2.0, Beam, Muse Spark, Omen Alpha, Hy).
  For those routes the internet prior is **absent**, not merely weaker —
  the strongest practical support for the owner's position that our own CLI
  findings take priority.

Recorded in [packages/ai_provider/docs/model-catalog.md](packages/ai_provider/docs/model-catalog.md)
("Capability prior coverage") and the interface contract.

## L2 slice 2 — Aider polyglot capability prior, 2026-10-22

The primary comparison source, and the last authorized slice of the
capability-data plan.

### What was built

- `packages/ai_provider/src/ai_provider/aider_polyglot_scores.py`:
  `read_aider_polyglot_scores()` parses the public leaderboard **HTML using
  only the Python standard library**. The approved HTML-parsing dependency was
  **not needed** and remains unspent.
- `source_info.py`: `CapabilityScore` gained `configuration` plus
  `test_cases`, `well_formed_percent`, `syntax_errors`, `context_exhausted`,
  `prompt_tokens`, `completion_tokens`. Unknown stays `None`.
- `configuration` is Aider's `edit=<format>; reasoning=<level>`, which keeps
  repeated runs of one model distinguishable.
- Tests: `tests/test_aider_polyglot_scores.py` (19 cases), registered in the
  `provider` group.

### Four measured findings that constrain the future scoring decision

Saved with provenance under `artifacts/model-capability-priors-20261022/`
(git-ignored local data: aider, swe-bench, openrouter availability, README):

1. **An unpinned model id is a rolling alias.** `deepseek/deepseek-chat`
   published **17.8 / 48.4 / 55.1 / 70.2** under an *identical* configuration
   between 2024-12-21 and 2025-10-03. A leaderboard score for an unpinned id
   is a snapshot, not what that id resolves to today. Prefer pinned ids.
2. **Configuration materially changes the score.** `openai/gpt-5` 88.0 (high)
   / 86.7 (medium) / 81.3 (low); `o3` 81.3 (`diff`) / 78.2 (`architect`).
3. **Accuracy is not reliability.** `openai/gpt-5` hit 88.0% at only 91.6%
   well-formed, versus `gemini/gemini-2.5-pro-preview-06-05` at 83.1% with
   99.6% well-formed. The more accurate model is the worse unattended choice.
4. **The OpenRouter free route set turns over within the hour.** ~50 minutes
   apart, `openai/gpt-oss-120b:free` and `qwen/qwen3.8-27b:free` left the
   public free catalogue while unrelated free models appeared; the total stayed
   at 17. Verified not to be a rate-limit artefact (repeated reads with and
   without delays returned empty, and the ids were absent from the catalogue).
   **Availability must be re-read before use, never cached as a route property.**

### Revised source position (supersedes the earlier reversal)

Neither source wins outright:

- **Aider for ranking models against each other** — one harness, and it
  publishes a *specific model id* rather than a display name. This is what
  "grade specific models, not just their family" requires.
- **SWE-bench for task-shape relevance and freshness** — repo issue resolution
  is closer to our real work, and it is ~4 months fresher (runs to 2026-02-26
  versus Aider's 2025-10-03).
- **Do not average across them**: `percent_correct` and `percent_resolved` are
  different scales. Both readers keep `scale` distinct for that reason.

### Owner decision, 2026-10-22

The Orchestrator **keeps routing from the declared catalog**. These findings
become a basis for *modifying* the catalog later, once normalized into a
per-model grade. **The scoring rule is deliberately not decided**; normalizing
the data and defining how to grade a specific model is the next step of that
work, not part of this slice.

## OpenCode Go integration — three-protocol support implemented 2026-10-22

Owner approved extending Go support to all three documented endpoints (Chat
Completions, OpenAI Responses, Anthropic Messages) using reusable base adapters
with Go-specific subclasses. Privacy/protocol metadata was added to the model
catalog, and Console Privacy toggles for Global regions and training-on-request
data were approved by the owner. Implementation is offline unit-tested; the
fresh live all-model probe is pending availability of the Go inference key.

### Implemented

- `packages/ai_provider/src/ai_provider/source_info.py`: extended
  `ModelInventoryItem` with `protocol`, `trains_on_request_data`, and
  `requires_global_regions`.
- `packages/ai_provider/src/ai_provider/go_source_info.py`: Go-specific collector
  now populates protocol/privacy metadata and routes endpoint paths by protocol.
- `packages/ai_provider/src/ai_provider/adapters/openai_responses.py`: generic
  reusable OpenAI Responses API base adapter (`complete`, `stream`, usage,
  error normalization).
- `packages/ai_provider/src/ai_provider/adapters/anthropic_messages.py`: generic
  reusable Anthropic Messages API base adapter (`complete`, `stream`, usage,
  error normalization).
- `packages/ai_provider/src/ai_provider/adapters/opencode_go_responses.py`:
  Go-specific Responses subclass with Go base URL, User-Agent and
  `x-opencode-session` header.
- `packages/ai_provider/src/ai_provider/adapters/opencode_go_messages.py`:
  Go-specific Messages subclass with Go base URL, User-Agent and
  `x-opencode-session` header.
- `packages/ai_provider/src/ai_provider/factory.py`: routes OpenCode Go models
  by protocol (`responses` → `OpenCodeGoResponsesClient`, `messages` →
  `OpenCodeGoMessagesClient`, otherwise `OpenCodeGoChatClient`).
- Existing `OpenCodeGoChatClient`, `ProviderKind.OPENCODE_GO`,
  `OPENCODE_API_KEY` and billing wiring remain unchanged.
- Tests: added `tests/test_opencode_go_protocol_adapters.py`; extended
  `tests/test_go_source_info.py` for protocol/privacy/endpoint metadata.
  Registered new test module in `scripts/run-tests.py` provider group.
- Docs: updated `interface.md`, `source-state.md`, `model-catalog.md` with
  adapter design, protocol routing, privacy metadata and pending live probe note.

### Verified

- New focused Go/adapter tests: 54 passed.
- Full registered suite via `scripts/run-tests.py full`: 2699 passed
  (workspace 2577 + council 38 + job-search 84), 3 skipped, 0 failed.
- `ruff check/format` and `pyright` pass on all new/modified files.
- `python -m ai_provider.go_source_info` runs without credentials and exits
  safely (status unavailable, no secret output).

### Live probe results — 2026-10-22

- Cheap model listing succeeded: **36 models** returned.
- Single-model inference acceptance on `kimi-k2.7-code` succeeded.
- Original all-model access probe (Chat-Completions-only adapter): **23 ok / 13 error**.
- Rerun with Responses/Messages protocol routing and Console Privacy toggles
  (Global regions + allow paid endpoints that train on request data), using
  `max_output_tokens=16`: **33 ok / 3 error**.
- **Models unblocked by protocol routing + privacy toggles**: DeepSeek V4.1
  Flash / V4 Pro, Grok 4.6/4.7, GPT 5.6/6 Luna, Muse Spark Contributor 1.2/1.3,
  Claude Haiku 5.5, MiniMax M2.7.
- **Still failing**: `mimo-v2.5-pro` (upstream unsupported), `gemini-4-argon-contributor`
  (no supported protocol across Chat/Responses/Messages), `longcat-2.0`
  (endpoint unavailable).
- **Models ignoring `max_output_tokens`**: `qwen3.6-plus`, `qwen3.7-max`,
  `qwen3.7-plus`, and `grok-4.6` produced far more tokens than requested.
- **GPT Luna requires `max_output_tokens >= 16`**; lower values return
  `invalid_request_error`.
- Full probe artifacts preserved in `docs/artifacts/` (gitignored):
  `go-all-model-probe-20261022.json` and
  `go-all-model-probe-20261022-rerun.json`.

## Shell/PID baseline work — completed in isolated IDE-assisted candidate 2026-10-22

Created isolated candidate at `artifacts/ide-shell-pid-20261022/candidate`
(detached HEAD `4611dfa4ee166979caaa37b4b91cc339b91ac9d6`).

### Problem

Ownership fixtures published descendant PIDs with `Path("child.pid").write_text(...)`.
That creates the file before its contents exist, so readers waiting only for file
existence could observe an empty/partial PID and fail on `int("")`.

### Fix

- Replaced direct `write_text` PID publication in the three ownership fixtures
  with an atomic write-and-rename helper (`_publish_pid`).
- Updated readers to wait for file existence **and** non-empty content before
  parsing.
- Added `tests/test_pid_publication.py` with deterministic companions:
  `test_atomic_publication_hides_partial_write`,
  `test_reader_waits_for_content_not_just_existence`,
  `test_publish_pid_overwrites_stale_file`.
- Registered `test_pid_publication.py` in `scripts/run-tests.py` agent group.

### Files changed in candidate

- `packages/ai_agent/src/ai_agent/tools/shell.py` (matches EL inherited hash)
- `packages/ai_agent/src/ai_agent/validation_process.py` (matches EL inherited hash)
- `scripts/run-tests.py`
- `tests/test_ai_agent_tools.py`
- `tests/test_validation_process_ownership.py`
- `tests/test_native_diagnostic_ownership.py`
- `tests/test_shell_process_ownership.py` (untracked)
- `tests/test_pid_publication.py` (new)

### Validation

- Ruff check/format passed on all 8 candidate files.
- Pyright passed on `shell.py` and `validation_process.py`.
- Targeted ownership tests: 43 passed in 12.39 s.
- Full registered suite: 2503 passed, 3 skipped.
- `git diff --check`: clean.

### Artifacts

- Implementation report: `artifacts/ide-shell-pid-20261022/implementation-report.md`
- Candidate HEAD and diff stat saved in `artifacts/ide-shell-pid-20261022/`

No commits, merges, pushes or main-root modifications were made for this slice.

## Committed and merged slices

Both approved slices were committed on `feature/cli-readiness-and-tool-parity`
and merged into `develop`:

- `ed9776d` — `feat: OpenCode Go three-protocol integration`
- `ad2ba78` — `fix: atomic PID publication for shell/validation ownership fixtures`
- Merge commit on `develop` bringing in the feature branch history.

Full registered suite after both commits: **2702 passed, 3 skipped, 0 failed**.
No push to `origin` was performed.

## Remaining uncommitted work

None. The EP slice, the `.env.example` completion and the conformance slice
are all committed; the working tree is clean.

## Next action

Owner direction (2026-10-22): **continuing towards the baseline CLI is the
higher priority.** The MCP recovered-warning vs strict unresolved call-ID
decision was made: **option C, for both failure kinds** (ADR-064, implemented
offline above). Nothing further is blocked on that decision.

Fresh deterministic CLI baseline acceptance evidence for the EL/EQ/EU follow-up
was produced in this session (2768 passed/3 skipped full suite, 534 passed
provider group, 383 passed/2 skipped agent group, ruff/format/pyright clean).
Evidence recorded in `artifacts/cli-baseline-acceptance-20261022ev/`.

Remaining candidates, in priority order:

1. **Live CLI baseline acceptance** — highest priority now that the deterministic
   prerequisite is satisfied. Requires an owner-authorized bounded run on the
   selected paid route with fresh named bounds, actual execution, both faithful
   reports, frozen independent validation and owned cleanup. No blind full pilot
   or historical replay.
2. **Documentation-conformance plan** (group 1 remaining provider adapters and
   shared contracts, then groups 2-4) — offline, bounded, already the tracked
   high-priority prerequisite. Safe to do now if live baseline is blocked.
3. **Capability-data plan, next slice — DECISION, not code.** The readers and
   the saved data exist. What remains is to define how to grade a *specific*
   model (not its family) from these priors plus our own CLI transcripts, and
   whether a prior may ever override a transcript. This is an owner decision
   boundary: it determines what the Orchestrator does, so it needs a decision
   brief before implementation. Do not implement a scoring rule unapproved.

**Deferred easy work for less capable models** is recorded in
`docs/plans/deferred-baseline-work-20261022.md` (local plan; directory
`docs/plans/` is git-ignored). It covers documentation-conformance expansion,
route-to-upstream mapping, live acceptance fixture preparation, shell/PID
ownership companions and provider source-state refresh. Three ledger items are
now complete as of 2026-10-22:

- **Item 4 (shell/PID ownership companions):** added
  `test_reader_times_out_cleanly_when_pid_never_appears` and
  `test_publishing_same_pid_twice_is_idempotent` to
  `tests/test_pid_publication.py`; agent group 386 passed, 2 skipped.
- **Item 2 (route-to-upstream-family mapping table):** created
  `packages/ai_provider/docs/route-upstream-family-mapping.md`, covering all
  18 declared routes with evidence, confidence level and a 2026-10-22 checked
  date. Verified programmatically that every `route_id` in the catalog has
  exactly one row and the table has no extra rows. Result: 0 exact, 14 family,
  0 alias, 4 unmatched; the four unmatched routes
  (`ollama/deepseek-coder-v2:16b`, `openai/codex-gpt-6.1-sol`,
  `github/copilot-cli-auto`, `kiro/auto`) are explicitly left
  ungraded. Linked from the capability-prior section of
  `packages/ai_provider/docs/model-catalog.md`.
- **Item 3 (bounded acceptance controller):** added
  `scripts/bounded-acceptance-controller.py`, a route-agnostic controller
  that writes `task.md`, `coherence.py`, `validate.py`, `checksums.json` and
  `run.json` into a controller directory, and gates `launch` behind an
  explicit `--grant` or `--bounds` argument. The coherence gate refuses a
  mis-prepared fixture, a changed frozen input, or a fixture whose tests
  already pass; the validation gate refuses an unchanged editable file, a
  modified frozen test, a failing test run, or an undeclared new file. Both
  gates and preparation run with no credential and no network; only `launch`
  would touch a provider. 14 deterministic tests in
  `tests/test_bounded_acceptance_controller.py` (registered in the `cli`
  group) plus a manual shell end-to-end check: prepare → coherence exit 0 →
  launch without grant exit 1 → launch with grant exit 0 → simulate success →
  validate exit 0. Not yet replicated onto the OpenCode Go harness itself,
  which still embeds its own fixture inline.

## Route-id normalization + catalog-derived `--provider` — complete 2026-10-22

**Deferred ledger item 6 is now complete.** The owner approved normalizing every
route id to `provider/product-model`, keeping `product` in the label so ADR-021
billing boundaries stay visible.

### What changed

- **All 18 routes** in `packages/ai_orchestrator/examples/model_catalog.toml`
  were renamed. Models keep native punctuation, so labels now show the real
  model string: `ollama/qwen2.5-coder:14b` (was `ollama-qwen2-5-coder-14b`),
  `openai/codex-gpt-6.1-sol`, `google/antigravity-gemini-3.1-pro-high`,
  `requesty/openai/gpt-5.1`, `github/copilot-cli-auto`, `kiro/auto`,
  `opencode-go/go-kimi-k2.7-code` (was bare `kimi-k2.7-code`).
- `_default_route_id()` in `packages/ai_orchestrator/src/ai_orchestrator/catalog.py`
  was rewritten to derive that form: product omitted when it equals the provider,
  human slugs `ai-studio`/`api`/`free`/`copilot-cli`, `opencode_go` ->
  `opencode-go`. A new test asserts the derivation reproduces every declared
  route id, so the hand-authored catalog cannot drift from the convention.
- **`--provider` no longer hardcodes** `["ollama", "openai", "requesty",
  "google"]`. It is validated against the loaded catalog, so `github`, `kiro`
  and `opencode_go` are now accepted (previously rejected) and an unknown value
  fails listing the available providers.
- The two acceptance harnesses used the route id as a **filesystem path
  component** (`fixture = root / ROUTE`); that is now sanitized to
  `ROUTE.replace("/", "-")` so a `/` in the id cannot break `mkdir()`. Route ids
  are never path components anywhere in the packages.

### Deliberately left unchanged

- **`gemini-cli-free-flash`** (`gemini_cli_catalog.toml`) and
  **`openrouter-free-qwen38-27b`** (`openrouter_free_catalog.toml`) are
  explicitly-marked "preserve the failed route" historical evidence; rewriting
  preserved evidence would defeat its purpose.
- Evidence artifacts under `artifacts/opencode-go-*` and
  `artifacts/cli-baseline-live-*` retain old labels as historical records.
- `kimi-k2.7-code` remains the **model id** everywhere (it is only the *route*
  id that changed).

Recorded as **ADR-065** (`docs/decisions/ADR-065-route-id-naming-convention.md`)
with a cross-reference amendment on ADR-021, since this changes a public CLI
contract.

Fresh full-suite evidence after all three slices: `scripts/run-tests.py full`
**2792 passed, 3 skipped, 0 failed** (2670 workspace + 38 council + 84
job-search); `ruff check .` clean; `ruff format --check .` 321 files already
formatted; `pyright` 0 errors, 0 warnings, 0 informations.

### Model capability & availability data — plan added, not authorized

[docs/plans/model-capability-data-plan.md](docs/plans/model-capability-data-plan.md)
(private, gitignored) records the owner's request for a reliable way to gather
data about available models and judge their capabilities, using existing public
sites rather than building our own benchmark.

Key researched facts (checked 2026-10-22):

- **L1 (availability/performance, machine-readable, no auth):**
  `GET https://openrouter.ai/api/v1/models/{author}/{slug}/endpoints` returns
  per-provider uptime (1d/5m/30m), latency, throughput, context length,
  pricing, quantization, service tier and supported parameters. Verified by
  direct fetch.
- **L2 (capability prior):** SWE-bench leaderboard JSON
  (`https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json`
  plus `data/info_for_leaderboard.json`); Aider polyglot leaderboard HTML
  (robots.txt has no Disallow rules; reports per-model code-editing pass rate,
  malformed responses, syntax errors, context exhaustion and cost); LMArena
  leaderboard HTML (robots.txt allows `/leaderboard*`, disallows `/api/` and
  `/nextjs-api/`); Artificial Analysis (robots.txt `Allow: /`).
- **The crux:** leaderboards score flagship upstream models, so route ids need
  an explicit, dated mapping to upstream families. Unmatched routes stay
  unmapped. Access route stays separate from model identity (ADR-021).
- **Limit:** a leaderboard is a selection prior, never acceptance evidence
  (acceptance-criteria.md). L3 local measurement remains decisive.
- **Priority:** supporting workstream for the baseline CLI; it must not
  displace baseline CLI acceptance work. L1 (first-party provider APIs) first,
  then the mapping table, then one L2 source, then a second opinion, then
  optional feed into declared route selection.
- No implementation, scraping, dependency, service or inference is authorized
  by that plan.

### Open questions recorded in that plan

Owner answers (2026-10-22), now recorded in the plan:

1. **Refresh mode** — automatic refresh is the default for every source; the
   owner sees no case for a "read manually only" class. A narrow exception
   rule is kept for later (terms/robots forbid automation, a credential we do
   not hold, or browser-only reading). The surviving rule is field-level:
   automate the numbers, keep the interpretation human.
2. **HTML parsing** — a small HTML-parsing dependency is acceptable, and
   **data uniformity is encouraged**: every source normalizes to one shared
   record shape, so no downstream code branches per source.
3. **Grading basis** — internet data is the default basis for model grading
   (readily available, tested by more people); our own CLI transcripts take
   priority for judging suitability for a specific task. Both are recorded
   with provenance, and the local result overrides the internet prior for that
   task. This plan produces the default prior that local evidence overrides.

### OpenCode Go pricing clarification (confirmed with owner)

Subscription fee ($10 Go / $40 Plus) unlocks **per-model monthly dollar caps**.
Token prices determine how fast a model's own cap is consumed. Hitting 100% on
Kimi K2.7 Code only exhausts that model's cap; other models with their own caps
and the temporary free models remain available. Extra Console credits are used
only if explicitly enabled.

### Live work pending

Read-only metadata observation with the configured key and a bounded inference
acceptance proposal are prepared below; no live call has run. Next is either
owner approval for the metadata/inference probes or continuation with the
planned shell/PID baseline work.

## Latest task order — OpenCode integration FIRST, then planned baseline

Owner requests a new OpenCode-chat prompt: connect Go through ai_provider, establish
automatic model/usage information with a small common class/source-specific
implementations if appropriate, then resume planned work. New complete handoff:
docs/plans/opencode-go-integration-first-20261022.md. Kimi remains the model; no
routine manual switching. This supersedes earlier "no Go integration authorized"
and shell-first priority wording within the scope of the requested integration.
Offline implementation is complete; live calls need a fresh bounded grant.

Investigation found account_usage.py dispatches existing source-specific readers;
reuse these. New prompt requires a small design, compatibility and material-decision
briefs before architecture/public-contract changes. Model discovery, response usage
and remaining subscription allowance are different measurements. Official Go model
listing and Console budget/Usage Read docs do not establish Go quota-reader support.
No invented endpoints/counters, credential scraping or blanket runtime refactor.
Offline implementation and declared read-only metadata diagnostics are scoped;
live nested inference needs a fresh concrete synthetic acceptance grant after
billing/privacy admission. No paid overage, automatic model switching, SDK adoption,
new service/storage or unattended mode. If blocked, continue independent planned
shell/PID work from the older IDE handoff, preserving all candidate/trial evidence.

## New owner decision — OpenCode Go manual IDE use, 2026-10-22

LATEST OWNER PREFERENCE: use Kimi K2.7 Code for the whole manual workflow; no manual
model switching until automation exists. Updated IDE handoff keeps implementation
and a separate fresh-session frozen review on Kimi. GLM-5.2/5.3 are retained future
options, not current requirements. Same-model review may share blind spots; actual
validation/report/freeze/cleanup gates remain. Added linked ai_provider reference
docs/model-catalog.md (human-readable recommendations, not runtime routing).
The Orchestrator's executable model catalog remains unchanged.

Owner-highlighted temporary Go promotions verified2026-10-22: LongCat2.5PreviewFree,
MiniMaxM3.1FlashFree, BeamFree advertise temporary free/unlimited usage. Added exact
IDs/privacy distinctions and provisional evaluation status to ai_provider's model
catalog/source-state. No model call or switch. Current Kimi-only preference remains;
Beam's published retention is30days versus zero for the other two Go routes.

Owner reports purchasing OpenCode Go, adding it to PyCharm agents and placing its
key in .env. These are OWNER observations, not independently tested account/model
entitlements. No .env read, key display, model call, install or config change by
Codex. Manual Go use is selected; previous "capacity preference pending" text is
historical. No SDK migration, package Go adapter, automatic fallback, paid overage,
new processor/model beyond the selected session, or unattended automation follows.

Suggested models: Kimi K2.7 Code throughout current manual use; GLM-5.2 alternative
and GLM-5.3 optional different-model review for future automation. Provisional
choices, not repository quality parity.
Current published policies for these routes differ from Contributor training routes.
Keep optional extra usage separate. Actual PyCharm model availability still needs
the owner/client's observation; no account quota refresh occurred this turn.

Prepared explicit IDE-assisted continuation/review prompt:
docs/plans/opencode-go-ide-handoff-20261022.md. It completes shell/PID work in a
NEW isolated candidate with original Unicode/tests, real validation, provenance,
both reports/frozen review and owned cleanup. This is ordinary IDE development,
not activation of EU or retrospective CLI acceptance; no code/report rescue of
consumed trials. CLI baseline still needs its own fresh intended-workflow evidence.
Owner chooses whether to run this handoff; Codex has not launched another agent.

Durable provider research: packages/ai_provider/docs/source-state.md contains
all latest comparisons/model starting points and primary sources. New
packages/ai_provider/docs/access-options.md provides a comparison/SDK decision
map linked directly from package README. No production routing/default change.

Git inspection now shows the prior14 dirty paths PLUS owner-modified .env.example;
preserve it without edits. Provider README/access-options are new authorized docs
changes this turn. EU's historical root snapshots cannot certify these newer docs;
do not rewrite its seals. Original consumed trials and candidate code untouched.

## Latest continuation — 2026-10-22, ET comparison / EU v2 offline preparation

FOLLOW-UP OWNER STEERING: explicitly include OpenCode Go, Claude Pro, Antigravity
and official Codex/Copilot SDK alternatives. Official findings appended to
ai_provider/docs/source-state.md under "Follow-up". Go$10/Plus$40 is a serious
paid candidate, separate from Console free promotions; model-dependent allowances,
20%five-hour/50%weekly caps, session-header/privacy/extra-usage conditions matter.
ClaudePro$20 includes ClaudeCode; current SDK/headless subscription access confirmed
officially, but no repository executor accepted. Antigravity wasn't absent, but was
underweighted: binary exists; exact shared-executor MCP-grant refusal is a concrete
gap to investigate, not a reason to dismiss its free capacity. No new account probes.
SDKs: stable Codex Python SDK controls app-server; Copilot SDK supports typed
sessions/events/tools/permissions over its local runtime, plus experimental FFI.
Recommend focused OFFLINE contract comparison, retaining optional CLI executors,
explicit child-process isolation, all guards/cleanup and neutral architecture.
No dependency/adoption/provider/privacy/purchase decision or install authorized.
This later authorized source-state documentation update means EU v2's frozen
main-root snapshot is HISTORICAL and will refuse current root bytes. Do not edit
its seal/snapshot to compensate; the already-required fresh activation needs fresh
coherence/snapshots. EU's original preparation results are unchanged.

This section supersedes older next-action/status text below. No unattended window,
sleep, wake, scheduling, purchase/signup, new inference route or generation ran.
Branch feature/cli-readiness-and-tool-parity and full HEAD
4611dfa4ee166979caaa37b4b91cc339b91ac9d6 verified. Same 14 deliberate dirty paths.
13 retain exact initial hashes; source-state.md alone intentionally refreshed with
dated official offers and historical strict-entitlement wording qualified under
the already-approved ADR-063 exception. No code integration/staging/commit/push.
Previous handoff preserved at artifacts/cli-capacity-comparison-20261022et/context-before.md.

### Capacity comparison and pending owner preference

Read artifacts/cli-capacity-comparison-20261022et/results.md for offers, sources,
safe account receipts, uncertainty and trade-offs. Reusable official findings are
appended to packages/ai_provider/docs/source-state.md; private quotas stay local.
At 08:28 UTC: Codex primary5%/weekly91% used; weekly reset2026-10-27T08:23:36Z
(09:23 Budapest/Warsaw after DST), primary2026-10-22T13:24:26Z. Copilot native
chat200/200, premium entitlement0; these legacy fields do not establish AI-credit
balance, and its reset equals observation time, so actual next reset unknown.
Kiro native estimate50/50 used, reported reset2026-11-01. OpenRouter uncached
Free0/50 used,50remaining; twoGETs, zero completions. All metadata cleanup verified.

Published: Copilot Pro$10/$15 AI-credit value, Pro+$39/$70, variable flex included;
Codex Pro listed$100/$200/$500, top-ups available but this account's pack price,
plan and upgrade availability unknown. OpenRouter$10 lifetime purchase raises
free ceiling1000/day, Standard5.5% fee; no proven strong coding replacement.
Kiro Pro$20/1000credits, first eligible upgrade advertises$20subscription credit;
eligibility unknown. Antigravity free weekly but shared permission gap; Zed
$5/14days Luna-only; Cerebras$5/30days/card; OpenCode limited-time free models,
some no-training/ZDR claims, quota/integration unestablished. ClaudeCode$20Pro
is a paid alternative with no accepted integration. Trials do not prove quality.

RECOMMENDATION, NOT OWNER DECISION: check a capped top-up on existing Codex first
for immediate continuity; compare recurring Copilot/Kiro with actual checkout.
An async preference question was sent; no answer received at this checkpoint.
No purchase, signup, paid balance use or new processor/privacy scope authorized.
Do not infer authorization from the recommendation or elapsed waiting time.

### NEW guarded shell preparation — EU v2, OFFLINE ONLY

artifacts/cli-shell-faithful-preparation-20261022eu/results.md is the human entry.
Fresh detached4611dfa checkout; saved six EL inputs retain closure hashes, not
applied to candidate. Fixed one-use helper lets the future agent copy those inputs
byte for byte into only the six declared paths. No EQ output or host-authored
candidate repair. Portable checker derived from prospective EQ fix; original
Unicode/protected bodies, native/shell assertions/decorators/raises, meaningful
companions, real full tests, both reports, frozen independent checks and cleanup
remain gates. Semantic report fidelity cannot be certified by mechanical checks.

Final v2:23preparation testsPASS;6portable positives/5other positives/12negative
command controls/4process controlsPASS; both actual CLI composition probesPASS
with zero native generation; Ruff check(ignore E402/E501)/format15helpers/Pyright
PASS; independent audit confirms158selected historical files unchanged, root14
paths retained/index/HEAD preserved, clean candidate and owned probe cleanup.
No repair/report/frozen live review/full candidate suite ran. Baseline INCOMPLETE.

Important v2 correction: inspection uses a separate read/search-only MCP, not the
coding foreground registry; its empty foreground tool-list field is expected.
Final composed command now checks all six effective inspection tools/no shell or
mutation. Copied private user config moved OUTSIDE model workspace and supplied
via existing --user-config host argument. Actual shared read refuses sibling path.
Working-root instructions/coherence verified BEFORE v2 snapshots. No private config
contents printed. V1 seal/probes preserved; changed controller preimages under
revisions/v1. seal-v2.json and independent-preparation-audit-v2.json certify FINAL
v2. prepare.py is historical one-use v1 builder, not an activation entry point.
An initial broad archive command was auto-review rejected before running; a safer
exact controller-only archive plus verified config move succeeded after inspection.

run.py accepts only seal/probe; worker asserts probe. launch_ready=false; no active
grant or model reports. Proposed inherited bounds2CLI/1200sec (repair480/review240,
validation+cleanup reserves) are NOT activated. Preserve sealed preparation; next
create a fresh reviewed activation after capacity preference/account admission and
realistic full-validation headroom. No blind full pilot or historical replay.
Keep current strict MCP semantics; pending warning-versus-unresolved-call-ID owner
decision is unchanged and needed only if changing it. Only accepted code may be
integrated, then fresh combined EP checks. EL/EQ/EP remain historically incomplete.

### Current next-session steering

Continue ATTENDED from this latest section. Read ET/results.md and EU/results.md
plus v2 seal/audit before activation planning. Resolve capacity preference at the
purchase/provider/privacy boundary; no purchase/signup/new route by implication.
Retain all14dirtypaths and consumed trials. Do not run historical prepare.py or
remove offline guards to activate EU in place. No power/scheduling actions.

---

## Prior saved handoff — preserved historical context

End-of-day checkpoint recorded 2026-10-22, after the late 2026-10-21 session.
Owner returned to ATTENDED on 2026-10-21. No unattended continuation, timers,
sleep or wake actions without fresh explicit direction. cancel-sleep.cmd previously
acknowledged no pending repository timer. Historical unattended windows are CLOSED.

## Git and preservation

Repository C:/Users/Jakub/PycharmProjects/AI-projects.
Branch feature/cli-readiness-and-tool-parity.
HEAD 4611dfa4ee166979caaa37b4b91cc339b91ac9d6.
Latest docs-only commit clarifies End of Day local-commit/merge/push authority and
links Prompt Library automation ideas into the post-baseline supervisor roadmap.
No push/merge. Root intentionally has 14 saved dirty paths; never reset or stage
unfinished work to obtain a clean checkout. Use fresh guarded controller trees.
Historical checkpoints, artifacts and detached worktrees remain preserved.

Closeout evidence: artifacts/end-of-day-closeout-20261022es/.
context-before.md preserves the entire preceding handoff, including historical
continuation details. root-before.json records all 16 pre-closeout working files.
Hook stash/restore changed raw bytes of four unfinished provider documentation
files (architecture.md, decisions.md, provider interface.md and source-state.md).
Their Git-normalized blobs exactly match the pre-hook saved patch postimages;
code/tests/untracked files retain exact hashes. Original mixed raw byte layout was
not recovered; do not claim all working bytes unchanged. hook-byte-check.json and
the saved pre-commit patch record the evidence; no semantic edits were made.

## Committed baseline progress

c3b4ba9: model-authored diagnostic ownership/cancellation, Linux zombie controls,
conservative MCP failure correlation and tests; independent 2604 PASS/3 SKIP,
lint/type and frozen review. Original coding failure/timeout remain historical.
216744b: HOST-authored fix to contradictory shared-agent system prompt prefix.
Preserves caller extras/history/quotes/final/away contracts and nonshared defaults.
Independent frozen 2610 PASS/3 SKIP, Ruff/format/Pyright; committed blobs verified.
See artifacts/cli-shared-prompt-repair-20261021en/results.md.
607933a: provider knowledge discoverability and Prompt Library automation assessment.
48d35a5: bounded End of Day workflow and future supervisor plan. No scheduler.
5315812: mandatory ## **SUMMARY** reporting heading. 80ffc65: CLI guide/readiness.

## Preserved incomplete candidates

EL: artifacts/cli-shell-authority-followup-20261021el/closure.json.
Capacity-interrupted, CLOSED, missing model report/frozen review. Host-only
2616 PASS/3 SKIP and lint/type are not acceptance. Six saved root files:
- packages/ai_agent/src/ai_agent/tools/shell.py
- packages/ai_agent/src/ai_agent/validation_process.py
- scripts/run-tests.py
- tests/test_ai_agent_tools.py
- tests/test_validation_process_ownership.py
- tests/test_shell_process_ownership.py (untracked)
Do not overwrite from a failed candidate or replay EL.

EP: artifacts/openrouter-public-input-20261021ep/results.md.
Owner-approved public/synthetic privacy exception implemented, UNCOMMITTED.
OpenRouter only relaxes uncertain Free-plan privacy-filter entitlement when
PrivacyClass.PUBLIC_OR_LOW_RISK AND metadata public_or_synthetic is exactly True,
attesting the complete input. Private/default, price/quota, requested policy filters
and no-fallback boundaries remain. No automatic CLI classification or new service.
Eight saved root paths: provider adapters openai_compatible.py/openrouter.py,
tests/test_openrouter_free_models.py, docs/architecture.md, docs/decisions.md,
packages/ai_provider/docs/interface.md and source-state.md,
docs/decisions/ADR-063-explicit-public-input-privacy-exception.md (untracked).
179 focused PASS plus Ruff/format/Pyright. Frozen full 2649 PASS/3 SKIP/2 FAIL:
native diagnostic and saved shell interrupt fixtures race on an empty PID file.
No EP advisory launched, no green full claim. The older strict-entitlement section
of source-state.md needs consistency review before final integration.

EQ: artifacts/cli-shell-fixture-completion-20261021eq/results.md and closure.json.
CLOSED INCOMPLETE after one CLI launch (native 0/CLI 1, 110 tools, mcp_tool_call).
Model saved an atomic PID publisher/partial-write companions in its isolated tree,
but changed four protected Unicode test bodies. Honest repair report; no independent
full acceptance or frozen review. Reported 64 affected/2624 full passes remain
unaccepted model claims. Owned root PID 28092/birth134370924988543567 independently
absent and cleanup verified. Unused review is CLOSED; no reuse of its deadline.
All run controllers, reports and seals remain immutable.
Prospective portable_guard.py fixes path normalization in the private command
checker: 6 positive/10 negative offline controls PASS. Not installed into EQ.
Exact denied command spellings unavailable; do not attribute every denial to it.
Actual Greek read/MCP ASCII-serialized/write roundtrip PASS. Unicode corruption
origin in the native/model path remains UNKNOWN; raw payloads were not retained.

## Next baseline action and acceptance

DETERMINISTIC PREREQUISITE COMPLETED 2026-10-22. Fresh CLI baseline acceptance
evidence for the EL/EQ/EU follow-up has been produced: full suite 2768 passed/3
skipped, provider group 534 passed, agent group 383 passed/2 skipped, ruff/format
and pyright clean. The shell/PID fixture work, literal fidelity, EP public-input
exception and ADR-064 warning policy are integrated and validated. Evidence is in
`artifacts/cli-baseline-acceptance-20261022ev/`.

Remaining: live CLI model-quality, continuity, fallback and representative
daily-use acceptance on an owner-selected paid route with fresh named bounds.
Original tests, meaningful companions, real execution, both faithful repair/frozen
review reports, frozen independent validation and owned cleanup remain required
for that live phase. No guard bypass, host code/report rescue, blind full pilot,
historical replay or regrading. Only accepted candidate code may be integrated;
any future integration must be followed by fresh combined EP checks. No broad new
pilot at closeout. Local finite tests and useful standing allowance work are
authorized, but fresh named bounds and all admission guards remain required.

RESOLVED — MCP recovered-warning semantics, decided 2026-10-22 as ADR-064
(owner selected Option C for both failure kinds): an MCP tool-call failure that
call identity cannot resolve (unresolved call identity, and same-tool retry
under a new call id) is a visible warning beside a completed result, not a
failed run, when the run independently proves completion. Fatal, incomplete and
unfinished runs still fail and exit non-zero; unresolved reasons are retained
verbatim. Implemented in f90b58a with 10 new tests. Privacy exception approval
was separate. One residual question remains unimplemented: whether the
"identified but never retried" case should stay a warning or return to being a
failure. It currently warns, per the approved general rule. Do not change it
without owner instruction.

## Next-session allowance deliberation - explicitly requested by owner

Codex weekly limit is approaching (owner observation; latest numeric quota unknown).
Compare new Copilot subscription, increased Codex limits, OpenRouter $10 credit
purchase/account upgrade, and suitable free trials. Read existing provider knowledge
FIRST: packages/ai_provider/docs/source-state.md; ADR-021/031/042/052 explain access,
billing and quality floors. Published historical offers include OpenRouter free-day
ceiling changes after $10 credits, Requesty, Groq, Cerebras/Zed trials and Antigravity.
Most broad research is dated 2026-10-13; scoped updates 2026-10-21. Refresh current
official offers, actual account quotas/reset times and CLI integration before advice.
Do not equate quota with model availability, private routing or coding quality.
Compare marginal cost, usable strong-agent capacity and baseline development fit.
Codex subscription and OpenAI API billing are distinct. No purchase/signup/upgrade,
new provider, disclosure or paid inference is authorized merely by this discussion.

Stale observations, not admission evidence: EI 2026-10-21 13:38Z Codex primary56%
used/secondary71%; Copilot0 remaining; Kiro50/50 used. EO20:50Z OpenRouter0/50 used,
50 remaining. Antigravity capacity/shared permissions unverified. Explicit local
Copilot/Antigravity binaries exist under .tools; PATH absence is not proof missing.
Use ai_provider safe credential/account facilities, never inspect .env.
No new generation/account call in this closeout; no busywork to empty a counter.

## Handoff prompt for the next (paid-model) session

Copy-paste block, written 2026-10-22. Purpose: resume the deferred CLI
baseline acceptance work now that paid-tier allowance has refreshed.

```text
Resume CLI baseline acceptance work in C:\Users\Jakub\PycharmProjects\AI-projects
on branch feature/cli-readiness-and-tool-parity (clean tree, merged into
develop, no push to origin, master untouched).

GOAL (highest priority): produce fresh CLI baseline acceptance evidence for the
EL/EQ/EU follow-up. The previous attempt was deferred because it ran on a free
tier; the owner's paid allowance has refreshed, so this is now active.

READ FIRST, before changing anything:
- AGENTS.md (this is the behavioural baseline; ask before assuming)
- CURRENT_CONTEXT.md, especially "Next baseline action and acceptance" and
  "Committed baseline progress"
- docs/repo-assistant/acceptance-criteria.md, baseline-gap.md,
  development-roadmap.md
- docs/decisions.md and the ADRs it indexes (ADR-064 was added 2026-10-22)
- The preserved EL originals and the EQ findings, per the plan below

THE PLAN: read EQ/results.md and EP/results.md; prepare a NEW bounded
controller to restore literal fidelity, admit equivalent declared Windows
paths, and complete the shell/PID fixture work. Prefer scoped byte-faithful
file operations to reconstructing large files through prose. Test the final
composed task with ci/bz-derived coherence checks, and account for working-root
AGENTS before HEAD snapshots.

HARD CONSTRAINTS:
- Original tests, meaningful companions, real execution, both faithful repair
  and frozen review reports, frozen independent validation and owned cleanup
  remain required.
- NO guard bypass, host code/report rescue, blind full pilot, historical
  replay or regrading.
- Only accepted candidate code may be integrated; then run fresh combined EP
  checks.
- No broad new pilot at closeout.
- Local finite tests and useful standing allowance work are authorized, but
  fresh named bounds and all admission guards remain required.
- Do not read .env directly. Load credentials only through the normal Python
  harness (for example uv run --env-file .env).
- No git push or merge to origin/master without explicit owner approval.

VALIDATION AFTER ANY CODE CHANGE:
- python -m uv run --offline --no-sync python scripts/run-tests.py full
  (baseline before this slice: 2768 passed, 3 skipped, 0 failed)
- python -m uv run --offline --no-sync python -m ruff check .
- python -m uv run --offline --no-sync python -m ruff format --check .
- python -m uv run --offline --no-sync python -m pyright

ALREADY RESOLVED, do not redo: ADR-064 makes an unresolvable MCP tool-call
failure a visible warning beside a completed result, not a failed run. Fatal,
incomplete and unfinished runs still exit non-zero.

OPEN, DO NOT IMPLEMENT WITHOUT OWNER WORD: whether the "identified MCP call
never retried" case should stay a warning or return to being a failure. It
currently warns.

NOT BLOCKED, but a decision boundary: the model-capability readers exist
(ai_provider.openrouter_endpoints, swe_bench_scores, aider_polyglot_scores)
and dated data is saved under artifacts/model-capability-priors-20261022/. The
Orchestrator keeps routing from the declared catalog. Turning these priors into
a per-model grade is an owner decision; present a decision brief, do not
implement a scoring rule unapproved.
```


Read current AGENTS.md including nested instructions; docs/repo-assistant/
acceptance-criteria.md, baseline-gap.md and relevant development-roadmap.md sections.
Private plans: docs/plans/repo-assistant-cli-parity-plan.md,
cli-development-readiness-review.md, shared-agent-capabilities-options.md,
research-review-orchestration-plan.md; Orchestrator DOCX for later quota supervisor
planning. docs/logging-and-artifact-structure-plan.md governs immediate failure tracing.
Prompt source: docs/prompt-library.md (End of Day, DoD Closeout, Session Boundary).
No .env inspection, installs/downloads, new dependencies/providers/services,
model/runtime/context changes, raw prompt/private reasoning logs, publication,
push/merge/branch cleanup. Fresh scoped grants do not revive consumed runs.
Consult python-tools skill/get_python_environment before every Python command.
Established bootstrap: configured system Python -m uv run --offline --no-sync;
existing venv only. Long commands yield10000; completion polls >=30000.

## Saved continuation prompt for next work session

Continue baseline CLI work in C:\Users\Jakub\PycharmProjects\AI-projects.
ATTENDED: no unattended window, sleep, wake or scheduling. Read CURRENT_CONTEXT.md
first, including this saved prompt, then current AGENTS.md and relevant CLI plans.
Verify branch feature/cli-readiness-and-tool-parity, checkpoint 4611dfa and the
14 deliberately preserved dirty paths. Baseline remains INCOMPLETE.

First deliberate about the next allowance: Codex weekly limit is approaching.
Compare expanding Codex limits, a Copilot subscription, OpenRouter's $10 account
upgrade/credit purchase, and suitable free trials. Start with ai_provider's
source-state.md and existing access/quality decisions, then refresh relevant
official offers and safe account observations.Afterwards search the internet for alternatives, especially current offers.
Recommend usable strong CLI-agent capacity for baseline work; ask at the purchase/provider/privacy decision boundary.
No purchase, signup or new inference route is authorized by this comparison.

Then continue the concrete baseline plan: read EQ/results.md and EP/results.md,
preserve EL originals and all consumed trials, and prepare a NEW guarded controller
for faithful shell/PID fixture completion. Use the prospectively tested portable
checker; preserve Unicode originals, meaningful companions, real tests, both reports,
frozen independent validation and owned cleanup. Verify final composed-task coherence
including working-root instructions before snapshots. Never bypass guards, rescue
failed reports, replay trials or launch a blind full pilot. Ask at material decisions.


## Delegated matcher slice ? COMPLETE (2026-10-23)

Implemented `ai_provider.route_family_matcher.propose_route_family`, its frozen
result, 19 tests, provider-group registration and proposal-only mapping docs.
No inference/admission/fallback integration. Existing table unchanged.
Validation: 19 matcher tests plus 75 neighbouring reader/band/test-group tests
passed with `python -m pytest ... -q`; repository-venv Ruff check/format and
module Pyright passed. Saved JSON files are serialized reader outputs, restored
using CapabilityScore; raw-reader network functions were deliberately not called.
Reproduction: 13/18 agree on confidence and a cited row; 5 disagree. GPT-5.5
selects closer SWE GPT-5.2 rather than Aider GPT-5. GPT-5.1 and GPT-5 Mini
(OpenAI and Requesty routes) select normalized exact SWE rows rather than the
table's family Aider GPT-5 row. Preserve these discrepancies for human review;
do not tune away the snapshot evidence. Unknown families remain conservative
false negatives; effort suffixes always carry a stated gap.
Only matcher module/tests, one registration line, appended mapping documentation
and this handoff were edited by this delegation. Other active work stays owned
by its original worker. Next action: review the five proposals against the
manual mapping; completion condition for this delegated implementation is met.


## 2026-10-23 attended Go review diagnostics

Prepared and offline-verified read-only Go continuation trial a at f728fce;
owner then confirmed Extra Usage disabled and standing approval for comparable
bounded Go runs. Trials a/b stopped on second-completion 60-second HTTP response
waits; c returned at 72 seconds but exhausted 4096 tokens; d returned at 124 seconds
and exhausted 8192 tokens with zero visible report text. Each performed five valid
inspections, stopped before turn two and verified owned cleanup. Original failed
receipts remain under artifacts/go-review-continuation-prep-20261023[a-d]/.
Eight total provider attempts, six returned responses; usage on timeouts is unknown.
No raw reasoning logging, model/billing fallback or account setting change.

The private worker now retains actual tool receipts on model failure and safe
transport-stage diagnostics; 34 offline controls and independent scripted audits
pass. Production fixes retain visible incomplete native reports (f4ef561) and
Go Kimi origin-bound continuation state (518b8e1). Official Kimi guidance requires
preserved reasoning and recommends >=16000 output tokens. Changing admission's
8192 default versus exposing an explicit neutral CLI option remains an owner
choice. Do not silently raise output after admission. e remains an unlaunched
draft. Initial post-adapter full run failed an external-agent fixture that watched
the real repository and captured concurrent artifact writes; 48d31f2 isolates it,
28 module tests pass, full root rerun 2778 pass / 9 skip in 237.67 seconds.
The earlier pre-push flake's missing
original traceback still prevents asserting it had this same cause.


## 2026-10-24 Go default and diagnostic cleanup follow-up

Owner selected automatic 16000-token native admission for exactly Go Kimi K2.7
Code, committed 720378d. 98 focused checks passed. Initial full suite: 2785 pass,
1 failure, 9 skip; diagnostic exit_cleanup_error lacked the expected warning note.
Original receipt preserved in go-kimi-default-output-full-suite-20261023.log.
A traced module run passed all 23 original cases; original trigger stays unknown.
Four deterministic controls reproduced cancellation during cleanup losing the
warning and sometimes skipping remaining root cleanup. 75ebd83 repairs those
paths without extending the cleanup deadline; 91 focused checks and full root
2790 pass / 9 skip (224.90 seconds). Before/after evidence stays in artifacts.

Fresh read-only Go trial 20261024a was sealed at 75ebd83: 37 offline controls,
real scripted CLI composition, admission/transport budget agreement and independent
owned audit passed. Automatic approval review rejected live launch twice before
execution, requiring user authorization naming the exact repository payload and
OpenCode destination beyond standing bounded-Go approval. Files were independently
compared to already-pushed origin/develop, with no private plans or .env in fixture;
the reviewer still rejected. No hosted calls or live launch marker were created.
An explicit payload/destination approval request is pending. Preserve unconsumed
trial state; after HEAD changes prepare a fresh exclusive seal instead of editing
its old manifest. This is a platform approval block, not provider/model failure.


## 2026-10-24 explicit payload approval and Go continuation result

Owner explicitly approved the declared repository payload and OpenCode destination
after the platform review block. Fresh 20261024b, sealed at a1ce8d0, then completed:
two actual coding-chat invocations in one saved session, four provider responses,
nine successful inspections, 171.46 seconds, frozen source/tests/index/dependencies
and verified owned cleanup. Production admission and transport both used 16000.
Transient continuation was observed and forwarded within each tool loop; only
visible conversation was restored across invocations, under ADR-055's existing
persistence boundary. 96082 provider-reported input plus 12719 output tokens;
reported dollar cost unavailable. No model edits/shell/tests or route/billing switch.

Independent structural audit passed. Scoped static code observations/no-findings
assessment are supported, but report quality is not accepted unqualified. First
report says no provider calls were performed; four host completion calls actually
returned. External Codex corrects that unqualified claim and attributes detection
externally, not to automatic CLI protection. Second report duplicates the reserved
SUMMARY heading. Original reports/receipts remain unchanged; no silent rewrite,
extended allowance or retrospective promotion of earlier failures. Structural Go
continuity is demonstrated; clean report fidelity and full coding/orchestrated/
fallback baseline remain incomplete. See local 20261024b/results.md and separate
independent-report-assessment.json for exact evidence and limitations.

## 2026-10-24 - Go primary with local support and scrutiny evidence repair

Owner retained local auxiliary/scrutiny, permitted wholly paid-tier escalation
only after evidence of local inadequacy, and prioritized adequate local context,
output and time over token economy. The durable clarification is indexed in
docs/decisions.md; production ADR-025 defaults stay unchanged.

The first fresh hybrid c trial stopped at frozen-review scrutiny after 16 calls
(12 Go, 4 local), 22 tools and 272.46 seconds. Both model test runs and the
independent oracle passed; worker/runtime cleanup passed. Investigation found
that unchanged review phases supplied neither changed-file excerpts nor native
inspection/test receipts to scrutiny. Original trial remains failed.

Repairs: e2936f6 closes run-store connections after commit/rollback; 107c17d
supplies bounded native read/diff/test receipts; c96cc92 gives the CLI sole
rendered summary heading while preserving raw responses; c6c2f34 handles empty
bold Changed labels and clarifies host bookkeeping in response instructions.
Latest full suite: 2801 passed, 9 skipped in 238.94 seconds.

Two fresh local-only diagnostic calls with 65536 context and 16384 output tokens
passed the supported review and requested revision for synthetic 99-tests/hash
claims. No paid requests, original fixture changes or cleanup uncertainty.
These controls supported retaining local review instead of escalating.

Fresh hybrid e at 6885708 completed coding and frozen review with 11 Go and four
local calls, 19 tools and 328.19 seconds. Each phase executed ten passing tests,
five originals and five model-authored companions. The independent 3616-case
oracle, model-only source reconstruction, frozen review, saved-report continuity
and cleanup passed. Go reported 215382 input / 5447 output tokens; local reported
40492 / 5771. Actual dollar cost and account remaining allowance were unobserved.

Reporting remains qualified: both model reports called CLI bookkeeping DBs
unrelated and unchanged, although the host created/updated them. Local scrutiny
did not correct this. Subsequent prompt clarification is implemented and tested,
not a new live adherence pass or a retrospective rewrite. This bounded coding
result establishes neither universal report fidelity nor broader quality parity;
live fallback and scrutiny-fed repair were not exercised. Evidence is preserved
in artifacts/cli-baseline-hybrid-successor-20261024{c,e}/,
artifacts/local-scrutiny-evidence-20261024d/ and
artifacts/hybrid-live-assessment-20261024/. Five matcher proposals remain unapplied.

## 2026-10-24 - Bookkeeping review trial f and auxiliary-pass repair

Fresh read-only frozen-review trial `f` asked whether the native production
review produces a faithful report after the final-response contract is actually
delivered. Preparation found and committed three production defects with failing
regressions first: d7c102c delivered the contract to native agents, d7423ca kept
handoff status inspection from refreshing the index, and 4a6e6d9 stopped
read-only diff from refreshing index metadata.

Live `f` used 6 calls (1 local auxiliary, 4 Go coding, 1 local scrutiny),
11 proposed tools and 199.70 seconds, with verified owned cleanup. The Go primary
and local scrutiny completed. The local auxiliary pass failed at its first call
because gpt-oss:20b proposed an unavailable tool in a tool-free pass; the harness
refused it before execution. The workflow is `completed_with_auxiliary_errors`
with `stop_reason=Unknown proposed tool`; this is a production auxiliary-pass
defect, not a Go/provider failure.

Both 10-test runs and the independent 3616-case oracle passed. Frozen inputs and
index, original tests, inherited companions, raw saved-report continuity and the
single SUMMARY heading were independently verified. Usage was 85847 input and
4099 output provider-reported tokens; dollar cost was unavailable. The audit
records mechanical acceptance but not clean workflow acceptance. Independent
agent inspection found the report supported by its 10 tool receipts with no
material false claim; a minor scope imprecision describes whole-worktree Git
status as the two reviewed files, and bookkeeping attribution was not exercised
because the report never mentioned the host databases it saw.

Repairs after the trial: c2a82d7 rejects auxiliary advice that proposes tools or
is empty/truncated, with a clear failure reason, instead of displaying it; 7478fc8
recognises `**Changed:**` in the closeout preview. Focused checks and the full
suite (2809 passed, 9 skipped) pass. The consumed trial keeps its original
verdict; the integrated live effect of the repairs is not established.

## 2026-10-24 - Trial g: auxiliary contract alignment and bookkeeping attribution

Fresh read-only frozen-review trial `g` tested two questions left open by `f`:
does a tool-free auxiliary proposal become a recorded auxiliary failure instead
of a run-level safety stop, and does the primary report attribute host
session/orchestration bookkeeping correctly? The candidate stayed the unchanged
Go-authored `e` implementation and five companions; five originals remained
protected. No trial was replayed or regraded.

Preparation aligned the harness with production's `run_auxiliary_panel`: an
advisory proposal is recorded in `advisory_tool_proposals`, never executed and
never counted, while primary unknown tools still stop and primary known tools
still count. `test_auxiliary_contract.py` proves this deterministically. The
declared 9-file guard suite passed 107/107; a first whole-directory run exposed
28 failures in stale two-phase copies, which are preserved rather than rewritten
or deleted. One scripted production workflow (8 calls, 5 tools, network
disabled), an independent offline audit, the seal and an owned smoke all passed.

Live `g` used 6 calls (1 local auxiliary, 4 Go coding, 1 local scrutiny), 8
executed tools and 85.43 seconds, with verified worker/runtime cleanup. The
auxiliary pass again proposed `repo_browser.git_status`; the harness recorded it
and did not stop, so `stop_reason` is `None`. Production's own stage classified
the pass as "Auxiliary advice proposed tools in a tool-free pass" and the run
reports `completed_with_auxiliary_errors`. The Go report named both untracked
host entries (`orchestration.sqlite3`, `session.sqlite3`) as host bookkeeping,
distinguished them from the `AM` candidate files, and made no
predate/unchanged/unrelated claim. Both 10-test runs and the 3616-case oracle
passed; frozen inputs/index and the no-edit review were verified.

Usage was 86094 input and 3893 output provider-reported tokens across 6 calls
with complete coverage; dollar cost and account quota were unavailable. The
independent live audit records mechanical and clean workflow acceptance for this
bounded question, auxiliary alignment and bookkeeping attribution. Scrutiny
passed with one harmless wording note about grouping the five originals. This
does not establish general report fidelity, live fallback, scrutiny-fed repair or
a clean paid-agent baseline. Evidence: artifacts/cli-bookkeeping-attribution-20261024g/.

## 2026-10-24 - Consolidated C1-C6 IDE-independence offline contract

The M5 gap was the absence of a single deterministic contract showing the
approved capability set works with PyCharm unavailable. The new
`tests/test_ide_independent_capabilities.py` exercises each capability through
the shared coding registry in a workspace with no `data/pycharm-mcp.json`:

- C1 real Git status/diff plus read/list/find/grep and create/edit, with the
  index tree unchanged by reads.
- C2 the canonical portable review skill and working repository instructions.
- C3 `python_runtime` plus a real unittest run using the current interpreter.
- C4 `fetch_url` provenance through an injected test fetcher and the real
  private-network refusal.
- C5 Jedi definitions and preview-then-apply rename, with no mutation before
  apply.
- C6 host-owned child process continuity and refusal after supervisor close.

Two further checks prove the common surface is complete and never imports the
MCP SDK in a fresh process, and that a valid IDE configuration only adds the
three read-only IDE tools while removal restores the identical surface.

Eight tests pass; Ruff, formatting and Pyright are clean. This is deterministic
offline composition evidence, not installed-client or live-model acceptance.
The C4 success path uses an injected test fetcher; C5 requires the optional Jedi
extra; C6 covers host-owned child continuity rather than a cross-provider route
switch. M5 still needs installed-client/live evidence. Slice B (live fallback)
remains blocked pending the owner's route/billing/trigger decision.

## 2026-10-24 - Slice B completed: whole-set fallback walks to a real completion

Owner direction was that fallback "only makes sense if it tries whole set", and
that a cheaper tier must stay admissible from an allowance initial so a free
route with a capable model and enough allowance is used and prioritised.

Implemented:

- `fallback_candidates` admits any tier the task cost policy allows
  (`cost_policy_allows(entry.tier, initial.tier)`) instead of demanding the exact
  initial tier. `fallback_diagnostics` now reports "higher cost tier" rather than
  "different cost tier". The old same-tier invariant test was replaced by
  `test_free_tier_route_is_admitted_and_prioritised_from_allowance_initial` and a
  ceiling assertion in `tests/test_gemini_cli.py`.
- `tests/test_execution_fallback.py::test_session_walks_the_whole_ordered_set_until_a_route_completes`
  proves the loop continues across three failing fallbacks and stops only when a
  route finishes.
- `OpenCodeGoSourceInfo.account_allowance` reads
  `GET https://opencode.ai/zen/go/v1/usage` with the Go inference key and
  normalizes rolling/weekly/monthly percentages plus reset times;
  `read_opencode_go_allowance` adds `binding_window`, `model_limits_usd` and
  `usage_scope`. Account-wide percentages and published per-model dollar caps stay
  separate facts.
- `scripts/fallback-acceptance.py` takes repeatable `--fallback-route`, builds the
  catalog from that order, records the session's ready set and attempt sequence,
  and can force a declared synthetic limit on one external route with
  `--simulate-limit-on` so the walk must continue.

Two bounded live runs passed and one earlier attempt is preserved as a failure:

- `artifacts/fallback-acceptance-20261024-151618/`: whole set held 4/4, 0
  unaccounted; `simulated-codex:usage_limit -> requesty free:finished`; 6 real free
  calls, 18529 tokens, reported cost $0.00.
- `artifacts/fallback-acceptance-20261024-151909/`: two hops,
  `simulated-codex:usage_limit -> kiro:usage_limit (declared synthetic) ->
  requesty free:finished`; 5 real free calls, 15523 tokens, $0.00.
- `artifacts/fallback-acceptance-20261024-151449/`: failed attempt. The free route
  did real tool work but exhausted the default `--max-action-rounds 3`. The harness
  now uses a still-finite 6 rounds; the failure is kept and not regraded.

Defect found and fixed on the way: the preflight provider probe constructed
`OpenAICompatibleChatClient` directly, which raised `KeyError` for
`opencode-go` because that client has no default base URL, and it probed
`{chat_base}/models`, a 404 for Go. The probe now uses `create_chat_client` and
Go's real model-inventory URL, and session admission stays configuration-only so a
transient provider error cannot shrink the candidate set. `TeeOutput.flush` no
longer raises during interpreter shutdown when the terminal stream is already
closed.

Remaining limits: the completing route was the free Requesty route in both runs, so
a live walk that continues into `opencode-go` or a CLI client is still unexercised.
Kiro reports its exhausted plan as a generic process error, not a usage limit, which
is why the second hop's failure had to be declared synthetic. Fallback still switches
only on usage-limit/overload signals.

## 2026-10-25 — Public source integration and README reconciliation

Release preparation integrates restricted reviewed-input execution and corrections
to CLI failure records, stale review evidence and validation status after repair.
The README combines the remote master introduction with implementation-checked
capabilities and explicit acceptance limits. Offline software validation does not
establish general model quality or complete coding/research acceptance.

Immediate handoffs and private window plans stay local. Two public reference notes
now have documentation paths: [reviewer output formatting](research/reviewer-output-format-20261023.md)
and the [route-family matcher proposal](research/route-family-matcher-proposal-20261023.md).
Their dated findings and proposal status are preserved. Existing published history
is retained; removing private paths from the current tip does not erase history.
