# STT v1: browser dictation for the operator UI — design

Client-only patch. Derived from the `operator-ui-guided` v2 bundle
(`index.html`, `app.js`, `app.css`); the v2 element IDs are the contract and
are preserved untouched. Prerequisite: `operator-ui-guided` applied first
(sibling base `cc3577e`).

Sources: `patches/operator-stt-research/RESEARCH.md`,
`patches/operator-stt-research/OPEN-QUESTIONS.md` (Decided section),
`patches/operator-stt-research/I18N-INPUT.md` (Decided section).

## What it does

Adds a mic toggle button plus an EN/PL language picker beside three
textareas:

| Textarea (v2 ID) | View | Mic button | Language select | Status line |
| --- | --- | --- | --- | --- |
| `prompt` | Demo step 1, Request | `dictate-prompt` | `dictate-lang-prompt` | `dictate-status-prompt` |
| `supervisorInput` | Supervise, Chat message | `dictate-supervisor` | `dictate-lang-supervisor` | `dictate-status-supervisor` |
| `answer-text` | Review, owner answer | `dictate-answer` | `dictate-lang-answer` | `dictate-status-answer` |

Press the mic, speak, press again or pause: the transcript is written into
the textarea. Dictation FILLS the field only — it never sends, submits, or
answers. The user reviews and edits, then presses the existing
Send/Submit button. This is the decided NO auto-send rule (Q5).

## Decisions mapped to the research briefs

- Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`), pure
  client-side. No server route, no dependency, no key, no billing.
- Day-one languages: English (default, must work) + Polish
  (`en-US`, `pl-PL` per-utterance `lang`). Further languages only after a
  cost-vs-reward evaluation — the `<select>` takes more `<option>`s later.
- The demo `prompt` input IS covered (chat + answer + prompt). The research
  sketch left `prompt` out of scope, but the v1 task names it explicitly;
  the `csv` sample-data input stays typed-only (dictating CSV is useless).
- Typed non-English input is already accepted everywhere (plain textareas);
  no change needed for that half of the I18N rule. The English-normalization
  pipeline step is server work and explicitly NOT part of this patch.
- Target phone is Xiaomi Redmi Note 13 Pro 5G, mobile Chrome, over Tailnet
  HTTPS (secure context, mic permission available). Firefox desktop lacks
  the API, so the PC browser simply shows no mic buttons.

## Implementation

`index.html`: one `div.dictate-row` (with `data-dictate-for` naming the
paired textarea) after each of the three `<label>`s. Each row holds the mic
button, a `dictate-lang` label + `<select>` (English default, Polski), and
a `dictate-status` live region. Rows ship with the `hidden` attribute; JS
removes it only when the API exists.

`app.js`: one shared helper appended after the v2 code; no v2 line touched.

- `Dictation` — feature detection (`supported()`), session factory, and a
  single-active-session guard (`stopActive`/`setActive`/`clearActive`), so
  starting dictation in one field stops any other.
- `wireDictation(fieldId, buttonId, langId, statusId)` — per-field wiring.
  When unsupported it returns before unhiding, leaving typed input as the
  only path.
- Recognition runs `interimResults = true`, `continuous = false` (single
  utterance; the platform end-points on silence), `maxAlternatives = 1`.
- Interim transcripts render live in the textarea (provisional, overwritten
  as results stream); on `end` only final text is committed, appended after
  the pre-dictation content with a separating space. If the user typed
  during dictation, the final text is appended to their edit rather than
  clobbering it.
- Recording indicator: the button gains a `recording` class (red pulse, see
  `app.css`), flips to "Stop dictation" with `aria-pressed="true"`, and the
  status line shows "Listening (English/polski)…".
- Errors map to plain-language status notes (mic blocked/HTTPS, no speech,
  no mic, service unreachable, language unsupported); error notes are also
  mirrored to the global `#message` line. `start()` exceptions restore the
  pre-dictation text.

`app.css`: `.dictate-row` flex layout with an explicit
`.dictate-row[hidden]{display:none}` (author `display:flex` would otherwise
override the UA `hidden` rule), 44 px mic tap target, `.recording` pulse,
compact language select, status line styling.

## Privacy

Button labels and tooltips say "browser speech recognition" and name the
browser vendor (Google on Chrome) as the transcriber — never implying local
or Meta transcription. Per-tap mic, off by default. Accepted by the owner
for hackathon/personal use; a company product gets the whisper/DPA path
later behind the same buttons.

## Graceful degradation

- No API (Firefox desktop, old browsers): rows stay `hidden`; zero visual
  or behavioral change vs v2.
- API present but mic denied / insecure context: honest error note naming
  mic permission + HTTPS.
- Mid-dictation language switch: applies to the next utterance (the running
  session keeps its start-time `lang`).

## Known limitations

- Interim rendering briefly replaces the textarea content each result; a
  concurrent external edit in the same field during that window could be
  overwritten (user typing is protected, see above).
- No word timestamps/confidence — the API returns plain transcripts.
- Safari supports the API with quirks; v1 is tested against mobile Chrome.

## Verification

- `node --check` on `app.js`: pass.
- ID preservation: every v2 `id="..."` present exactly once; 9 new IDs
  (table above), each exactly once; every JS-referenced ID exists in HTML.
- Stub-harness run (temporary, removed afterwards): unsupported API leaves
  rows hidden and wires nothing; fake recognition fills the field on final
  results, commits on end, reports `not-allowed` honestly; the dictation
  section references no send/submit control.
- Manual phone pass still needed: dictate EN + PL into all three fields on
  the target phone, confirm review-before-send and HTTPS behavior.
