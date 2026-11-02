# Translation / normalization-step brief (remote-ai-operator, DESIGN ONLY)

Status: design only. No code written, no sibling files touched, no inference
run, no secrets read, no paid calls. Sibling repo (`remote-ai-operator`)
treated as read-only.

Sources read (2026-11-02):

- `patches/operator-stt-research/I18N-INPUT.md` (incl. Decided)
- `patches/operator-stt-research/RESEARCH.md`
- `patches/operator-meta-stt/DESIGN.md` (billing/metering patterns to mirror)

Sibling patterns inspected read-only: `web.py` (`ThreadMessage`,
`ThreadTopic`, `AnswerInput`, `Principal` deps, supervisor routes),
`supervisor.py` (`open_thread`, `post_message`, `write_plan`, `approve_plan`,
history/plan/run shapes), `meta.py` (grant/allowance admission, `key_source`
closure, receipt vocabulary).

Decided inputs this brief reuses (not re-decided):

- Input is multilingual (STT dictation or typed); planning/dev stay in English.
- Day-one languages: English MUST work, Polish heavily recommended; more only
  after cost-vs-reward evaluation.
- Translator: Meta chat now (hackathon credits), free alternative later.
- Source text preserved verbatim; English working translation accompanies it
  into threads, plans, and runs; source language tagged.
- Normalization is server/pipeline work, NOT part of STT v1.

## 1. Placement: where the native-language -> English step runs

### 1.1 Options considered

| Option | Where | Verdict |
|---|---|---|
| A. Client pre-send | Browser translates before POST | Rejected |
| B. Server acceptance (recommended) | Sibing server translates at ingestion, before history append | Recommended |
| C. Lazy thread ingestion | Store source, translate at plan/run time | Rejected |

Why A is rejected:

- CSP is `connect-src 'self'`; the browser must never call Meta directly
  (same constraint as STT DESIGN.md section 6).
- The browser never holds the Meta key; client-side translation would mean a
  different vendor (browser/Google) with inconsistent quality and no ledger.
- Bypasses admission/billing entirely; judges would not self-pay.

Why C is rejected:

- Planning replies (`Supervisor._live_reply` builds its prompt from the last
  10 history turns) would consume non-English text, violating the
  planning-in-English rule.
- Mistranslation would surface late (at plan approval or run time) instead of
  at message time, when the author is present to correct it.

### 1.2 Recommended: server acceptance at the Supervisor boundary

Translate synchronously at ingestion, inside the lock, BEFORE the user turn is
appended to history. Exact call sites (sibling, future patch):

1. `Supervisor.post_message`: translate `text` (+ caller-supplied
   `source_lang`, default `en`) before `thread["history"].append(...)`.
   This covers chat messages AND `reply_to_owner_thread` (it delegates to
   `post_message`), so owner replies are normalized on the same path.
2. `Supervisor.open_thread`: translate `topic` the same way. The thread
   `prompt` feeds every planning prompt (`"Planning thread '{prompt}'..."`)
   and `write_plan` output, so it must be English working text with source
   preserved alongside.
3. Owner-answer ingestion (`POST /api/tasks/{task_id}/answer`,
   `AnswerInput.text`): translate at the same boundary before the answer
   resumes the task. Same data shape, same translator, same ledger.

Request-shape consequence: `ThreadMessage`, `ThreadTopic`, and `AnswerInput`
each gain an optional `language` field (BCP47, default `"en"`; day-one
allowlist `en` + `pl`, extensible; unknown tag -> 422). The client sends the
dictation/typing language it already knows (the STT picker drives this same
value). `extra="forbid"` stays; this is an additive optional field.

Failure semantics: translate-then-append is atomic under the existing
`operator.lock`. Translation failure stores NOTHING (no half-state turn):
map to the existing error vocabulary (section 5). Scripted/offline mode
(`ScriptedModel`, no key/grant): skip translation, store verbatim with
`translator: "none"` and `translated: false` (section 2); planning proceeds
on source text and the review note flags it untranslated.

## 2. Data shape (source + working text preserved through threads/plans/runs)

English working text is what history, planning prompts, plans, and runs
consume. Source is preserved verbatim next to it, never overwritten.

