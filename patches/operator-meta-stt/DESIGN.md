# Meta STT server-side design (remote-ai-operator, DESIGN ONLY)

Status: design only. No code written, no sibling files touched, no inference
run, no secrets read. Sibling repo (`remote-ai-operator`) treated as read-only.

Sources read (decided research, 2026-11-02):

- `patches/operator-stt-research/RESEARCH.md`
- `patches/operator-stt-research/OPEN-QUESTIONS.md` (incl. Decided)
- `patches/operator-stt-research/I18N-INPUT.md` (incl. Decided)

Sibling patterns inspected read-only: `web.py` (`Principal`, `owner`/`visitor`
deps, `RequestBodyLimitMiddleware`, `BufferedBodies`), `credentials.py`
(`SessionKeys.key_for`), `meta.py` (`InferenceGrant`, `MetaModel` key-source
handling), `store.py` (`reserve_allowance`), `judge_grants.py`.

Decided inputs this design reuses (not re-decided):

- Meta STT key source: the SAME Meta API key already used for model runs
  (session key). No separate STT credential.
- No auto-send, ever for v1: dictation fills the textarea; the user reviews,
  edits, and presses Send.
- Input is multilingual; day-one languages: English MUST work, Polish heavily
  recommended. Further languages only after cost-vs-reward evaluation.
- Phone route is Tailnet HTTPS (secure context satisfied); test phone is Xiaomi
  Redmi Note 13 Pro 5G, mobile Chrome.
- Browser-cloud STT accepted for hackathon/personal use with mitigations;
  company product gets the whisper/DPA-covered path later.
- Meta model: `muse-voice-transcribe-1.0`, one-shot file endpoint
  `POST https://api.meta.ai/v1/asr/transcribe` (multipart `request` JSON +
  `audio` WAV, mono 16-bit PCM 16/24 kHz, mode `PUSH_TO_TALK` fits a mic
  button). $0.18/hour of audio, whole-second floor. Provider limits: 32 MB
  body, 10 min audio. No Contributor variant; ZDR at parity.

## 1. Endpoint contract

### 1.1 Route

`POST /api/stt/transcribe` in the sibling `web.py`, registered for BOTH
`create_app` (owner) and `create_hosted_app` (visitor) via the existing
`Principal` dependency (`owner` / `visitor`). Same-origin only: the CSP is
`connect-src 'self'`, so the browser must never call Meta directly.

Auth behavior (no new credential):

- Owner deployment: existing `Authorization: Bearer <access_token>` check, then
  the same Meta key resolution the owner model runs use.
