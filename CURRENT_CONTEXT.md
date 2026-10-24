# Current task - ATTENDED; Slice B (live whole-set fallback) complete, M5 next

Branch: develop. Latest production code: ca03d1b; handoff commit follows.
No active inference job, local server, timer, sleep or unattended window.
Owner-authorized logical commits and push to develop remain in scope.

**Status: INCOMPLETE.** Slice B is COMPLETE; the wider paid-agent CLI baseline is
not established. Next imperative action: M5 installed-client/live parity (below).

## Owner authority and current policy

Keep auxiliary review and scrutiny local for now (ADR-025). A wholly paid-tier
workflow is permissible only after evidence establishes local-model inadequacy.
Local token economy is secondary to sufficient context, output and time; retain
finite run/cleanup bounds, count every role and report hosted usage separately.

Standing comparable bounded Go acceptance authorization remains; owner confirmed
Extra Usage disabled. No paid overage, unbounded retries, model/billing switches,
new private payloads, raw-prompt/private-reasoning logging or credential exposure.
Native Go Kimi default is 16000 output tokens before admission; explicit caps win.
Existing endpoint: https://opencode.ai/inference/go/openai/v1/chat/completions.
Fresh synthetic fixture tasks/source/tests, committed AGENTS and their execution
history were used; no private plans or .env values were transmitted/logged.
Closeouts begin with exact ## **SUMMARY** and Changed/Validated/Notes bullets.

## Completed implementation and validation

Slice B: the fallback now walks the whole ordered candidate set and admits cheaper
tiers than the initial route, so the free Requesty route can complete after a
usage-limited primary. `fallback_candidates` uses
`cost_policy_allows(entry.tier, initial.tier)`; `fallback_diagnostics` reports
"higher cost tier". OpenCode Go account usage is readable from
`GET https://opencode.ai/zen/go/v1/usage` (account-wide percentages) with the
published per-model dollar caps reported separately. `scripts/fallback-acceptance.py`
takes repeatable `--fallback-route`, records the ready set and attempt sequence, and
supports a declared `--simulate-limit-on` for one external route.

Live evidence (no trial replayed or regraded):

- artifacts/fallback-acceptance-20261024-151618/ passed. Whole set held 4/4, 0
  unaccounted. `simulated-codex:usage_limit -> requesty free:finished`, 6 real free
  calls, 18529 tokens, $0.00.
- artifacts/fallback-acceptance-20261024-151909/ passed. Two hops,
  `simulated-codex:usage_limit -> kiro:usage_limit (declared synthetic) ->
  requesty free:finished`, 5 real free calls, 15523 tokens, $0.00.
- artifacts/fallback-acceptance-20261024-151449/ preserved failure: the free route
  did real tool work but exhausted the default `--max-action-rounds 3`. Fixture
  bound, not a fallback defect; the harness now uses a still-finite 6 rounds.

Earlier completed work: d7c102c delivers the final-response contract to native
agents; d7423ca and 4a6e6d9 stop read-only handoff status/diff inspection from
refreshing the Git index; c2a82d7 rejects auxiliary advice that proposes tools or is
empty/truncated; 7478fc8 recognises `**Changed:**` in the closeout preview. Slice C
offline C1-C6 lives in `tests/test_ide_independent_capabilities.py` (8 tests).

## Consumed live evidence - do not replay or rewrite verdicts

artifacts/cli-baseline-hybrid-successor-20261024c/: FAILED private acceptance.
16 calls (12 Go, 4 local), 22 tools, 272.46 seconds. Source/tests and oracle
passed; frozen-review scrutiny lacked actual read/diff/test receipts, requested
revision, and private acceptance stopped. Both runtime and worker cleanup passed.
Original reports/logs preserved. This wrapper stop was not a Go service failure.

artifacts/local-scrutiny-evidence-20261024d/: fresh local-only diagnostic,
2 real GPT-OSS calls, 65536 context / 16384 output, 66.08 seconds. Supported
candidate passed (9/10); synthetic 99-tests/hash-verification claim required
revision. Original fixture remained unchanged; cleanup verified; no paid calls.
This does not regrade c or establish a general truth guarantee.

artifacts/cli-baseline-hybrid-successor-20261024e/: fresh frozen HEAD 6885708.
313 guard tests, scripted production workflow, independent audit and owned launch
smoke passed before live. Existing coding-chat --orchestrated completed coding
and frozen review: 15 calls (11 Go primary, 2 local auxiliary, 2 local scrutiny),
19 tools, 328.19 seconds. Both phases ran 10 tests: 5 originals preserved, 5
meaningful companions added. Independent 3616-case oracle, raw saved-report
continuity, model-only writes, frozen review and owned cleanup all verified.
Usage: Go 215382 input + 5447 output; local 40492 input + 5771 output tokens.
Independent mechanical/substantive evidence:
artifacts/hybrid-live-assessment-20261024/assessment-e.json and substantive-e.json.