User turn (appended to `thread["history"]`):

```json
{
  "role": "user",
  "text": "<English working text>",
  "source_text": "<verbatim submitted text>",
  "source_lang": "pl",
  "translated": true,
  "translator": "meta:muse-spark-1.3"
}
```

Conventions:

- `text` is ALWAYS the English working text. When `source_lang` is `en`
  (or translation is skipped in scripted mode), `text == source_text`,
  `translated` is `false`, and `translator` is `"none"`.
- `source_text` is ALWAYS the verbatim submission, byte-identical to what the
  client sent.
- `source_lang` is the validated BCP47 tag from the request (echoed, like the
  STT receipt echoes `language`).
- `translator` is a stable id: `meta:<model-id>` now (e.g.
  `meta:muse-spark-1.3`), `free:<impl-id>` after the swap (section 6),
  `"none"` when no translation ran. This id is the audit trail for which
  engine produced the working text.
- Assistant turns are unchanged (`role`, `text`, `route`).

Thread topic: `thread["prompt"]` stays the English working topic (existing
readers — `_live_reply`, `write_plan`, `list_threads` truncation — are
untouched). Add sibling keys `prompt_source`, `prompt_lang`,
`prompt_translator` with the same conventions.

Plans: `write_plan` builds from working `text` as today (no change to plan
rendering or the nonce/digest approval binding). The thread record SHOULD also
carry a small translation manifest for the review UI, e.g.
`thread["translation"] = {"langs": ["pl"], "translators":
["meta:muse-spark-1.3"], "untranslated": false}` — computed at plan time from
history turns. Runs: the enqueued job (`plan`, `plan_digest`) is English-only
as today; copy the manifest into the job JSON (`translation_manifest`) so a
run is auditable without re-reading the thread.

Migration: existing threads/turns lack the new keys. Readers MUST treat
missing `source_text`/`translator` as legacy English (`translated: false`,
`translator: "none"`); no backfill.

## 3. Meta chat route + metering

### 3.1 Which route performs translation

The EXISTING Meta Responses chat route (`meta/muse-spark-1.3`,
`https://api.meta.ai/v1/responses`) via the existing chat adapter — NOT a new
model, NOT the ASR endpoint. Translation is a narrow chat call:

- Same session Meta key as model runs (decided key reuse; `key_source`
  closure, cleared after use, never logged — mirror `meta.py` /
  STT DESIGN.md section 2).