- Hosted deployment: existing session cookie + `x-operator-request: 1` header
  checks inside `visitor`, then `sessions.key_for(token, subject)` — the exact
  same call the model factory path uses. Keyless sessions get 409 (mirror the
  existing "Set judge spending limits first" / "Hosted model route is not
  configured" 409 style), and the client falls back to Web Speech (section 6).
- The Meta key must be pulled per request through a `key_source`-style closure
  and cleared after use, mirroring `MetaModel.next_operation` (which resets
  `self._key = ""` in `finally`). Never log, persist, or echo the key; reuse
  the `_redact` habit for provider payloads.

### 1.2 Request shape (browser -> operator server)

`multipart/form-data` with fields:

| Field      | Type   | Required | Notes                                              |
|------------|--------|----------|----------------------------------------------------|
| `audio`    | file   | yes      | Clip blob; see accepted types below                |
| `language` | string | yes      | BCP47 tag chosen per utterance (`en`, `pl`, ...)   |
| `input`    | string | no       | Hint only: `supervisor` \| `answer`; purely for client-side routing of the returned text, never trusted server-side for anything else |

Accepted `audio` content types (recommended): `audio/webm` (MediaRecorder
default on Chrome/Android), `audio/wav`, `audio/mp4` (Safari fallback).
The server converts to Meta's required format with ffmpeg (section 1.4).
Reject anything else with 422.

### 1.3 Limits (local, stricter than Meta's)

Meta allows 32 MB / 10 min, but dictation utterances are seconds long. Local
admission bounds are the only spend guard (Meta has no provider cap), so:

- Max utterance duration: **60 s** (probed server-side after decode; spoofed
  container headers must not be trusted).
- Max upload body: **4 MB** for the `audio` part (covers 60 s of Opus/WebM with
  headroom; converted WAV at 16 kHz mono s16le is ~32 KB/s, so 60 s ≈ 1.9 MB).
- Over duration -> 422; over bytes -> 413.
- Convert target: WAV mono 16-bit PCM **16 kHz** (halves bytes vs 24 kHz;
  both are accepted by Meta).
- Request timeout to Meta: 60 s, mirroring the chat adapter's deadline.
- Concurrency: rely on Meta's 256 concurrent / 16,000 streams/hour budget
  shared with file transcription; add a small local semaphore (e.g. 4
  concurrent transcriptions) so one client cannot exhaust the shared budget.

Middleware warning (implementer must handle): `_base_app` installs
`RequestBodyLimitMiddleware(max_body_size=8192)` globally plus the
`BufferedBodies` POST replay wrapper. An audio upload WILL trip the 8 KB cap.
The STT route needs a path-aware exemption (skip/raise the cap for
`/api/stt/*`) while keeping 8 KB everywhere else. `BufferedBodies` replays
`Request.body()`, which is compatible but means the full clip is buffered in
memory — acceptable at a 4 MB cap.

### 1.4 Server flow

1. Authenticate via `Principal` (section 1.1). Resolve effective grant
   (section 3); if none or no key attached -> 409, client falls back.
2. Validate `language` against the day-one set (+ extensible allowlist);
   validate `audio` content type and size (413/422).
3. Reserve allowance BEFORE sending (section 3). Exhausted -> 409 with the
   existing "Inference allowance exhausted; no request sent" message.
4. Decode + probe with ffmpeg (duration check), convert to 16 kHz mono s16le
   WAV in memory (spill to temp file only if needed; delete in `finally`).
5. Forward to Meta:

   ```http
   POST https://api.meta.ai/v1/asr/transcribe?sessionId=<server-uuid>
   Authorization: Bearer <session-meta-key>
   Accept: application/json
   ```

   multipart parts: `request` =
   `{"model":"muse-voice-transcribe-1.0","audioEncoding":"WAV","mode":"PUSH_TO_TALK","languageBias":[...]}`,
   `audio` = converted WAV. `sessionId` is a fresh random UUID per request
   (correlation only, appears in Meta logs; must NOT be the user id, subject,
   or anything linkable). `languageBias` maps from the `language` field
   (exact Meta language codes TBD — see section 8). `httpx` client with
   `trust_env=False`, `follow_redirects=False`, as in `meta.py`.
6. Parse Meta JSON `turns` array, join turn texts in order, return section 1.5.
   Delete temp bytes. Never write audio or transcripts to the store/events/log.

### 1.5 Response shape (operator server -> browser)

Success (200, JSON):

```json
{
  "text": "transcribed utterance",
  "language": "pl",
  "duration_seconds": 4.2,
  "billed_seconds": 4,
  "receipt": {
    "provider": "meta",
    "model": "muse-voice-transcribe-1.0",
    "reservation_usd_estimate": "0.000300",
    "spending_control": "local_estimate_not_provider_cap"
  }
}
```

- `text`: required, may be empty string when Meta returns no turns (client
  shows "nothing heard", keeps existing textarea content).
- `language`: echo of the request tag, so the pipeline can tag source language
  per I18N-INPUT consequence 4.
- `billed_seconds`: whole-second floor, matching Meta metering.
- `receipt`: mirrors the chat `last_receipt` vocabulary; no usage-token fields
  (audio billing has none).

Errors use the existing `{"detail": ...}` shape:

| Situation | Status | `detail` hint |
|---|---|---|
| No session / bad owner token | 401 | existing messages unchanged |
| Missing session header (hosted) | 403 | existing message unchanged |
| No grant / no key attached | 409 | "Transcription unavailable; ..." (client falls back to Web Speech) |
| Allowance exhausted | 409 | "Inference allowance exhausted; no request sent" |
| Upload over 4 MB | 413 | "Audio exceeds 4 MB limit" |
| Bad/unsupported audio, over 60 s, bad language | 422 | specific reason |
| Meta 401/403 (session key refused) | 409 | "Provider refused the session key; re-attach and retry" |
| Meta 429 (concurrency/hourly budget) | 429 | "Transcription busy; retry or use browser dictation" + `Retry-After` passthrough when present |
| Meta 400/413 (clip rejected) | 422 | redacted provider detail, max ~700 chars |
| Meta 5xx / timeout / transport | 502 | "Transcription provider unavailable" |
| Malformed Meta response | 502 | "Malformed provider response" |

All provider details redacted to the same ~700-char bound as `MetaFailure`.

## 2. Session-Meta-key auth reuse

- The SAME key as model runs (decided). Locally: whatever credential the owner
  run path uses. Hosted: `sessions.key_for(token, subject)` in-memory session
  key; judges use their own attached key, so STT spend lands on the judge's
  account exactly like runs do.
- Key lifetime handling is inherited: expiry -> `SessionUnavailable` ->
  existing 401 mapping; client treats it as "fall back + prompt reconnect".
- No key transport to the browser beyond what exists today (the browser never
  sees the Meta key; it only holds the session cookie / owner token).
- Pydantic/model note: no new key models. The STT module takes a `key_source`
  callable (same convention as `MetaModel`), so tests can inject a fake without
  touching `SessionKeys`.

## 3. Admission and billing hooks

- The grant/allowance to consume: **the same effective grant** as model runs
  (`owner grant` first, else the subject's judge self-grant via
  `effective_grant`), recorded in the **same `allowances` ledger row**
  (`Store.reserve_allowance`, same `grant_id`). Rationale: one spending view
  in `GET /api/allowance`, no split-brain budget, judges stay self-paying.
- Each transcription consumes **one request count** against `max_requests`
  plus a USD reservation of `ceil(duration_cap_s) * 0.18 / 3600`
  (60 s cap -> $0.003 worst case). Actual billed cost
  (`floor(processed_s) * 0.18/3600`) is reported in the receipt but the ledger
  keeps the conservative reservation — consistent with the existing ledger,
  which never trues-up chat reservations either.
- Price constant: `AUDIO_USD_PER_HOUR = "0.18"` as a server-side constant, NOT
  judge-configurable (judge grant forms stay token-priced; adding audio price
  fields would change the `InferenceGrant` fingerprint and trip "Consumed grant
  settings cannot be changed" for existing ledgers — see risk 1).
- Suggested new module (sibling, future patch): `src/remote_operator/stt.py`
  with a `transcribe(key_source, grant, store, audio_bytes, language)` function
  that owns reserve -> convert -> forward -> parse, raising a `MetaFailure`-style
  typed error the route maps per section 1.5. Keeps `web.py` thin and mirrors
  the `meta.py` separation.

## 4. Privacy handling

- Audio retention: **none by default**. Transcribe from memory; any temp file
  is unlinked in `finally`; no audio bytes in SQLite (`tasks`/`events`),
  logs, receipts, or error payloads.
- Transcripts: the returned `text` is NOT persisted by the STT route. It only
  enters existing handling after the user presses Send (same as typed text),
  tagged with the source `language`.
- Transit only: browser -> operator server over Tailnet HTTPS, server -> Meta
  over HTTPS. Meta Standard terms (no training); `sessionId` is a random
  per-request UUID with no linkability to subject/task.
- UI honesty: the mic button label must name the backend actually used
  ("Dictate (Meta)" vs "Dictate (browser)"), since the fallback changes who
  hears the audio (Meta vs browser vendor). No silent backend switching.
- Records: log only coarse events ("stt request rejected: over duration cap",
  "stt provider 429") at debug/info, never transcripts, durations tied to
  subjects, or key material.

## 5. Multilingual behavior (from I18N-INPUT decided)

- `language` is required per utterance; the client offers a picker defaulting
  to the last-used language (day-one: `en` + `pl`).
- Server maps `language` -> Meta `languageBias` (fixed at session/request
  start). Code-switching within the utterance is handled by Meta's 25-language
  support; the bias list should be `[requested, en]` so English planning terms
  inside a Polish utterance still resolve (exact code strings TBD, section 8).
- Normalization to English stays OUT of this endpoint (separate pipeline
  brief): STT returns source-language text + tag; translation happens later.

## 6. Browser client call shape

Same-origin `fetch` (CSP `connect-src 'self'` forbids direct Meta calls):

```js
const form = new FormData();
form.append("audio", webmBlob, "clip.webm");
form.append("language", pickedLang); // "en" | "pl"
form.append("input", "supervisor");  // or "answer"
const res = await fetch("/api/stt/transcribe", {
  method: "POST",
  credentials: "include",              // hosted session cookie
  headers: { "x-operator-request": "1" }, // hosted; owner uses Authorization Bearer instead
  body: form,
  signal: AbortSignal.timeout(75000),
});
if (!res.ok) throw new SttError(res.status, await res.text());
const { text, language } = await res.json();
// insert into the textarea as provisional, user reviews, then Send
```

Client flow (both `supervisorInput` and `answer-text` share one helper):

1. On mic press: if `config.live_inference` is true (key attached), record via
   `MediaRecorder` (mimeType `audio/webm;codecs=opus` preferred, Safari
   fallback `audio/mp4`) and POST on stop/silence/max-60s. Show a recording
   indicator + elapsed time (no interim partials on this path).
2. On Meta-path failure (network error, timeout, 429, 502, 409-no-key): fall
   back to Web Speech `SpeechRecognition` with `lang` = picked language when
   available, showing interim transcripts live. If Web Speech is absent too,
   show a typed-only message.
3. If `config.live_inference` is false from the start, go straight to Web
   Speech (the free v1 path); Meta STT is purely an upgrade when a key route
   is configured.
4. Never auto-send on any path. Provisional text is visually marked until the
   user edits/confirms by pressing Send. Mic buttons hide only when NEITHER
   backend is available (no MediaRecorder/fetch route AND no SpeechRecognition).
5. Language picker sits next to the mic button and drives both `language`
   (Meta path) and `recognition.lang` (Web Speech path).

## 7. Three hardest risks

1. **The allowance model does not fit per-second audio billing.** `InferenceGrant`
   is token-priced (`input/output_usd_per_million`), the ledger stores
   reservation estimates with no true-up, and the grant fingerprint freezes
   settings after first use. Bolting audio spend onto it means either a second
   price dimension inside the frozen grant (migration hazard: fingerprint
   change bricks existing ledgers) or a server-side constant outside the grant
   (judges cannot see/negotiate the audio price; `max_requests` gets shared by
   two very different cost profiles, so a dictation-heavy session can starve
   runs or vice versa). Any choice here changes what `GET /api/allowance`
   means and needs care.
2. **The HTTP boundary was built to reject exactly this request.**
   `RequestBodyLimitMiddleware(8192)` + `BufferedBodies` assume small JSON
   POSTs. Carving a 4 MB multipart exemption without weakening the global cap,
   handling FastAPI `UploadFile` spooling safely, adding an ffmpeg dependency
   with duration probing that resists spoofed headers and decompression bombs,
   and keeping temp-file hygiene on every error path is the largest
   server-side attack-surface change in this patch. ffmpeg availability in the
   deployed environment (PC + any hosted image) is unconfirmed.
3. **Client capture heterogeneity + honest fallback matrix.** MediaRecorder
   codecs differ (Chrome `webm/opus` vs Safari `mp4`), there are no interim
   partials on the Meta path (worse UX than Web Speech for long utterances),
   the 60 s client/server cap must agree, and the fallback chain
   (Meta -> Web Speech -> typed) triples the test matrix across browsers that
   each support a different subset. The privacy label must track the backend
   actually used per utterance, or the owner cannot tell whether Meta or
   Google heard a given clip.

## 8. What a future implementer still needs decided

1. Backend order when both exist: Meta-first with Web Speech fallback (this
   design's recommendation), or Web-Speech-first (free) with Meta as manual
   override? Affects spend and UX.
2. Allowance bucket: shared `max_requests`/ledger row with runs (recommended
   here) or a separate STT request/USD bucket? If separate, where does its UI
   surface and who configures judge STT limits?
3. Exact local caps: is 60 s / 4 MB right, or lower (30 s) for tighter spend?
4. Accepted upload codecs: `webm` + `wav` + `mp4`, or require client-side WAV
   encoding to drop server ffmpeg? (Client-side WAV bloats uploads ~10x.)
5. Exact Meta `languageBias` code strings for `en`/`pl` (+ bias list shape:
   `[requested, en]` or `[requested]` only?). Confirm from current Meta docs.
6. Meta `mode` fixed to `PUSH_TO_TALK`, or `ENDPOINTING` for snappier command
   edges? (Diarization explicitly out: not tuned for commands.)
7. Meta `Accept` shape: JSON `turns` (recommended) vs SSE vs plain text.
8. ffmpeg in the deploy: system dependency, vendored binary, or pure-Python
   decode (e.g. `soundfile`) with ffmpeg only as fallback?
9. Realtime WebSocket (`/asr/realtime`) explicitly out of scope? (Recommended:
   yes — file flow covers dictation; streaming adds auth-handshake and billing
   complexity for no v1 benefit.)
10. Judge grant UX: show audio spend as a separate line in `/api/allowance`
    and receipts, or folded into the single reserved-USD figure?
11. ZDR flag for STT: request zero-data-retention explicitly (parity-priced),
    or accept Standard? Needs a check of how ZDR is signaled for ASR.
12. `sessionId` correlation: random UUID per request (recommended) or a
    hashed thread/task id for support debugging? (Prefer unlinkable.)
13. Demo-playground `prompt` input: dictation or typed-only? (STT v1 said
    typed-only; confirm it stays that way once server STT exists.)
14. Client recording UX: manual stop only, auto-stop on silence, or fixed max
    with countdown? Who owns the 60 s cutoff display?