artifacts/cli-bookkeeping-review-20261024f/: completed_with_auxiliary_errors.
Fresh read-only frozen review after d7c102c delivered the final-response contract.
6 calls (1 local auxiliary, 4 Go coding, 1 local scrutiny), 11 proposed tools
(10 executed + 1 refused auxiliary proposal), 199.70 seconds. Go primary and
scrutiny completed; the local auxiliary pass proposed an unavailable tool in a
tool-free pass and was refused before execution. Both 10-test runs and the
3616-case oracle passed; frozen inputs/index, report continuity and cleanup were
verified. Usage: 85847 input / 4099 output tokens; dollar cost unavailable.
Independent agent inspection supports the report with no material false claim;
one minor Git-scope imprecision; bookkeeping attribution was not exercised.
The first independent audit attempt failed on a harness predicate expecting one
timing observation per admitted call (6) while the failed auxiliary call has none
(5); the audit script was corrected and the re-run passed. Original verdict kept.

artifacts/cli-bookkeeping-attribution-20261024g/: completed_with_auxiliary_errors,
auxiliary contract aligned, attribution exercised. Fresh read-only review of the
unchanged e candidate. 6 calls (1 local auxiliary, 4 Go coding, 1 local scrutiny),
8 executed tools, 85.43 seconds, verified worker/runtime cleanup. The auxiliary
pass again proposed `repo_browser.git_status`; it is now recorded in
`advisory_tool_proposals`, executed and counted nowhere, so `stop_reason` is
`None`. Production's own `auxiliary_panel` stage classifies it as "Auxiliary
advice proposed tools in a tool-free pass". The primary report names both
untracked host entries (`orchestration.sqlite3`, `session.sqlite3`) as host
bookkeeping, distinguishes them from the `AM` candidate files, and makes no
predate/unchanged/unrelated claim. Both 10-test runs and the 3616-case oracle
passed; frozen inputs/index and no-edit review verified. Usage: 86094 input /
3893 output tokens; dollar cost and account quota unavailable. Scrutiny passed
with one harmless wording note about grouping the five originals. First
whole-directory guard run exposed 28 failures in stale two-phase copies; those
are preserved, and the declared 9-file suite passes 107/107.

## Remaining limits / next independent acceptance scope

Slice B establishes a live whole-set fallback that reaches a real completion on a
different billing source. It does not establish a live walk that continues *into*
`opencode-go` or a CLI client, because the completing route was the free Requesty
route in both runs. Kiro reports its exhausted plan as a generic process error
rather than a usage limit, so the second hop's failure was declared synthetic.
Fallback still switches only on usage-limit/overload signals.

g establishes the auxiliary-contract alignment and explicit bookkeeping
attribution for this bounded read-only question. It does not establish general
report fidelity, scrutiny-fed repair or a clean paid-agent baseline. Five
matcher disagreements remain unapplied: ask before changing mapping. Post-trial
current-render files are labelled host re-renderings, not original model delivery.

Slice C offline consolidation is implemented in
`tests/test_ide_independent_capabilities.py`: C1-C6 each have a deterministic
contract through the shared coding registry with no IDE configuration, the
common surface never imports the MCP SDK in a fresh process, and a valid IDE
configuration is purely additive. Remaining M5 work is installed-client/live
parity, not missing offline capability. The C4 success path uses an injected test
fetcher; C5 requires the optional Jedi extra; C6 covers host-owned child
continuity, not a cross-provider route switch.

Next actions, in order:

1. M5 installed-client/live parity. Reuse the consolidated offline contract and
   add only the missing installed-client evidence; do not redo the deterministic
   surface checks. Completion condition: at least one capability set exercised
   through an installed client against a real repository, with receipts.
2. Optional follow-up, owner decision needed: add an OpenRouter free catalog route
   so its real account allowance can participate in fallback. It is not a catalog
   route today, so it cannot be selected.

Fallback ordering is configurable and evidence-derived: `[fallback]`
`priority`/`exclude`/`allow_cost_escalation`, plus `--fallback-priority` and
`--fallback-exclude` per invocation. The local default order is Requesty free,
opencode-go, kiro, copilot, antigravity-pro, antigravity-flash, derived from
`artifacts/allowance-inventory-20261024/`. Two recorded hazards: `kiro_usage`
reports plan coverage, never remaining balance, and hitting any Go account window
blocks the whole `opencode-go` provider including its free models.

Do not replay c, d, e, f or g, and do not regrade them.

Relevant private plans remain repo-assistant-cli-parity-plan.md and
opencode-go-integration-first-20261022.md; old unattended plan is CLOSED.
Historical continuity trials and earlier failures remain in docs/session-history.md.
