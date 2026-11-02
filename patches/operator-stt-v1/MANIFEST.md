# STT v1 (browser dictation) — manifest

## Base

- Repository: `remote-ai-operator` (sibling; this patch was built without
  writing there)
- Base commit: `cc3577e`
- Prerequisite: `operator-ui-guided` applied first. These files are full-file
  replacements derived from that bundle's v2 `index.html` / `app.js` /
  `app.css`; applying them on any other base will clobber unrelated UI.

## Contents (mirror paths under the sibling checkout)

| Patch path | Target path | Kind |
| --- | --- | --- |
| `index.html` | `src/remote_operator/index.html` | full-file replacement |
| `app.js` | `src/remote_operator/app.js` | full-file replacement |
| `app.css` | `src/remote_operator/app.css` | full-file replacement |
| `DESIGN.md` | — (review doc, not applied) | doc |
| `MANIFEST.md` | — (this file, not applied) | doc |

No `.py` changes. No API changes. No new dependency, key, or billing.

## Diff summary vs the guided-UI v2 bundle

- `index.html`: +3 `div.dictate-row` blocks (mic button + EN/PL select +
  status live region), one after each of the `prompt`, `supervisorInput`,
  and `answer-text` labels. No v2 line otherwise touched.
- `app.js`: +1 appended dictation section (`Dictation`, `dictateLangName`,
  `dictateErrorMessage`, `joinDictation`, `wireDictation` + 3 calls). No v2
  line touched.
- `app.css`: +8 appended rules (`.dictate-row`, `.dictate-btn`,
  `.recording` pulse, `.dictate-lang`, `.dictate-status`). No v2 line
  touched.

## New element IDs (9; each exactly once)

- `dictate-prompt`, `dictate-lang-prompt`, `dictate-status-prompt`
- `dictate-supervisor`, `dictate-lang-supervisor`, `dictate-status-supervisor`
- `dictate-answer`, `dictate-lang-answer`, `dictate-status-answer`

All v2 IDs preserved exactly once (see verification).

## Apply order

1. Confirm `operator-ui-guided` is already applied.
2. Copy the three files over their targets.
3. Run validation below.

## Validation steps

From the `remote-ai-operator` checkout:

1. `node --check src/remote_operator/app.js` (already green here).
2. `node scripts/browser-smoke.mjs` — needs Node 24+ and Edge/Chromium;
   spins its own scripted server, spends nothing.
3. `node scripts/hosted-browser-smoke.mjs` — same requirements.
4. Manual phone pass on the target phone (Xiaomi Redmi Note 13 Pro 5G,
   mobile Chrome, Tailnet HTTPS): dictate in English and Polish into the
   demo request, chat message, and owner answer; confirm interim text
   appears, final text is committed, nothing sends without review, and
   errors (mic denied) read honestly. Confirm mic buttons are absent on
   Firefox desktop.

## Verified here (without sibling writes)

- `node --check`: pass.
- ID preservation: every v2 `id="..."` present exactly once; 9 new IDs
  above, each exactly once; zero dupes; every JS-referenced ID exists.
- Graceful degradation: dictate rows ship `hidden`; the helper returns
  before unhiding when the API is absent (stub-harness verified).
- Dictation section references no send/submit control (`supervisorSend`,
  `send-answer`, `submit` untouched by the new code).