- Translation-only instructions ("Translate the following <lang> text to
  English. Return only the translation, no commentary."), NO tools, low
  output cap (input length is already bounded: 4000 chars for messages/topics,
  2000 for answers).
- Suggested sibling module (future patch):
  `src/remote_operator/translate.py` with
  `translate_text(key_source, grant, store, text, source_lang)`, raising a
  `MetaFailure`-style typed error the Supervisor/web layer maps per section 5.
  Keeps `supervisor.py` thin and mirrors the `meta.py` / proposed `stt.py`
  separation.

Skip fast-path: when `source_lang == "en"`, no provider call is made at all
(no spend, no latency); the turn is stored per section 2 with
`translator: "none"`.

### 3.2 Metering: REUSE the run-grant pattern (recommended)

**Recommendation: same effective grant, same `allowances` ledger row as model
runs** (`owner grant` first, else the subject's judge self-grant via
`effective_grant`; `Store.reserve_allowance`, same `grant_id`). Rationale:

- Translation is token-priced chat, so it FITS the existing `InferenceGrant`
  (`input/output_usd_per_million`) with no new price dimension — unlike STT
  audio seconds, which needed a server-side constant (STT DESIGN.md risk 1).
  No grant fingerprint change, no migration hazard.
- One spending view in `GET /api/allowance`; judges stay self-paying for
  their own non-English input.
- Short inputs (<=4000 chars) cost fractions of a cent per message; the
  reservation is a normal small chat reservation.

Mechanics (mirror STT DESIGN.md section 3, token-priced):

- Reserve allowance BEFORE sending; exhausted -> 409 with the existing
  "Inference allowance exhausted; no request sent" message; no provider call.
- Each translation consumes request count + token USD reservation like a small
  chat op. The ledger keeps the conservative reservation (no true-up,
  consistent with chat).
- Record a receipt in the existing `inference_receipt` event vocabulary plus
  translator fields (`translator`, `source_lang`, `chars_in/out`), so spend
  and provenance are both auditable from thread events.

Rejected alternative: a separate translation counter/bucket. It would split
the budget (translation-heavy sessions starve runs or vice versa with no
shared view), need new grant UX for judge translation limits, and repeat the
split-brain problem STT DESIGN.md section 8.2 flags — with none of STT's
excuse, since token pricing already fits the grant.

## 4. Surfacing mistranslation risk to reviewers

The approval flow (nonce + `plan_digest` binding, expiry, invalidation on
change) is UNCHANGED and continues to bind the exact reviewed English plan
bytes. Translation risk is surfaced as review context, not as a second
approval:

1. Plan-review banner (required): when the thread manifest shows any
   `translated: true` turn, the review UI shows a note such as
   "Includes text translated from PL via Meta muse-spark-1.3 — source
   preserved below; verify meaning before approving." When any turn is
   untranslated non-English (scripted/offline path), the banner instead warns
   "Contains untranslated non-English text — planning ran on source text."
2. Per-message source expansion (required): each translated user turn renders
   working English by default with an expander showing verbatim
   `source_text` + `source_lang` + `translator` id, so a bilingual reviewer
   can compare without leaving the review screen.
3. Run audit (recommended): run detail shows the copied translation manifest
   (langs + translator ids), so post-hoc review can ask "was this run's plan
   shaped by translation, and by which engine?"
4. Optional hardening (open decision 6): require an explicit "I checked the
   translation" checkbox before Approve is enabled on threads with
   translations. Recommended to DEFER — banner + expander is enough for v1.

Never auto-correct or hide the source; never re-translate silently between
review and approval (the digest binding already prevents plan substitution).

## 5. Error mapping (mirror existing vocabulary)

| Situation | Status | Behavior |
|---|---|---|
| Bad/unsupported `language` tag | 422 | Specific reason; nothing stored |
| No grant / no key attached, non-English input | 409 | "Translation unavailable; ..." — client offers: send as English-typed (author self-translates), retry after attaching key, or (scripted) accept untranslated with flag |
| Allowance exhausted | 409 | "Inference allowance exhausted; no request sent"; nothing stored |
| Provider 401/403 (key refused) | 409 | "Provider refused the session key; re-attach and retry" |
| Provider 429 | 429 | Retryable; `Retry-After` passthrough when present |
| Provider 5xx / timeout / malformed | 502 | "Translation provider unavailable" / "Malformed provider response"; nothing stored |
| Empty translation of non-empty input | 502 | Treat as malformed provider response |

All provider details redacted to the same ~700-char bound as `MetaFailure`.
English (`source_lang: en`) submissions NEVER touch this path — they post
exactly as today, so translation outages cannot break English-only use.

## 6. Free-later swap path

The call site (`Supervisor.post_message` / `open_thread` / answer ingestion)
depends on a narrow `Translator` interface, not on Meta. The free
implementation MUST implement:

```python
class Translator(Protocol):
    id: str                      # recorded in turns, e.g. "free:argos-en-pl"
    def supported_languages(self) -> list[str]: ...
    def needs_key(self) -> bool: ...          # Meta: True; free: False
    def estimate_usd(self, text: str) -> str: ...  # free: "0"
    def translate(self, text: str, source_lang: str) -> TranslationResult: ...

@dataclass
class TranslationResult:
    text: str            # English working text
    source_lang: str     # validated tag
    translator_id: str   # self.id
```

Swap mechanics:

- Selection is server config (e.g. `--translator meta|free:<id>` or
  settings), NOT per-request; the `translator` id recorded per turn preserves
  which engine ran, so mixed-history threads stay auditable after a swap.
- `needs_key() == False` implementations skip key resolution AND the ledger
  reservation (no spend), but keep the same data shape, review UI, and error
  mapping (provider errors become local errors with the same 422/502
  surface).
- Candidate free engines (undecided, evaluate later): local text-translation
  model (e.g. Argos Translate / NLLB-class) beside the server. Explicitly NOT
  browser translation (same bypass/consistency reasons as placement option A).
- Contract tests for the swap: each implementation must pass a shared fixture
  (EN passthrough byte-identical, PL->EN smoke pair, over-limit rejection,
  empty-input rejection) before selection.

## 7. Privacy handling

- Source text enters existing handling (threads/events/plans) exactly like
  typed text does today — no new store, no new retention class.
- Transit: browser -> operator server over Tailnet HTTPS, server -> Meta over
  HTTPS under the existing Standard terms (no training). No new data class is
  created; translation just sends user text the operator would already send
  for planning.
- Never log source/working pairs beyond existing transcript handling; log
  only coarse events ("translation rejected: bad language", "translation
  provider 429").
- UI honesty: the review note (section 4) always names the engine that ran
  per turn (`translator` id); no silent engine switching within a thread
  beyond the recorded config change.

## 8. Top 3 risks

1. **Mistranslation becomes plan.** The English working text — not the
   author's words — is what planning, the plan artifact, and the run consume.
   A fluent-but-wrong translation is harder to catch than a dictation typo,
   and the nonce/digest approval binds the (possibly wrong) English bytes.
   Mitigations: verbatim source always preserved and one click away at review
   (section 4.2), banner forcing reviewer attention (4.1), EN transcript of
   record stays byte-bound. Residual risk: monolingual reviewers cannot verify
   — accept for hackathon/personal use, revisit (deferred checkbox, section
   4.4) if real use shows errors.
2. **Every non-English message is now a metered inference call on the send
   path.** Translation adds latency (one chat round-trip before the planning
   reply, which is itself a call — message post becomes two sequential
   provider calls) and spend to each message, and failures (429/5xx/exhausted
   allowance) now block SENDING, not just replying. A translation outage or
   empty allowance bricks non-English input while English keeps working.
   Mitigations: skip fast-path for English (zero added latency/spend),
   fail-closed with nothing stored (no half-threads), 409 fallback offers
   (section 5). Needs load/latency judgment at implementation time.
3. **Scope creep across three ingestion points + schema drift.** The step must
   land identically in `post_message`, `open_thread`, AND answer ingestion
   (miss one and non-English leaks into planning untranslated), while history
   turns, thread prompts, manifests, and run jobs each gain translator-aware
   fields. Partial implementation silently violates the planning-in-English
   invariant. Mitigations: single `translate.py` module + shared call helper
   used by all three sites, legacy-tolerant readers (missing keys = English),
   contract tests asserting every ingestion path normalizes (section 6).

## 9. Open decisions (for owner/implementer)

1. 409-no-key fallback for non-English input: block with retry (recommended),
   or accept untranslated-but-flagged so offline/scripted use keeps working?
2. `language` field shape: optional-with-`en`-default on the three models
   (recommended), or required like the STT `language` field?
3. Day-one allowlist: exactly `en` + `pl`, or accept any BCP47 and let Meta
   handle it (cost-vs-reward gate says constrain — confirm `en`+`pl`)?
4. Translation prompt: fixed server-side English-only instruction
   (recommended), or allow target language parameterization for future
   non-English planning (out of scope per decided rule)?
5. Receipt/allowance surfacing: fold translation tokens into the single
   reserved-USD figure (recommended, like chat), or break out a translation
   line in `/api/allowance` and receipts?
6. Review hardening: banner + expander only for v1 (recommended), or also
   require the "I checked the translation" checkbox before Approve?
7. Free-engine pick (later): which local text-translation engine + size, and
   does it run beside the server (recommended, mirrors whisper Option B) or
   as a sidecar?
8. Mixed-language single message (code-switched PL+EN): translate whole-turn
   with source_lang as written (recommended) or per-sentence detection (out
   of scope)?
9. Topic translation UX: translate the thread topic at creation (recommended)
   or keep topics author-verbatim and translate only message turns?
10. Latency budget: is two sequential provider calls per non-English message
    acceptable, or should translation + first planning reply be fused into
    one call later (quality risk — keep separate for v1)?
