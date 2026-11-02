# Guided UI rewrite — design (patch for remote-ai-operator, base cc3577e)

Owner decision D5=A (2026-11-02): rewrite today. The single stacked page
(8 numbered sections + playground) is undiscoverable: the demo hops §8→§3→§6,
plan approval sits above the settings it depends on, and Progress follows the
selected task instead of the open thread.

## Shape: 4 views + shared access

A tab bar (`#viewNav`) after the Access section switches views. Access,
judge quick-start, and the model-key section stay always visible (hosted and
judge flows untouched). The `#message` status line moves above the tabs so it
is visible in every view.

- **Demo** (default): guided judges' flow in order —
  1. Request (`prompt` + `inject` + `submit`, sample pre-filled)
  2. Review (`diff`, new `#verdict` line, `validation-summary`, `evidence`,
     `approve`/`reject`/`revalidate`, `question-block`)
  3. Try it (`csv`, `preview`, `issues`, `import-errors`)
  4. Demo task history (`newTask` relabeled "Start new demo draft",
     `recentTasks`, `refreshTasks`, recover-by-ID `<details>`,
     `reconcile`/`resume`/`cancel`)
  5. Demo progress (`status`, `event-summary`, `events`, `eventHistory`)
- **Supervise**: Chat (`supervisorThreads`, topic+`supervisorOpen`,
  `supervisorTranscript`, `supervisorInput`+`supervisorSend`,
  `supervisorPlan`+`supervisorWritePlan`) → Run settings (`runMode`,
  `supervisionMode`, `mailState`, `approvalWindow`, `execMode`,
  `settingsNote`, **`supervisorApprovePlan` moved here**, new
  `#planSettingsNote` restating effective settings) → Runs
  (`supervisorRuns`, thread-filtered, each with a Review button).
- **Review**: shared approval place for BOTH flows — task review is used
  from here (see JS note), Workbench external actions (`refreshExternal`,
  `externalActions`).
- **Activity**: worker/machine state — `drainStatus`, `windowStatus`,
  `agentsStatus`, spending (`allowance-summary`, `allowance-note`,
  `refreshAllowance`), `power-block`.

Wait — Review view sharing task-review elements with Demo would duplicate IDs.
Resolution: the task review + task progress sections live in the **Review**
view (not Demo); the Demo view's step 2 is a Review *step* that deep-links
("Open in Review") and the app auto-switches to Review when a demo task
reaches `awaiting_approval` or when a run Review button is pressed. One
review surface, no duplicated IDs, both flows guided to it.

Revised Demo view: Request → "Review & approve" step (status + button that
switches to Review) → Try it → Demo history. The auto-switch happens once
per status transition to `awaiting_approval` (flag reset on new selection),
never yanks the user otherwise.

## Findings mapping (operator-ux-findings-20261102)

- A (demo hopping): Demo view orders the flow; auto-switch to Review on
  `awaiting_approval`; fewer than 2 taps between steps.
- B (§6 scope): relabeled "Demo task history"; supervisor threads stay in
  Supervise (recentTasks already filters `thread` items server-side).
- C (approve above settings): `supervisorApprovePlan` moved below settings;
  `#planSettingsNote` restates run mode + supervision at approval time.
- D (progress/thread): runs filtered to the open thread; each run gets a
  Review button (fetches `run_status` for `task_id`, selects it, switches
  to Review); runs refresh on the 1s poll while a task runs.
- E (§3 confusing): new `#verdict` plain-language line
  ("Ready to approve…", "Validation failed…", "No candidate yet…") above
  the diff; evidence stays collapsed in `<details>`.

## JS edits (all IDs preserved; smoke-test couplings kept)

1. View switching (`switchView`, nav wiring, deep-link: task hash opens
   Review; default Demo).
2. Auto-switch to Review once per `awaiting_approval` transition.
3. `#planSettingsNote` update in `supervisorActions()` + `runMode` change.
4. `loadSupervisorRuns` rewrite: thread filter + Review buttons.
5. `#verdict` updates in `refresh()` + `clearTaskView()`.
6. Poll also refreshes runs.
7. Judge quick-start wording mentions views (text only).

## Couplings honored

- Every `id="..."` in the original exists exactly once in the new file
  (verified by script), plus new `viewNav`, `view-*`, `verdict`,
  `planSettingsNote`, `demoReviewCta` IDs.
- `taskId` stays inside a `<details>` (browser-smoke.mjs:102).
- All smoke-test IDs/flows work via JS-driven clicks regardless of view
  visibility; `disabled` semantics unchanged.
- No `.py` changes; no API changes. `run_status` already returns `task_id`.

## Validation (sibling side)

1. `node --check` on app.js (done here).
2. `scripts/browser-smoke.mjs` + `scripts/hosted-browser-smoke.mjs`
   (needs Node 24+ and Edge/Chromium; sibling session runs these).
3. Manual phone pass of Flow A (Demo view) and Flow B (Supervise view).

## Open layout questions (owner can answer after trying)

- View order/labels (Demo/Supervise/Review/Activity) — rename freely.
- Whether Approve-plan should ALSO stay in Chat (duplicate needs a second
  ID + handler; not done).
