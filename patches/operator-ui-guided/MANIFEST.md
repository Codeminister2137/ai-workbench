# Guided UI rewrite — manifest

## Base

- Repository: `remote-ai-operator`
- Base commit: `cc3577e`
- Slice: guided views rewrite of the operator single-page UI (D5=A)

## Contents (mirror paths under the sibling checkout)

| Patch path | Target path | Kind |
| --- | --- | --- |
| `index.html` | `src/remote_operator/index.html` | full-file replacement |
| `app.js` | `src/remote_operator/app.js` | full-file replacement |
| `app.css` | `src/remote_operator/app.css` | full-file replacement |
| `DESIGN.md` | — (review doc, not applied) | doc |
| `MANIFEST.md` | — (this file, not applied) | doc |

No `.py` changes. No API changes.

## Apply order

1. Copy the three files over their targets.
2. Run validation below. There is no step 3: layout follow-ups (view
   labels/order, finding-E detail) need owner input after a live pass.

## Validation steps

From the `remote-ai-operator` checkout:

1. `node --check src/remote_operator/app.js` (already green here).
2. `node scripts/browser-smoke.mjs` — needs Node 24+ and Edge/Chromium;
   spins its own scripted server, spends nothing.
3. `node scripts/hosted-browser-smoke.mjs` — same requirements.
4. Manual phone pass: Flow A in the Demo view, Flow B in Supervise,
   approvals in Review.

## Verified here (without sibling writes)

- `node --check`: pass.
- ID preservation: all 91 original `id="..."` present exactly once; 13 new
  IDs (`viewNav`, `view-*`, `nav*`, `verdict`, `planSettingsNote`,
  `demoReviewCta`, `demoReviewStatus`); zero dupes.
- `taskId` still inside a `<details>` (browser-smoke.mjs coupling).
- Every JS-referenced element ID exists in the new HTML.
- JS diff limited to the 7 intended groups (views, poll runs refresh,
  settings note, thread runs + Review buttons, verdict/CTA, auto-switch,
  saved-task view).
