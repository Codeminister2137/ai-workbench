# E2E behavior triage - run 60066ae7c5c34084b9a02373055c5b04

## INCOMPLETE - API and contract evidence checked; browser and run-specific outcomes unverified

Follow-up to [the corpus audit](e2e-corpus-audit-73249b26.md). Checked on 2026-11-21 against `http://127.0.0.1:8766`, serve `develop` commit `7e23229e59df`, started `2026-11-21T14:54:03.418027+00:00`; inspected worktree HEAD `7e23229e59dff4110eb7f31ad86e011560dd1643`. Served `/app.js` bytes equal the worktree file. This report changes no historical verdict and grants no promotion approval.

All 56 action-bearing source reports and 48 directly linked follow-up records were fetched individually over HTTP and compared for full JSON equality with shared on-disk records. All original tasks were fetched, and all later same-commit reports were inspected including actions, expectations, notes, and step results. Five explicit consolidation links were resolved to their full target records. All 280 history references on these tasks resolve to existing reports matching area, commit, and verdict (15 distinct reports). History is per **area**, not per exact item id: behavior and regression kinds can legitimately share an area. An initial item-id equality diagnostic was too strict; inspection of `history_for_area` established the correct contract, and the corrected check passed.

No current product failure was reproduced by these probes. That is not proof that none remain. No fresh task was filed, no consumed checklist was resubmitted, and no production settings were changed by this investigation's tools. The tools performed HTTP GETs and local diagnostics/tests; this statement does not describe inference or host bookkeeping effects.

## Eight missing direct links

| Original task | Current reproduction / checked chain | Disposition |
| --- | --- | --- |
| `03dbaccf4df3441783bc88d5a198ccca` | Served JS uses `Date.now()` for elapsed time, but deliberately disables its timer when `prefers-reduced-motion: reduce` matches. This explains static `Working 0s` in reduced motion. `test_chat_agent_mode_toggle_and_staged` checks the source contract. | Static reduced-motion state consistent with original expectation. OS setup guidance and actual pending-reply display remain **UNVERIFIED** without a browser; no model turn sent. |
| `220bb7f5e7104ccf9c5e06309f7f5714` | Current `generate d16ed73 --dry-run`: `needs_pointers: true`, step `grounded: false`. Later `dbc7afca` has two performed steps and pass, but is only historical corroboration. | Original false-grounding failure **does not reproduce**. |
| `27cedba6a2864dcebc2ae78fa2a180f7` | GET `/api/chat/agent-config`: enabled true, approval yolo; served JS has Agent controls. Chat-agent fixture tests cover staging, review and auto-apply. Later `f2eb528a` fails for vague guidance; latest `ea285cfb` is bad-test, linked to `b762fc6c` exact-locator/subjects fix. | Missing feature flag **does not reproduce** at API/source boundary. Actual controls, pending status, apply/reject and model-backed behavior **UNVERIFIED**. Current yolo is observed configuration, not a setting changed for this test. |
| `405769cec55a4de49dee21e764bcf3e3` | Served JS labels history `Recent verdicts for this area (all merges)`, supplies per-step pass/fail and subjects on every item. Latest `014f493f` is bad-test for an unfindable multi-item checklist; its full follow-up `aadea311` requires exact locators. Pointer-mission and UI contracts pass. | Wording/per-step contract superseded. Visual readability and usability **UNVERIFIED**. The old first-item-only expectation is itself superseded by the subjects-on-every-item resolution. |
| `4f61616cf28740e3b9aef5dca2b93fb4` | `python -m pytest tests/repo_assistant/test_external_execution_completed.py -q` passes within the 197-test command. Later `edd88baa` and `2e364940` object to human-run commands and generic regression steps; follow-up `265c8c21` moves machine checks agent-side and removes unsupported regressions. Current generator tests verify those contracts. | Supported pytest invocation **passes**; direct OS execution of a `.py` file is not equivalent. Historical warning-bearing model-run outcome **UNVERIFIED**; no inference replay. |
| `5e8cb6796a5445ccae12a35a4926880d` | Current `generate 072087a --dry-run`: true pointers / false grounding. Later `7ff0358b` has both steps performed and pass, explicitly accepting no pass/fail in reminders; follow-up `46378d44` preserves that acceptance. Shared reminder/by-view fixture tests pass. | Reminder-control note has a **checked acceptance chain**. Browser refresh/render behavior **UNVERIFIED**. |
| `5f839073782f48b0aeff7a39f373cecb` | Live task exposes distinct area histories; every reference resolves with matching area/commit/verdict. Later `977a3633` is bad-test, not a pass. Its follow-up `7a79ee7d` fixes missing change subjects; UI source contract verifies subjects on every item and explicit all-merges labeling. | Misleading lineage wording **does not reproduce**. Same-area reports may legitimately recur; visual duplicate/readability complaint **UNVERIFIED**. |
| `f2280e3c98204f0692f0d9dbaa3294bb` | Referenced report `e7d27cdc746247d4a287ea352e50aa75` is a docs/tooling-only immutable report: both items pass, empty tested-on and no step results; build time exists. Current report renderer reads step results, tested-on and build time. Current round-trip/build-report fixture tests verify behavioral reports carry them. Latest `8e16e78e` is bad-test with full follow-up `ba83f791` deduping generic steps; it does not retroactively repair missing historical fields. | Historical nonbehavioral record lacks behavioral evidence by construction; no current behavioral-report API failure reproduced. Browser rendering **UNVERIFIED**. |

## Validation and limits

318 tests passed in three bounded commands, using `C:/Users/Jakub/PycharmProjects/ai-workbench/.venv/Scripts/python.exe -m pytest`:

1. `apps/workbench_dashboard/tests/test_dashboard_ui.py apps/workbench_dashboard/tests/test_e2e.py apps/workbench_dashboard/tests/test_e2e_cases.py apps/workbench_dashboard/tests/test_e2e_agent_checks.py apps/workbench_dashboard/tests/test_e2e_promotion.py tests/repo_assistant/test_external_execution_completed.py -q` - **197 passed**.
2. `apps/workbench_dashboard/tests/test_restrictions_view.py apps/workbench_dashboard/tests/test_restrictions_toggles.py apps/workbench_dashboard/tests/test_providers_view.py apps/workbench_dashboard/tests/test_project_filters.py apps/workbench_dashboard/tests/test_inbox_tasks.py apps/workbench_dashboard/tests/test_inbox_bridge.py apps/workbench_dashboard/tests/test_chat_agent.py apps/workbench_dashboard/tests/test_chat_run_request.py -q` - **76 passed**.
3. `tests/test_e2e_promotion.py tests/test_knowme_bank.py tests/test_p7_intake.py apps/workbench_dashboard/tests/test_workflows.py apps/workbench_dashboard/tests/test_p7_intake.py -q` - **45 passed**.

Read-only probes: GET `/api/version`, `/api/status` (ok), `/app.js`, `/api/chat/agent-config`, `/api/e2e/tasks?status=open` (zero open), `/api/e2e/reports`, each ledger task/report/follow-up and each referenced history report. Generator dry runs used `scripts/e2e-promotion.py generate d16ed73 --dry-run` and `generate 072087a --dry-run`. PowerShell redirection produced UTF-16 diagnostic files; decoding corrected locally, no product issue.

No `CURRENT_CONTEXT.md` or private `docs/plans/` files were available in this worktree. The audit ledger and current E2E generator/renderer/store tests are the applicable task context; no architecture change is proposed. Work is on `docs/e2e-behavior-triage-60066ae7`, created from the inspected develop tip.

**Next action:** trace the unresolved run-specific failures from saved receipts to their originating runtime and verify each claimed fix against current code; do not replay consumed inference. Retain browser-only scenarios for a browser-capable session. **Completion condition:** verify each remaining browser-only scenario in an environment with a browser, and establish current outcomes for historical execution failures and scheduler/receipt claims before calling those behaviors resolved. Saved bridge-run receipts have now been read (see below); they preserve failures, cancelled work, proposals and unlanded changes, and cannot by themselves establish current behavior. The appendix's record chains and passing contracts establish only their stated boundaries. Generic ?handled live? resolutions, completed run status, later same-commit reports and exact-locator policies alone do not establish a behavioral fix. No fresh failure task is warranted without current reproduction steps and expected/actual evidence.

## Saved bridge-run evidence

Fetched full run records and re-rendered receipt payloads over HTTP for all 47 directly linked bridge-run ids (49 receipts). The remaining follow-up (`7ea1f1be259b4f1792c9d33213e95985`) has no metadata bridge-run id. Read the receipt bodies, including stdout/stderr tails and agent reports; the list below preserves run ids alongside receipt evidence, never using status as proof of completion. Agent-reported edits and tests below are historical claims, not this investigation's independent validation.

Notable discrepancies: `d2740a80` reports an **E2E** badge fix while its source observation concerned **Inbox** counts; it does not prove that Inbox issue resolved. `526dc2bd` only proposes a badge policy, and `143d6137` could not find its input report; neither establishes a fix. `ccf5f177` actually has a warning-bearing completed receipt with a substantive final report, so it is a concrete saved example for the original external-execution-warning observation; current execution classification is also covered by the passing four-case test module. Replacement one-off cases in several receipts were later declined in follow-up notes: those generated artifacts are not assumed landed. Failed/cancelled runs are not accepted as completed fixes. Historical underlying provider/process failures were not replayed, and causes not established by the available saved evidence remain unknown.

## Full action-bearing ledger review

For every original action-bearing item below, the source notes were read in full. Excerpts are abbreviated for readability. Full resolution text is preserved; it is **historical reported evidence**, not an independently rerun fix. Later reports are listed with every item's per-step completion counts and exact action/expectation alignment to the original item. Exact alignment is diagnostic only: changed steps require separate interpretation. A performed checkbox records execution, not success. Bad-test is never converted to pass.

### Task `03dbaccf4df3441783bc88d5a198ccca` - report `9c3020a2e30d47f980a8f283554fe2d2`

- Original `behavior:dashboard`: **pass**; 2 defined steps, 2 recorded results. Note excerpt: 2 Shows "Working 0s" constantly, which I presume is intended. Also I had to google how to enable reduced-motion in the OS - such things should be included above.
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `115eec0a57e840f39d9d9174a80984fd` - report `5899713af70b4ef79ea3ebe842d8c27e`

- Saved run `ccf5f17748cf437f8f2e57668004c554`: observed state `completed`. Receipt 1 (mai-session): Clarified the dashboard README: `#/?f=open` verifies root-route compatibility. Overview ignores `f`, so identical content is expected. The existing routing test passed; `git diff --check` passed. Only the README changed. No filtering behavior was added.

- Original `behavior:dashboard`: **pass**; 5 defined steps, 5 recorded results. Note excerpt: 2: adress bar contains it, but it doesn't change anything for user
- Direct follow-up `eb57ae17051644a681d6ff7db5866887`: `closed`. Resolution: Observation preserved in report 5899713a: filter query visible in address bar but user-invisible in effect. Minor UX nit, no change — quoted here so it isn't lost.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `125f581784924861ad2afbe332dca3b7` - report `13699bd86fac4bbab97a59155b774a21`

- Saved run `301e04a36d984134b7cadb5c1cf1173d`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: My message in report was rendered well, however the run failed so marking test as fail. Fix underlying issue
- Direct follow-up `d7b576e0f3a54eecb0ca87148398be22`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `8d146a8c73464fdda791590629cc16ad` (2026-11-16T22:52:01.408124+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/2 performed; 2/2 exact original step pairs; note: I think I've already seen this E2E item and responded to it.
- Later report `db8c9424069b4145b3632a453776717f` (2026-11-17T12:01:43.318946+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/2 performed; 0/2 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `1d08593298754d9db34905043034438a` - report `0dc42e191f9643dc8f8ca76731634ef0`

- Saved run `85a203f8bf864b879c57f7b7175c99ed`: observed state `completed`. Receipt 1 (mai-session): Corrected E2E test generation without changing product behavior: - Provenance checks now handle missing filenames/original text and mark absent examples as uncovered. - KnowMe package checks include an exact agent-runnable pytest command. - Authoring instructions assign scoped tests/scripts to the agent. Verified: 90 tests passed; Ruff and diff checks passed. Pyright reported zero errors, with a missing worktree `.venv` notice. The live E2E checklist was not reissued or rerun.

- Original `behavior:dashboard`: **bad-test**; 4 defined steps, 0 recorded results. Note excerpt: 2: all entries just say (CV import) without saying filename or path. 3: entry like that co can't test (all entries claim being imported from CV). 4: "step is not agent runnable" when it clearly is (this made me flag this as bad test design)
- Original `behavior:packages`: **bad-test**; 1 defined steps, 0 recorded results. Note excerpt: "step is not agent runnable" and runnign scripts SHOULD ABSOLUTELY BE AI JOB
- Direct follow-up `02d4694f4ee949d8a39e268093975c36`: `closed`. Resolution: 'Not agent runnable' fixed at the root: suite steps now emit agent-side with exact commands and human templates carry no pytest clause. CV-provenance precision is covered by the renderKnowme:provenance registry step for future cases. Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `1d0a1886b9cd4bc9a9f50c37731ebead` - report `5f9df89eadbd412da05cec2352c3b064`

- Saved run `b068c77d2da34625a5316aae9ca80fe6`: observed state `completed`. Receipt 1 (mai-session): KnowMe now displays separate, bulleted category sections, with Skills and Career path first. Saved line breaks are preserved, and each section shows its entry count. Verified: 89 tests passed; Ruff, targeted type checking, JavaScript syntax, and diff checks passed. Existing notes remain in their saved categories. Career entries remain newest-added first; the live E2E acceptance review still needs confirmation.

- Original `behavior:packages`: **fail**; 1 defined steps, 1 recorded results. Note excerpt: No idea if regrouping worked, for me those know-me entries still don'tr read like na organized lists of skills or career path
- Direct follow-up `0ca531a4910d4361b199cbdd1107ef76`: `closed`. Resolution: Consolidated into 6e19c0f1; notes merged there.
- Checked consolidation target `6e19c0f1959945778d65809ccc36b962`: `closed`. Resolution: Fixed and verified live: splitter now strips source tags/labels and splits short-phrase lists (tests added); backfilled the bank (backup knowme.sqlite3.pre-skillsplit.bak) — 3 skill blobs became 35 atomic skills, each with source_file + origin_text. Dated career facts verified intact. Commit on branch fix/e2e-generator-strengthen.
- Later report `4f149dc2d3b34b639c923aa29973cd2f` (2026-11-17T11:42:58.891389+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/2 performed; 0/2 exact original step pairs; note: 1: Skills are still one item per import, that makes no sense. Import is already listed below as source (although it should mention what file it imported from), data should be clearly organized. ":Docker, AWS, CI/CD (Jenkins, CircleCI), Linux, Git, GitLab, Agile/Scrum; testing: Pytest, integration testing, Clean Code, SOLID." IS OBVIOUSLY NOT ONE SKILL.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `220bb7f5e7104ccf9c5e06309f7f5714` - report `a30c5c29a7b040da9d580c73f81efb1c`

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: 1 is good, 2 resulted in "needs_pointers: false". Copy of whole result: PS C:\Users\Jakub\PycharmProjects\ai-workbench> .venv/Scripts/python.exe scripts/e2e-promotion.py generate d16ed73 --dry-run { "merge_commit": "d16ed73", "title": "E2E promotion for d16ed73", "items": [ { "id": "behavior:dashboard", "kind": "behavior", "area": "dashboard", "behavior": "dashboard views and actions", "files": [ "apps/workbench_dashboard/dashboard_stores.py", "apps/workbench_dashboard/e2e_cases.py", "apps/workb?
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `dbc7afcae6ad46159457ed677e635e14` (2026-11-16T22:20:02.006306+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/2 performed; 0/2 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `22c4c2b1aa964af182e59b5371be7804` - report `64e9ac46897f4bdca4961b2a6c596c03`

- Saved run `beef7f0d69414312b11d71877dfff9d5`: observed state `completed`. Receipt 1 (mai-session): Fixed the E2E checklist templates to remove pytest from orchestrator and agent CLI human checks. Added regression coverage; product behavior is unchanged. Validation: 80 tests passed, Ruff and formatting passed, Pyright reported zero errors, and the final diff passed whitespace checks. Existing submitted reports were not rewritten.

- Original `behavior:orchestrator`: **bad-test**; 3 defined steps, 0 recorded results. Note excerpt: "Run the scoped pytest for the touched module" should not be in human test
- Original `regression:agent-cli`: **bad-test**; 4 defined steps, 0 recorded results. Note excerpt: Same as above, should not be a human test
- Direct follow-up `5e01b817d86c4741a155014f31613ebf`: `closed`. Resolution: 'Run the scoped pytest' removed from the orchestrator human template; the suite runs as a separate agent-runnable step. Regression items already emit agent_runnable in current code. Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `27cedba6a2864dcebc2ae78fa2a180f7` - report `8768bca8e8b54ac3b90620952e08f6a3`

- Original `behavior:dashboard`: **fail**; 4 defined steps, 4 recorded results. Note excerpt: 1. "press Agent" there's no button like that, I've created a new chat. 2. No option like this, so I presume whole "agent" mode is not on the site. As such I didn't even touch step 3 and 4
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `f2eb528a9984401eb7a68095271006bd` (2026-11-16T21:03:55.505810+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/1 performed; 0/1 exact original step pairs; note: Test tells me nothing about what exactly I'm supposed to do.
- Later report `ea285cfbf3c14195a79d5c31d75f4d0b` (2026-11-16T22:59:36.159369+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: No idea what I'm supposed to do.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `2d128378f5cc4279b932f60297fa1953` - report `ebc42f89ceae45f1b8bd87f1c6bef12d`

- Saved run `83f61857b87a4771b2a9910286c6be15`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Fan-out is restricted for every run, and I don't see an option for user to change that restriction
- Direct follow-up `7a98ce384041498a85d8a3e818016bd1`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `3e0b8172940d47219cf5f352bd3a20cc` (2026-11-16T22:50:56.750559+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/2 performed; 2/2 exact original step pairs; note: Fan out seems to be always restricted, no matter what I click in restrictions.
- Later report `cd1332c80b3c4a5d9f70212d176b12d3` (2026-11-17T09:21:59.268587+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/3 performed; 0/3 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `2ebdc5e06f3445b68a0433ccfd38ab0a` - report `1413f957bc0d42f29911442d020f8dcc`

- Saved run `04626a3b1b164f60a08c198c91ea872d`: observed state `failed`. Receipt 1 (mai-session): No final response was captured.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: 1. All have "no usage recorded" and there are providers missing (like Codex/openai which is ou main route after meta tokens are used up). 2: Only shows policy, doesn't alow user to change anything, so it's essentially useless. And it only talks about 200 credits of meta expired allowance (no idea where this came from, I never got 200$ of meta credits, I got 150$. The expiry is understandable we previously though those credits will expire at certain date, but they didn't)
- Direct follow-up `7412b2df6eb441e0aa491bba541430db`: `closed`. Resolution: Verified fixed live 2026-11-19: /api/providers lists OpenRouter, Requesty, Meta, OpenCode (3 windows), Ollama, Codex (2 windows) — Codex present with quota; restrictions editable via toggles + fanout endpoints (round-trip verified); Meta grant reads $150.00 granted / $88.36 balance (owner's figures; the $200 text is gone).
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `367b3f65cd6a4960bc33f8bb3030dd94` - report `dc973a15d0054a088f56535d53fcdfa5`

- Saved run `db3619a62be04b829884f80fc81b14de`: observed state `completed`. Receipt 1 (mai-session): Added eight automated executor cases and a replacement E2E checklist with explicit expected values. Product code is unchanged. Validated: 28 tests passed; Ruff, formatting, Pyright and checklist validation passed. The replacement checklist is saved in `docs/e2e/705363b-steps.json`; it has not been applied to live E2E records. No manual rendering check is needed for this merge because it changes no UI.

- Original `behavior:dashboard`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: Should be tested by automatic test or by AI, I should just test if it renders correctly (expected fields should be explicitly populted)
- Direct follow-up `716144fa2f9a49c387e782548170cbdc`: `closed`. Resolution: Suite work split agent-side; trigger templates carry concrete expected text. Human steps are now render/interaction checks only. Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `3932eb28e0a3441691be345c11e1fc44` - report `39d99bd3d312429d809598fd748fa3ba`

- Saved run `e899580b68a84e169a9ebdaceb6a47e0`: observed state `merged`. Receipt 1 (mai-session): Fixed `#/` to open Home while preserving the configured landing page for URLs without a hash. Added regression coverage and updated documentation. Verified: 74 UI tests passed; Ruff, formatting, Pyright, JavaScript syntax, and diff checks passed. Browser E2E was not rerun. Changes remain uncommitted on `fix/dashboard-root-home`. Receipt 2 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: 1. "#/" doesn't direct user to home, "#/home" does. Rest pass
- Direct follow-up `5d5b9b41059b4ea6ac4d2e2a2c014c33`: `closed`. Resolution: Fixed and merged (ab6f14e Tier 2): #/ now routes home (was Not found). 567 dashboard tests green incl. executed router cases. (Note: the filter-hash #inbox form is fixed separately by the 743c542 follow-up.)
- Later report `ce16951df72147949b8b95752857ae5f` (2026-11-16T21:09:16.714179+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 0/3 exact original step pairs; note: No idea what I'm supposed to test, this points at E2E generator failure.
- Later report `8a73b280e2e4446eb964b23360739d12` (2026-11-16T22:58:09.556127+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/3 performed; 0/3 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `405769cec55a4de49dee21e764bcf3e3` - report `90bd15351cfc416ba5f646cfd096fb1a`

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Opened "E2E promotion for bf18dc2". It has 2 sets of check steps and notes window, but only second one has Pass/fail option. Bundling E2E tests together is fine, but this needs improved readibility. Also there is no "recent verdicts", but there is "previously". Another note: Should every step have a pass/fail? Would be easier for me to fill and then I would just need to describe how they failed in notes
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `014f493f1a6045478212cbe27c57d97c` (2026-11-16T22:23:44.905617+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/2 performed; 0/2 exact original step pairs; note: This test should mention which E2E checklist is considered "multi-item" so that I can find it.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `41a4983c321d415d801b100e12170749` - report `1be8db7128534b8ab41d91dd4d4b7ed8`

- Saved run `526dc2bdca0a4137a515191f979491aa`: observed state `completed`. Receipt 1 (mai-session): Inspection found that badges use global counts, while lists apply filters. E2E also counts drafts in its badge even though its default filter hides them. The report doesn’t identify which badge showed 5. Two viable behaviors: - **Visible count:** matches filtered items, but hides the total attention count. - **Global attention count:** preserves outstanding-work visibility, but can differ from the filtered list; the UI should explain that. I recommend matching the active list’s filters to address the reported expectation. Which tab showed the mismatch, and should its badge follow the active filters? No repository files were edited, and no tests were run.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: Badge says 5 when I see 4 items filtered
- Direct follow-up `472d2af6c1674589a6e72f55856e5338`: `closed`. Resolution: Consolidated into f1203649; notes merged there.
- Checked consolidation target `f12036493b744ad1bbde6844fa644640`: `closed`. Resolution: Verified fixed: badge counts attention_inbox_items and the list endpoint unions attention_ids in, so a badged item can never hide past the cutoff. Observed correct in session (badge 2 == P7 item + upload follow-up; badge 3 with the devstral decision). Covered by badge-count tests.
- Later report `39e5eefd50324546a8f6e6a90f552d0f` (2026-11-17T09:23:05.070735+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 0/3 exact original step pairs; note: 2: Badge claims 3 items, default only sees 1.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `46bec73e59f9434281925ae3185e91ff` - report `cdf983e128e9464b8ab872729ce7e774`

- Saved run `5dd8740a13664bbea820b2f48f5f088d`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: No idea what I'm supposed to do here, but it sounds like something that should be automatic test, not human
- Direct follow-up `35a80f5ef4b040a799d94aef8ab8172e`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `49253937c438463092ca6d20882c57da` (2026-11-17T11:44:49.616868+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: Running test command is not a human-needing task.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `4afdac43111b44cd9c8c880e7430f586` - report `2e364940b21844a0a6a3d5af4d893efe`

- Saved run `80e69dfab55b45b196c4fcebbae57580`: observed state `completed`. Receipt 1 (mai-session): Added replacement test definitions for both rejected cases, with readable CLI evidence checks and specific Runs navigation. Product code was not changed. Validated: 24 tests passed; replacement payload accepted by temporary storage; diff checks passed. Retest remains pending: outcome transcripts and dashboard run links must be attached before issuing the checklist. Original verdicts were preserved.

- Original `behavior:agent-cli`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: Sounds like non-human test
- Original `regression:dashboard`: **bad-test**; 4 defined steps, 0 recorded results. Note excerpt: This part is generic
- Direct follow-up `265c8c210af044119aa70c826c20617e`: `closed`. Resolution: Both bad-tests addressed generator-side, no code re-test applicable: generic regression items now match behavior passes with area-file proof (2ccd4c6, brief 4f52d6b2-B); non-human CLI steps run agent-side with evidence (b11935d, brief 492fc69a-A). Next generated E2E demonstrates it.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `4ec3699689ae4b4886effe85a9425ac0` - report `ce16951df72147949b8b95752857ae5f`

- Saved run `80d948d37b374d74bf749dadccc3e2fd`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: No idea what I'm supposed to test, this points at E2E generator failure
- Direct follow-up `3883251db01f411da5b1fd368880357e`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `8a73b280e2e4446eb964b23360739d12` (2026-11-16T22:58:09.556127+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/3 performed; 1/3 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `4f61616cf28740e3b9aef5dca2b93fb4` - report `893624917b5a47e69f6de92759a28fb4`

- Original `behavior:agent-cli`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: PS C:\Users\Jakub\PycharmProjects\ai-workbench> tests/repo_assistant/test_external_execution_completed.py Traceback (most recent call last): File "C:\Users\Jakub\PycharmProjects\ai-workbench\tests\repo_assistant\test_external_execution_completed.py", line 3, in <module> from ai_agent.repo_coding_assistant import ( ...<2 lines>... ) ModuleNotFoundError: No module named 'ai_agent'
- Original `regression:dashboard`: **fail**; 4 defined steps, 4 recorded results. Note excerpt: No idea what to test and I don;t think there's any affected view? Also this looks very generic so this checklist in itself may be bugged
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `edd88baa464b4287995ec02e64de85de` (2026-11-16T21:02:27.368310+00:00): **fail**.
  - `behavior:agent-cli`: **fail**, 0/2 performed; 0/2 exact original step pairs; note: This should not be a human test, but an AI or straight-up automatic one..
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `regression:dashboard`: **fail**, 0/4 performed; 4/4 exact original step pairs; note: Generic tests, essentially useless.
- Later report `2e364940b21844a0a6a3d5af4d893efe` (2026-11-16T22:57:42.314885+00:00): **fail**.
  - `behavior:agent-cli`: **bad-test**, 0/2 performed; 0/2 exact original step pairs; note: Sounds like non-human test.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `regression:dashboard`: **bad-test**, 0/4 performed; 4/4 exact original step pairs; note: This part is generic.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `55b3a8f1dcd149029f134db6813da9ce` - report `76c6e9b16e1a4a058c68aa6d578ccbbd`

- Saved run `530a9f2d5dbb4efc9e5be5ace72c3972`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 1 defined steps, 1 recorded results. Note excerpt: Test tells me nothing about what I'm supposed to do. We need a way for me to mark "bad test design" and not just "fail" as those should have different follow-ups
- Direct follow-up `8287d09c36d74b66af8ff939da6d2a71`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `977a363363d14b8794e48bbdc1e2ae39` (2026-11-16T22:59:01.840128+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: No idea what changed.
  - `nonbehavioral:docs`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `5698f3cddad3445db331ed757a3c7152` - report `f2eb528a9984401eb7a68095271006bd`

- Saved run `37217e6fc56944b28231da5e89fa0a21`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 1 defined steps, 1 recorded results. Note excerpt: Test tells me nothing about what exactly I'm supposed to do
- Direct follow-up `6e4fbab55f6b4e6baec05c22fcd65406`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `ea285cfbf3c14195a79d5c31d75f4d0b` (2026-11-16T22:59:36.159369+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: No idea what I'm supposed to do.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `5c655451c9b946bca395f81c7c7f7f78` - report `4f149dc2d3b34b639c923aa29973cd2f`

- Saved run `18c35d9e32f345fa9a6c9de0463c008e`: observed state `completed`. Receipt 1 (mai-session): Implemented individual, alphabetized skills with duplicate sources combined. The reported example now renders as 11 skills while preserving parenthesized qualifiers. Verified: 87 UI tests passed; Ruff, formatting, JavaScript syntax, and diff checks passed. Filename provenance remains unavailable because existing records don’t store it; the dashboard now states that explicitly. Full browser E2E was not rerun.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: 1: Skills are still one item per import, that makes no sense. Import is already listed below as source (although it should mention what file it imported from), data should be clearly organized. ":Docker, AWS, CI/CD (Jenkins, CircleCI), Linux, Git, GitLab, Agile/Scrum; testing: Pytest, integration testing, Clean Code, SOLID." IS OBVIOUSLY NOT ONE SKILL
- Direct follow-up `6e19c0f1959945778d65809ccc36b962`: `closed`. Resolution: Fixed and verified live: splitter now strips source tags/labels and splits short-phrase lists (tests added); backfilled the bank (backup knowme.sqlite3.pre-skillsplit.bak) — 3 skill blobs became 35 atomic skills, each with source_file + origin_text. Dated career facts verified intact. Commit on branch fix/e2e-generator-strengthen.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `5e8cb6796a5445ccae12a35a4926880d` - report `c3e244f5a26140658a66b5a3af98517f`

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: 1. Except for step checkboxes it's correct. 2: Reauthor? What? 3: As expected
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `7ff0358be9884e289ff197530245666d` (2026-11-16T22:15:06.161257+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/2 performed; 0/2 exact original step pairs; note: There's no pass/fail in test reminder, but that's acceptable.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `5f839073782f48b0aeff7a39f373cecb` - report `6eac20069a37402d88b1803f75baad08`

- Original `behavior:dashboard`: **fail**; 4 defined steps, 4 recorded results. Note excerpt: 4 fails, all E2E checklists link same, recently-filled fail which isn't relevant to them. Also this window carries two "record: what changed" with same description but different files
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `76c6e9b16e1a4a058c68aa6d578ccbbd` (2026-11-16T21:05:02.908040+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/1 performed; 0/1 exact original step pairs; note: Test tells me nothing about what I'm supposed to do. We need a way for me to mark "bad test design" and not just "fail" as those should have different follow-ups.
  - `nonbehavioral:docs`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Later report `977a363363d14b8794e48bbdc1e2ae39` (2026-11-16T22:59:01.840128+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: No idea what changed.
  - `nonbehavioral:docs`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `65791589ef3b4911977b5d6424c25aa9` - report `e17b4d85e16045e7815c9e3af6e5545a`

- Saved run `1a88efb6ae7c4c6685d8c594ac0ea7f0`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 4 defined steps, 4 recorded results. Note excerpt: 1-2 don't exist or are named differently, also there's no "api" in our adress
- Direct follow-up `5e9242908ef4471eb24c84857e659ca2`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `8e16e78efed146e3a9ee00a5bafda69b` (2026-11-16T23:00:22.684474+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/4 performed; 2/4 exact original step pairs; note: Terrible test design.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `6767e8d8b273458aade530006a891f72` - report `4b2842a8807943058bf1e86d6b372f50`

- Saved run `df7987b523774bbf8c73011ce5746998`: observed state `completed`. Receipt 1 (mai-session): Fixed both E2E test definitions without changing product behavior: - Orchestrator spend checks now use exact automated suites. - CLI regression checks now specify concrete scenarios and expected outcomes. Validation: 109 tests passed; Ruff, formatting, targeted Pyright, and diff checks passed. Pyright noted the missing worktree `.venv`. Historical report preserved; revised checks apply when regenerated.

- Original `behavior:orchestrator`: **bad-test**; 6 defined steps, 0 recorded results. Note excerpt: Doesn't look like a human test at all, should be automated
- Original `regression:agent-cli`: **bad-test**; 4 defined steps, 0 recorded results. Note excerpt: Generic, so useless to me
- Direct follow-up `eddf3391de1d4e0cbef91abcd3c32d82`: `closed`. Resolution: Orchestrator template split (suite agent-side, trigger human-side). Generic regression standing checks are already banned in current code (REGRESSION_COMMANDS no-entry means no item). Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `6af39d3cc384499eb11290287d0bfdd4` - report `8d146a8c73464fdda791590629cc16ad`

- Saved run `143d6137b37843f4b69a42286dd648c3`: observed state `completed`. Receipt 1 (mai-session): Merge `37a65c3` fixes subprocess UTF-8 capture and includes an automated regression test. The supplied feedback concerns a repeated dashboard checklist, but I couldn’t locate report `8d146a8c73464fdda791590629cc16ad` or its original steps in the inspected repository files. No repository edits were made, and no tests were run. The next step is to inspect that report and its linked task in the dashboard’s configured `e2e_reports` and `e2e_tasks` stores, then compare earlier responses before correcting the checklist. Product changes aren’t justified by the available evidence.

- Original `behavior:dashboard`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: I think I've already seen this E2E item and responded to it
- Direct follow-up `b7392c934d9a4a3f9d70d2b6d3bb97e7`: `closed`. Resolution: Stale follow-up: the bad-test complaint on report 8d146a8c was already acted upon — task 125f5817 was re-authored by agent on 2026-11-16 with fresh report 13699bd8, and the behavior item is pending owner testing there. No separate fix needed; owner's 'already seen it' confirmed.
- Later report `db8c9424069b4145b3632a453776717f` (2026-11-17T12:01:43.318946+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/2 performed; 0/2 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `7ccae6fbf2064a6384b87b6e7aaabd6c` - report `3b5e11deeed54e8283f0e0093c6897ff`

- Saved run `3246a0630ddf43e58235884704137487`: observed state `completed`. Receipt 1 (mai-session): Fixed workflow node-type changes blocking further additions. Fleet probes now run concurrently. Clarified Intake’s file-based flow and Projects’ goal sources. Validation: 169 tests passed; Ruff, formatting, JavaScript syntax, and targeted Pyright checks passed. Fleet can still wait for the slowest probe; live browser latency was not measured. Item 19 remains with its scheduled fix. Full E2E acceptance remains unverified.

- Original `behavior:dashboard`: **fail**; 41 defined steps, 41 recorded results. Note excerpt: 5: Fleet view takes a while to load, I presume because it has to check something? Overview has the same issue, probably because it renders fleet information. 7: "Client intake Review website briefs, then approve valid ones into draft plans. Nothing executes or spends. No intake files. Drop chatbot briefs into p7-projects/ (gitignored, stays on this PC)." is only information on this tab. 14: Only Know-me has something I'd consider real project item, rest look hard-coded? 19: Already scheduled a f?
- Direct follow-up `0e74066aed9746938d107bf4f562be4c`: `closed`. Resolution: Consolidated into 7412b2df; notes merged there.
- Checked consolidation target `7412b2df6eb441e0aa491bba541430db`: `closed`. Resolution: Verified fixed live 2026-11-19: /api/providers lists OpenRouter, Requesty, Meta, OpenCode (3 windows), Ollama, Codex (2 windows) — Codex present with quota; restrictions editable via toggles + fanout endpoints (round-trip verified); Meta grant reads $150.00 granted / $88.36 balance (owner's figures; the $200 text is gone).
- Later report `402dd90015fc4f96b6b5cc59469d2263` (2026-11-17T09:27:23.536689+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 0/3 exact original step pairs; note: 1. redirect is correct, but no prividers are there in the fleet - they live in Providers tab, and that's where spend should be moved (I incorrectly told agent to move it to Fleet before). 2: Still stuck if I change it to agnet_run or skill. 3: Nothing changed here from before.
- Later report `d2adeaa2e9bc447dad8e2eb90d836422` (2026-11-17T11:47:26.964657+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 0/3 exact original step pairs; note: 1. Routes correctly, but every provider should have their respective allowances and spend listed, instead it's just one hard-coded meta spend at the top. 3 Technically works, but I've wanted those goals to become real projects.
- Later report `1413f957bc0d42f29911442d020f8dcc` (2026-11-17T13:57:18.259770+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/2 performed; 0/2 exact original step pairs; note: 1. All have "no usage recorded" and there are providers missing (like Codex/openai which is ou main route after meta tokens are used up). 2: Only shows policy, doesn't alow user to change anything, so it's essentially useless. And it only talks about 200 credits of meta expired allowance (no idea where this came from, I never got 200$ of meta credits, I got 150$. The expiry is understandable we previously though those credits will expire at certain date, but they didn't).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `86bb28b8d52645e8950da5944097187d` - report `edd88baa464b4287995ec02e64de85de`

- Saved run `c4715c8f851542779e37873faa517d09`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:agent-cli`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: This should not be a human test, but an AI or straight-up automatic one.
- Original `regression:dashboard`: **fail**; 4 defined steps, 4 recorded results. Note excerpt: Generic tests, essentially useless
- Direct follow-up `081a21d5ab294029a045f27e3bfc379f`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `2e364940b21844a0a6a3d5af4d893efe` (2026-11-16T22:57:42.314885+00:00): **fail**.
  - `behavior:agent-cli`: **bad-test**, 0/2 performed; 2/2 exact original step pairs; note: Sounds like non-human test.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `regression:dashboard`: **bad-test**, 0/4 performed; 4/4 exact original step pairs; note: This part is generic.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `8dc8d179421942b292c6d50a2cef4485` - report `dbd849fea0fe45eab44fce75c4013f7c`

- Saved run `7c5d457fe809490abd34522e9edd3b9a`: observed state `failed`. Receipt 1 (mai-session): No final response was captured.

- Original `behavior:agent-cli`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Steps above need guide how to do each (so that I know which beahviour, from which tab, doing what is expected and can compare it to real beahaviour)
- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Same as the other item above. If you're not seeing any other "note window" then that by itself is a bug and a case against multi window E2E tests
- Direct follow-up `e17035fad4044c839e7b9cc5db5170d9`: `closed`. Resolution: Triaged (run 7c5d457f failed Mai exit 1, no fixes): keepalive-Restart step text superseded (ritual fix; template no longer emits it); vague agent-cli steps superseded by grounding-tightening (current generation flags needs_pointers); multi-item note confusion was pre-per-step-verdict UX (da1cab4). Re-issued as task cd4ab743 (draft).
- Later report `b4c55e18f8e34f35aea376764a190fc7` (2026-11-17T11:44:30.132187+00:00): **fail**.
  - `behavior:agent-cli`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: Running test command is not a human-needing task.
  - `behavior:dashboard`: **bad-test**, 0/1 performed; 0/1 exact original step pairs; note: Running test command is not a human-needing task.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `91973d3649d54d028c6a47dc81c2001d` - report `402dd90015fc4f96b6b5cc59469d2263`

- Saved run `e7f15205ff7b4020aa0c6e395e25902d`: observed state `failed`. Receipt 1 (mai-session): No final response was captured.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: 1. redirect is correct, but no prividers are there in the fleet - they live in Providers tab, and that's where spend should be moved (I incorrectly told agent to move it to Fleet before). 2: Still stuck if I change it to agnet_run or skill. 3: Nothing changed here from before
- Direct follow-up `497f388032ed40a9bb5897f53c43ad4d`: `closed`. Resolution: Consolidated into 7412b2df; notes merged there.
- Checked consolidation target `7412b2df6eb441e0aa491bba541430db`: `closed`. Resolution: Verified fixed live 2026-11-19: /api/providers lists OpenRouter, Requesty, Meta, OpenCode (3 windows), Ollama, Codex (2 windows) — Codex present with quota; restrictions editable via toggles + fanout endpoints (round-trip verified); Meta grant reads $150.00 granted / $88.36 balance (owner's figures; the $200 text is gone).
- Later report `d2adeaa2e9bc447dad8e2eb90d836422` (2026-11-17T11:47:26.964657+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 1/3 exact original step pairs; note: 1. Routes correctly, but every provider should have their respective allowances and spend listed, instead it's just one hard-coded meta spend at the top. 3 Technically works, but I've wanted those goals to become real projects.
- Later report `1413f957bc0d42f29911442d020f8dcc` (2026-11-17T13:57:18.259770+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/2 performed; 0/2 exact original step pairs; note: 1. All have "no usage recorded" and there are providers missing (like Codex/openai which is ou main route after meta tokens are used up). 2: Only shows policy, doesn't alow user to change anything, so it's essentially useless. And it only talks about 200 credits of meta expired allowance (no idea where this came from, I never got 200$ of meta credits, I got 150$. The expiry is understandable we previously though those credits will expire at certain date, but they didn't).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `93a0ec1619584f978822465a751b9e38` - report `e3811118e29543ef90e714294a4ee1ca`

- Saved run `4a5c3dd7c7b640d299fe642c8870a086`: observed state `completed`. Receipt 1 (mai-session): Your logic is sound for step 2: checking generated command text belongs in automated testing. The exact-command assertion already exists in `test_e2e_cases.py`; all 20 tests passed. Step 1’s visual-grouping check still benefits from human review. The remaining decision is when automation runs: - **During normal test gates:** simpler, with existing coverage; no fresh result tied to E2E resolution. - **Pinned to E2E resolution:** fresh, linked evidence; requires a product workflow change beyond correcting this test. I recommend normal test gates and retaining only the visual check for human review. Do you want that approach, or specifically a pinned check triggered on resolution? I made no repository edits and left the submitted report unchanged. The follow-up remains pending that decision.

- Original `behavior:dashboard`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: 2: I doubt this should be a human task, it should be a pre-planned auto-test pinned on when I resolve this E2E test (I think, confirm if this logic is sound)
- Direct follow-up `320c1e03ba704e48b91d23fc1e17c03e`: `closed`. Resolution: Scheduler-gating logic confirmed sound via brief 24b004b6 (answer A) and implemented (auto-run at submit). The prompting e2e-promotion.py step is outside the current allowlist; extension needs a separate owner decision.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `960880f397194010a593cc49e547bdaf` - report `221dc6d5858541fe8081d174ca139406`

- Saved run `733b664ef5844dff91bf9197d5e98884`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Again, shouldn't be confirmed by human, but by automatic test written for it
- Direct follow-up `9cd4e495e37046a4b391bdaabb77cd98`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `d333fc0907c649dfa8d9272b1a411e5d` (2026-11-17T11:44:39.455921+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/2 performed; 0/2 exact original step pairs; note: Running test command is not a human-needing task.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `9e8d249ff7f549b280936945b2388e2f` - report `16f0927d05d3486bbb0d81920ae7ec32`

- Saved run `cb2b856b71f4498d8be50196407c8a4a`: observed state `completed`. Receipt 1 (mai-session): Fixed receipt display and full reports to show Mai output, errors, route, and session details. Saved runs also receive refreshed reports. Independently verified the disposable file contains deletion instructions and prints `hello world`. Saved evidence confirms execution passed startup without an instruction-budget refusal. The owner’s E2E verdict remains unchanged. Validation: 113 tests passed; Ruff and targeted Pyright passed. Browser E2E remains unverified. Naming needs your choice: it currently truncates the first 60 characters. - **Deterministic excerpt:** predictable and no extra inference, but may retain conversational filler. - **Model-generated title:** potentially clearer, but adds inference and variable results. I recommend a word-aware excerpt with an ellipsis first. Shall I implement that, or do you prefer model-generated titles?

- Original `behavior:dashboard`: **fail**; 1 defined steps, 1 recorded results. Note excerpt: I ran a task "We need to confirm Mai works properly, so so generate a smal" (name generation from chat runs in itself should be strengthened, investigate and if needed brief me for a decision), it completed, but receipt is not readable for humans, so you check if it matched expected behaviour, however this receipt issue and report not having useful information is another issue to fix
- Direct follow-up `ca3894b2d1c74e37abb8060602b097fe`: `closed`. Resolution: Both halves addressed: (1) run reports render as readable HTML in the run detail view (mdHtml, e76d420) and failure reasons surface in receipts; (2) chat run titles now cut at word boundaries with ellipsis (fix/e2e-generator-strengthen) — the mid-word 'smal' cut is covered by a regression test.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `a03ac81c816c4df9b6a1bbc8fcdb1402` - report `49253937c438463092ca6d20882c57da`

- Original `behavior:dashboard`: **bad-test**; 1 defined steps, 0 recorded results. Note excerpt: Running test command is not a human-needing task
- Direct follow-up `7ea1f1be259b4f1792c9d33213e95985`: `closed`. Resolution: Remedy shipped: machine auto-submit for all-agent checklists (brief ff9b255d-A, merged). No run needed.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `a1019cb8d7b44fddb25dde94b0a88694` - report `2174c4884f9844cbbe15034fd8f664c5`

- Saved run `3606848e44d949aa9a0832901a080ad2`: observed state `failed`. Receipt 1 (mai-session): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **bad-test**; 3 defined steps, 0 recorded results. Note excerpt: 2: I open home by clicking on "Overwiew" button, that by design opens default home without filter query. I think step 2 is badly designed
- Direct follow-up `133d9115ea004270aec0326dc9b782fa`: `closed`. Resolution: Bad-test resolved: corrected 'E2E re-test ab6f14e' issued and PASSED by owner (report 5899713a). Step 2 was badly designed (Overview opens default home by design). Step-splitting now ships generator-side (b11935d).
- Later report `5899713af70b4ef79ea3ebe842d8c27e` (2026-11-16T23:53:10.879715+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/5 performed; 0/5 exact original step pairs; note: 2: adress bar contains it, but it doesn't change anything for user.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `a4225f46a7004996afa2a47fef33253d` - report `0a26ef23b7e544d680c60c7999f25b9a`

- Saved run `dfd5e3cae17f4b6a8b3c744e57f5aec0`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: 2 fails as this should be tested by you, it should not be elevated to human behaviour, rather it should be run waiting for this test to finish (important feature of scheduler, if it;s missing then implement and wire it in)
- Direct follow-up `21f56e74ceb14dceaec5a4d6904b92b8`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `e3811118e29543ef90e714294a4ee1ca` (2026-11-16T22:54:47.277617+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/2 performed; 1/2 exact original step pairs; note: 2: I doubt this should be a human task, it should be a pre-planned auto-test pinned on when I resolve this E2E test (I think, confirm if this logic is sound).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `ac8946bd0389430f9337668d3d10cf32` - report `39e5eefd50324546a8f6e6a90f552d0f`

- Saved run `d2740a8079d2466cae15bf94f80c01b0`: observed state `completed`. Receipt 1 (mai-session): Fixed the E2E badge to match the default view: open checklists plus failed reports, excluding drafts. Removed the ten-report display cap. Verified: 165 tests passed; Ruff, formatting, type checks and diff checks passed. Changes remain uncommitted on `fix/e2e-badge-default-count`. Human browser E2E retesting remains outstanding.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: 2: Badge claims 3 items, default only sees 1
- Direct follow-up `f12036493b744ad1bbde6844fa644640`: `closed`. Resolution: Verified fixed: badge counts attention_inbox_items and the list endpoint unions attention_ids in, so a badged item can never hide past the cutoff. Observed correct in session (badge 2 == P7 item + upload follow-up; badge 3 with the devstral decision). Covered by badge-count tests.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `ae594db5d2b142e6a3aaef37d6f160c5` - report `ea285cfbf3c14195a79d5c31d75f4d0b`

- Saved run `3829105f21f34be2b635f718df767d30`: observed state `completed`. Receipt 1 (mai-session): Authored a replacement dashboard E2E case with explicit setup, clicks, inputs, and expected results. Added a test verifying checklist finalization leaves it pending without creating a verdict. Validated: 37 tests passed; Ruff, formatting, scoped Pyright, and diff checks passed. Product code and the live report were not edited by my tools. Loading the replacement checklist and performing the browser re-test remain outstanding.

- Original `behavior:dashboard`: **bad-test**; 1 defined steps, 0 recorded results. Note excerpt: No idea what I'm supposed to do
- Direct follow-up `b762fc6cee9b4015946011d10fbef764`: `closed`. Resolution: Vague case: subjects-on-every-item fix plus the exact-locator rule address both halves ('what' context + findable targets). Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `b285a745555641bcb48a8b2258232827` - report `d2adeaa2e9bc447dad8e2eb90d836422`

- Saved run `52a6aebb4f85454ca03e3f6c35b8634f`: observed state `failed`. Receipt 1 (mai-session): No final response was captured.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: 1. Routes correctly, but every provider should have their respective allowances and spend listed, instead it's just one hard-coded meta spend at the top. 3 Technically works, but I've wanted those goals to become real projects
- Direct follow-up `f91803de8f0a4fb8bd48a4b8315f8b9e`: `closed`. Resolution: Consolidated into 7412b2df; notes merged there.
- Checked consolidation target `7412b2df6eb441e0aa491bba541430db`: `closed`. Resolution: Verified fixed live 2026-11-19: /api/providers lists OpenRouter, Requesty, Meta, OpenCode (3 windows), Ollama, Codex (2 windows) — Codex present with quota; restrictions editable via toggles + fanout endpoints (round-trip verified); Meta grant reads $150.00 granted / $88.36 balance (owner's figures; the $200 text is gone).
- Later report `1413f957bc0d42f29911442d020f8dcc` (2026-11-17T13:57:18.259770+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/2 performed; 0/2 exact original step pairs; note: 1. All have "no usage recorded" and there are providers missing (like Codex/openai which is ou main route after meta tokens are used up). 2: Only shows policy, doesn't alow user to change anything, so it's essentially useless. And it only talks about 200 credits of meta expired allowance (no idea where this came from, I never got 200$ of meta credits, I got 150$. The expiry is understandable we previously though those credits will expire at certain date, but they didn't).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `bfdd19f7a50a406c8f0a3dc1da9ef9df` - report `7ff0358be9884e289ff197530245666d`

- Saved run `f3e743d106654cc49f7fd3618980c401`: observed state `completed`. Receipt 1 (mai-session): No code change is needed: the passed E2E note explicitly accepts pass/fail controls being available through the full checklist. Source inspection confirmed that flow. The focused reminder API test could not run because the Python environment lacks `httpx`. I made no repository edits; final Git status was clean.

- Original `behavior:dashboard`: **pass**; 2 defined steps, 2 recorded results. Note excerpt: There's no pass/fail in test reminder, but that's acceptable
- Direct follow-up `46378d44598f41db89236d58b4438b4a`: `closed`. Resolution: Owner-marked acceptable ('no pass/fail in test reminder, but that's acceptable'). No action.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `c23ffbcdac7e4994a8a1d3f35e4e7e98` - report `d333fc0907c649dfa8d9272b1a411e5d`

- Saved run `64651408856c4e118576d20c05298250`: observed state `completed`. Receipt 1 (mai-session): Prepared replacement E2E steps containing browser checks only; pytest remains agent validation. Product code was unchanged by my edits. Validated: 39 supervisor tests passed; replacement steps passed schema validation; staged diff checks passed. The original report is preserved. A fresh runtime checklist has not been filed, and the owner’s browser verdict remains pending.

- Original `behavior:dashboard`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: Running test command is not a human-needing task
- Direct follow-up `dc45700e6a0742dfb35e45696852a6b7`: `closed`. Resolution: Remedy shipped: machine auto-submit for all-agent checklists (brief ff9b255d-A, merged).
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `c730e39e6afc4a91aa660bd6dbbd792f` - report `f3a2fbaad2fb4d13b969165de6829290`

- Saved run `2cb81505c3e14b0390888868a725a885`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: 2: "the filter query is preserved." where should I see it?
- Direct follow-up `d8d0f6738cf841e6a5b2d3fa3e30ad79`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `2174c4884f9844cbbe15034fd8f664c5` (2026-11-16T22:56:47.657941+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/3 performed; 2/3 exact original step pairs; note: 2: I open home by clicking on "Overwiew" button, that by design opens default home without filter query. I think step 2 is badly designed.
- Later report `5899713af70b4ef79ea3ebe842d8c27e` (2026-11-16T23:53:10.879715+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/5 performed; 0/5 exact original step pairs; note: 2: adress bar contains it, but it doesn't change anything for user.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `cd2916de9f4c447ba49b1deec4384fb4` - report `977a363363d14b8794e48bbdc1e2ae39`

- Saved run `062b9026e3b04487bba55dcd7da6e3b2`: observed state `completed`. Receipt 1 (mai-session): Added a concrete replacement manual test, disposable dashboard fixture, and API lifecycle test. Product code is unchanged. Validated: 34 tests passed; Ruff and scoped Pyright passed. Browser acceptance remains pending. Commit was blocked because hooks expect a worktree-local `.venv/Scripts/ruff.exe`; the three files remain staged.

- Original `behavior:dashboard`: **bad-test**; 1 defined steps, 0 recorded results. Note excerpt: No idea what changed
- Direct follow-up `7a79ee7d3962407292fd6935ac12f0cc`: `closed`. Resolution: Root cause found and fixed: change subjects rendered only on the FIRST checklist item (whatHtml index===0). Subjects now render on every item. Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `cd4ab743c1df42fe8e5ef176fe0c7913` - report `b4c55e18f8e34f35aea376764a190fc7`

- Saved run `d2571274d1fc460e88d37eefdbf874b7`: observed state `completed`. Receipt 1 (mai-session): Added replacement E2E cases assigning both pytest commands to the agent, with regression coverage verifying they are agent-runnable. Product code was unchanged. Validated: 35 tests passed; Ruff, formatting, Pyright and diff checks passed. The live dashboard checklist still needs reauthoring from the saved replacement cases; the original report was not modified.

- Original `behavior:agent-cli`: **bad-test**; 1 defined steps, 0 recorded results. Note excerpt: Running test command is not a human-needing task
- Original `behavior:dashboard`: **bad-test**; 1 defined steps, 0 recorded results. Note excerpt: Running test command is not a human-needing task
- Direct follow-up `4d6dbd4ffdaf481084a34e8b2ebc7ab6`: `closed`. Resolution: Remedy shipped: machine auto-submit for all-agent checklists (brief ff9b255d-A, merged, pushes with next push). No per-item work remains.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `d66a7961b5d743d4ab4f0e01db2e2f6f` - report `0e68c25d1ac44d17bd24333befa3837f`

- Saved run `371eb2992def4156b995f882992427d2`: observed state `failed`. Receipt 1 (mai-session): No final response was captured.

- Original `behavior:dashboard`: **pass**; 2 defined steps, 2 recorded results. Note excerpt: Is this form good for you? Current way knowMe presents information is not very readable to human, but if it's good for you then it's okay. However I think it would be better to gather information together with a tag (here are all your career skills, here is you past employment etc), rather than separating them by import (this can definitely be a phase when getting to knothe user, however it doesn't sound sustainable long term). You can investigate better ways on the internet
- Original `behavior:packages`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: 1. What interview? There is no button or window like that. 2. This should be a task for you, not me (you can pre-plan automatic follow-ups for E2E tests and make them visible at the bottom of the respective test if that will help with organizing this).
- Direct follow-up `10948e382a6e4e17aecdf08508c08984`: `closed`. Resolution: Triaged (run 371eb299 failed Mai exit 1, no fixes; verdicts by direct investigation): KnowMe regroup request filed as b9459ccb (investigate-only); interview step template superseded — current generator flags needs_pointers instead (verified); auto-followup process request answered by forgotten-sweep auto-filing (79d0e89). Re-issued as task 1d0a1886 (draft, pointers 3b11e1bc).
- Later report `5f9df89eadbd412da05cec2352c3b064` (2026-11-16T22:28:44.530345+00:00): **fail**.
  - `behavior:dashboard`: **pass**, 0/1 performed; 0/1 exact original step pairs; note: (none).
  - `behavior:packages`: **fail**, 0/1 performed; 0/1 exact original step pairs; note: No idea if regrouping worked, for me those know-me entries still don'tr read like na organized lists of skills or career path.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Later report `4f149dc2d3b34b639c923aa29973cd2f` (2026-11-17T11:42:58.891389+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/2 performed; 0/2 exact original step pairs; note: 1: Skills are still one item per import, that makes no sense. Import is already listed below as source (although it should mention what file it imported from), data should be clearly organized. ":Docker, AWS, CI/CD (Jenkins, CircleCI), Linux, Git, GitLab, Agile/Scrum; testing: Pytest, integration testing, Clean Code, SOLID." IS OBVIOUSLY NOT ONE SKILL.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `dae099b0f39a4400bde8fafd12860ce8` - report `773bdc4d5cd7422ea0b85d8d08599c05`

- Saved run `abd4e486e201459b8b55793124607adc`: observed state `completed`. Receipt 1 (mai-session): Implemented drain visibility on the Runs page: scheduler state, interval, finished ticks, errors, and timing explanation. Validated: 96 tests passed; Ruff, JavaScript syntax, type checking, and diff checks passed. Queue execution policy is unchanged. The live backlog’s cause and browser E2E remain unverified.

- Original `behavior:dashboard`: **pass**; 1 defined steps, 1 recorded results. Note excerpt: No idea when drain ticks happen but there's A LOT of queued runs. However except for that behaviour is as expected above
- Direct follow-up `a707862a17f449e8bae961161647efc6`: `closed`. Resolution: Regulated by ADR-089 (e17d73d): full agent-queue pre-approval + drain auto-pause on allowance/config failure with owner alert. Backlog drains on ticks; empty-completion guard queued separately.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `df3d04a8cbf240aca5bf08cbf0ed3f63` - report `68841f56569b43e6a998507601484c89`

- Saved run `422dad5308af4ecaba347a263e131b62`: observed state `completed`. Receipt 1 (mai-session): Both notes are already addressed by `da1cab4` in this worktree: - Filter groups display on separate lines. - Each checklist step has Pass/Fail controls; any failed step fails its behavior. Verified: 102 dashboard/E2E tests passed using the repository virtual environment. System Python lacked `httpx`. No repository file edits were needed; final Git diff/status were clean. Browser appearance was not independently checked.

- Original `behavior:dashboard`: **pass**; 4 defined steps, 4 recorded results. Note excerpt: 1. As expected, but it's all single line, so it;s hard to distinguish what is connected to what. 2-4. Pass (we really need that PASS/FAILURE to be per-step)
- Direct follow-up `1615aaffa67249edbe9b0d3ea58cb13c`: `closed`. Resolution: Verified by run 422dad53 (no changes needed, correct): single-line filter groups now on separate lines + per-step pass/fail both shipped in da1cab4; reminder-entry separators added in 7b15c26. Report passed; no re-issue needed.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `e326255193de490fbd803d226390afba` - report `3e0b8172940d47219cf5f352bd3a20cc`

- Saved run `8b6c60a8e9f947078a1d8e43a467acce`: observed state `failed`. Receipt 1 (mai-session): No final response was captured.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Fan out seems to be always restricted, no matter what I click in restrictions
- Direct follow-up `08460f8473fa4288a6a183a87fd55453`: `closed`. Resolution: Verified fixed live: /api/restrictions/fanout round-trips (set chat=restricted, read back restricted, restored allowed). Fan-out is no longer stuck; toggles carry descriptions. No code change needed.
- Later report `cd1332c80b3c4a5d9f70212d176b12d3` (2026-11-17T09:21:59.268587+00:00): **pass**.
  - `behavior:dashboard`: **pass**, 0/3 performed; 0/3 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `e464aa9b2d174278b611ece2ed5509de` - report `0f3e448041f94d94b3fee506fc13971d`

- Saved run `b24d7f076887494c9d938a9e21158276`: observed state `completed`. Receipt 1 (mai-session): Fixed the test design without changing the intake product. - Intake schema changes now generate an agent-run pytest check instead of a human browser test. - Added mixed-change generator coverage and CLI exit-code/output tests; documented the testing approach. - Verified 169 passing tests, Ruff, formatting, and scoped Pyright checks. Pyright noted the worktree lacks its own `.venv`. - Replayed generation against `45c38f0` successfully. The original E2E report was not rewritten; repository changes remain uncommitted.

- Original `behavior:company-site`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: Not a human test. Strengthen E2E generator to account for such stuff, also strengthen our automatic test approach as I feel we don't cover everything with our curent test suite
- Direct follow-up `0a90eee3d53f493692ab5a3a48ef4b32`: `closed`. Resolution: Bad-test verdict correct: schema validation is machine-checkable and already covered by tests/test_p7_intake.py (5 green, verified live). No human re-test needed — automation IS the check. Lesson recorded: finalize rule = for machine-checkable diffs, find covering automated tests first; author human steps only for what automation cannot check. Generator proposal (needs owner call): route ungroundable machine-checkable items to agent coverage tasks instead of owner checklists.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `e89198d9e1da4a76900da1c215afe6d7` - report `562cb736fe974337b2f385f5950ace5b`

- Saved run `cecbe936846049df9dd928e54f68c74d`: observed state `cancelled`. Receipt 1 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 2 defined steps, 2 recorded results. Note excerpt: Receipt keeps closing every few seconds so I can't read it. And generally report is not really useful to human, check if it's at least useful for AI
- Direct follow-up `65271a4063fc44ceb502620071db680e`: `closed`. Resolution: Handled live in the driving session (triage + fixes + re-issue); run stood down to avoid duplication. See session history 2026-11-16.
- Later report `dc973a15d0054a088f56535d53fcdfa5` (2026-11-16T22:53:09.177963+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/2 performed; 2/2 exact original step pairs; note: Should be tested by automatic test or by AI, I should just test if it renders correctly (expected fields should be explicitly populted).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `ec0fa2fd7b014c9fbd56911d60a82138` - report `014f493f1a6045478212cbe27c57d97c`

- Saved run `86ad7b802dab4d5285da158a6e85d485`: observed state `failed`. Receipt 1 (mai-session): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **bad-test**; 2 defined steps, 0 recorded results. Note excerpt: This test should mention which E2E checklist is considered "multi-item" so that I can find it
- Direct follow-up `aadea3114b40498c8a35d9f6af3950b9`: `closed`. Resolution: Unfindable 'multi-item checklist' reference: pointer mission now requires exact locators (ids/paths/hashes) and rejects unfindable references as defects. Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `ed026812944f49f39eb7af7d9514de1c` - report `f91ec0452c99485eac0352213804c326`

- Saved run `542e6cc93d90450cbd83972bc328d761`: observed state `completed`. Receipt 1 (mai-session): Fixed the test design with reproducible success, decline, invalid-output, failed, and cancelled cases, including duplicate-routing checks. Added readable retest instructions. Validation: 38 tests passed; final five-case rerun, Ruff, formatting, and targeted Pyright passed. Only tests and documentation changed. Browser rendering and real-agent instruction compliance remain unverified; the original bad-test verdict was preserved.

- Original `behavior:dashboard`: **bad-test**; 5 defined steps, 0 recorded results. Note excerpt: 1. Not sure if AI properly adhered to STEPS nad DECLINE parts as report is not readable to human, but it meets test criteria I think. 2. Also not sure those steps are valid for the same reason as 1. 4 and 5 I can't execute since I cannot find an applicable run like that. Quite possible that it means issue is gone, but needs investigation
- Direct follow-up `a7e5f7ca940542a089dcd498c55eb129`: `closed`. Resolution: Investigated: the agent-pointers feature works (pointer run 9293f276 completed; 3 completions total). The case's fixture ids aged out, which caused the confusion. Future cases are bound by the new exact-locator rule (no 'applicable X' references). Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `ee9ddd9d0a9544d991db5bf7cc00df35` - report `7c21902b5d4c448ab7a8cbf1ea98ecc7`

- Saved run `222ebc4ca1b248fe80d0188ceb3b9366`: observed state `merged`. Receipt 1 (mai-session): Fixed checkbox navigation across all eight lists and preserved empty selections. Fixed the Inbox badge’s conflicting counts: it now consistently counts human-assigned open or follow-up tasks, excluding agent tasks. Validated: 93 tests passed, Ruff and formatting passed, JavaScript syntax passed, and targeted Pyright reported zero errors. Browser E2E was not rerun. Document filtering still needs your choice: - **Explicit importance marking:** precise and owner-controlled, but requires maintaining metadata. - **Recency-based filtering:** automatic, but recently edited documents may not be important. I recommend explicit marking and a searchable project selector, which scales better than project checkboxes. Runs and Inbox already have project dropdowns. Should document importance be explicitly marked or inferred from recency, and should project filtering extend to Documents only or other lists too? Receipt 2 (source unspecified): No substantive final agent report in stdout_tail; no fix established by this receipt.

- Original `behavior:dashboard`: **fail**; 4 defined steps, 4 recorded results. Note excerpt: 1. Unticking a box redirects to "http://127.0.0.1:8766/#inbox?f=open,followup" which just has "not found" - fresh bug, before I hard-refreshed site there was a bug where unticking all boxes reverted to default filtering. 2 New bug present on all (redirect to http://127.0.0.1:8766/#ideas?f=new,reviewing,implemented when clicking respective box in ideas as example), documents needs different filtering, one where we can see currently important documents. Also what about filtering by project (would ?
- Direct follow-up `b6e1453755a04cc598f83c49069c969f`: `closed`. Resolution: Fixed and merged (96c1a08 Tier 2): filter changes keep valid #/ routes, empty selection stays empty across reloads, inbox badge counts human open/follow-up via status endpoint. 568 dashboard tests green incl. executed filter/badge cases. Remaining (needs design input, filed separately): documents important-view filter + project filter UI for many projects.
- Later report `1be8db7128534b8ab41d91dd4d4b7ed8` (2026-11-16T22:26:10.485390+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 0/3 exact original step pairs; note: Badge says 5 when I see 4 items filtered.
- Later report `39e5eefd50324546a8f6e6a90f552d0f` (2026-11-17T09:23:05.070735+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/3 performed; 0/3 exact original step pairs; note: 2: Badge claims 3 items, default only sees 1.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `ef1f530211744d1dba0856cad04d957e` - report `0051d4564a064e73bb11ec85cd6d3eaa`

- Saved run `6c7a63679c094a28a8a358d61b2dafa2`: observed state `completed`. Receipt 1 (mai-session): Implemented: “All checklists” now restores the selected filters after opening a checklist or report, including after reload. Added regression coverage and documentation. Verified: 82 UI tests passed; Ruff, formatting, JavaScript syntax, targeted Pyright, and diff checks passed. Pyright noted the worktree’s missing `.venv` directory. Browser E2E was not run.

- Original `behavior:dashboard`: **pass**; 2 defined steps, 2 recorded results. Note excerpt: Reloa keeps selection, but entering checklist and then clicking "all checklists" does not. Would be great if we either have alternate button for returning to set-up filtering or just make it default
- Direct follow-up `182a9616b7af41fe8916843eb7954c55`: `closed`. Resolution: Implemented as the preferred option (make it default): E2E list selection survives in the URL (?s=) across list > checklist > report > back links (renderE2E listQuery threading). No separate return button needed.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `f2280e3c98204f0692f0d9dbaa3294bb` - report `54307aee2dd8461eb0309e28c16bfa54`

- Original `behavior:dashboard`: **fail**; 3 defined steps, 3 recorded results. Note excerpt: E2E promotion for 1b8fa9c report fails expected state of step 3
- No direct follow-up metadata link; see the explicit eight-case analysis above.
- Later report `e17b4d85e16045e7815c9e3af6e5545a` (2026-11-16T21:08:11.120436+00:00): **fail**.
  - `behavior:dashboard`: **fail**, 0/4 performed; 0/4 exact original step pairs; note: 1-2 don't exist or are named differently, also there's no "api" in our adress.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Later report `8e16e78efed146e3a9ee00a5bafda69b` (2026-11-16T23:00:22.684474+00:00): **fail**.
  - `behavior:dashboard`: **bad-test**, 0/4 performed; 0/4 exact original step pairs; note: Terrible test design.
  - `nonbehavioral:tests`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
  - `nonbehavioral:tooling`: **pass**, 0/0 performed; 0/0 exact original step pairs; note: (none).
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.

### Task `fcb4ae3317814b6a9ce95c9ff8468d7a` - report `8e16e78efed146e3a9ee00a5bafda69b`

- Saved run `1e09138698384f7e99833809a059b330`: observed state `completed`. Receipt 1 (mai-session): Added a concrete replacement dashboard E2E specification and strengthened HTTP tests for Pass/Fail reports, preserved notes, and rejected resubmission. Repository edits are limited to tests and test documentation. Validated: 14 tests passed; Ruff, formatting, and scoped Pyright passed. Pyright noted the worktree lacks its configured `.venv`. Browser retesting remains outstanding; the original report was not updated.

- Original `behavior:dashboard`: **bad-test**; 4 defined steps, 0 recorded results. Note excerpt: Terrible test design
- Direct follow-up `ba83f79146b747cd866c0a9bb1807032`: `closed`. Resolution: Confirmed: 4 near-duplicate generic steps (trailing-slash views + same-tab routes keyed separately). Generator now dedupes both (tab-keyed, slash-normalized), verified by new tests. Generator fix on branch fix/e2e-generator-strengthen. Submitted case superseded; fix verified by focused tests, full gate at batch closeout.
- No later same-commit report.
- Current boundary: applicable automated contracts listed above passed; browser interactions and historical model-run effects remain **UNVERIFIED**, unless a narrower acceptance or non-reproduction is stated in the eight-case analysis. Record closure alone is not a pass.
