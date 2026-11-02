# STT options for the remote-ai-operator phone UI

Research date: 2026-11-02. Sibling repo read-only; no inference run, no secrets read.

## 1. Meta STT: what exists and how to call it

### 1.1 Workspace state: no STT route exists in ai-workbench yet

- `packages/ai_provider/src/ai_provider/adapters/` holds chat-only clients
  (`meta.py`, `openai_responses.py`, `openai_compatible.py`, `baseten.py`,
  `ollama.py`, `openrouter.py`, `opencode_go*.py`, `modal.py`,
  `anthropic_messages.py`). None implements audio transcription.
- `packages/ai_orchestrator/examples/model_catalog.toml` declares only chat
  routes. The Meta entry (`meta/muse-spark-1.3`, base `https://api.meta.ai/v1`)
  is Responses-protocol, token-priced ($1.25 in / $4.25 out per 1M), with
  `multimodal_input = false`.
- `packages/ai_provider/docs/source-state.md` mentions audio only once: Baseten
  `audio_url` content parts let a *chat* model consume audio files. That is
  audio input to chat, not a transcription endpoint.
- The Meta adapter (`adapters/meta.py`) enforces a `muse-` model prefix and
  refuses `-contributor` variants. The voice model id below would pass the
  prefix check, but the ASR protocol (multipart POST / WebSocket) is entirely
  different from Responses — it must be a new client, never routed through
  `MetaResponsesChatClient`.
- Bottom line: adopting Meta STT means adding a new adapter + catalog route,
  not reusing the chat path.

### 1.2 Official Meta docs (dev.meta.ai, read 2026-11-02)

Model: **`muse-voice-transcribe-1.0`** — Meta's speech-to-text model on Model API.
Docs: [Speech to text](https://dev.meta.ai/docs/speech-to-text),
[Transcribe a recording](https://dev.meta.ai/docs/api-reference/voice/transcribe).

Two endpoints, same model and billing:

| Endpoint | Use | Auth |
|---|---|---|
| `POST https://api.meta.ai/v1/asr/transcribe` | One-shot file transcription | `Authorization: Bearer` header |
| `wss://api.meta.ai/v1/asr/realtime` | Live mic / streaming | First handshake frame (`Authorization` header is ignored) |

File endpoint (`/asr/transcribe`):

- `multipart/form-data` with two parts: `request` (JSON settings) and `audio`
  (the clip). Query param `sessionId` is a correlation id echoed in logs/response.
- Audio must be RIFF/WAVE, mono, 16-bit integer PCM, 16 or 24 kHz.
  Convert first, e.g. `ffmpeg -i input.m4a -ac 1 -ar 24000 -c:a pcm_s16le -map_metadata -1 output.wav`.
- `request` JSON: `{"model":"muse-voice-transcribe-1.0","audioEncoding":"WAV","mode":"PUSH_TO_TALK"}`.
  Modes: `PUSH_TO_TALK` (default, single delimited turn — fits a mic button),
  `ENDPOINTING` (model finds utterance edges, tuned for low-latency voice
  commands), `DIARIZATION` (adds speaker labels A/B; explicitly *not* tuned for
  low-latency commands).
- Optional `languageBias` (list of expected languages; 25 supported with
  code-switching) and `keywords` vocabulary biasing, fixed at session start.
- `Accept` selects the shape: JSON (buffered `turns` array), `text/event-stream`
  (turn events as processed), `text/plain` (one turn per line).
- Limits: body max 32 MB (HTTP 413), audio max 10 minutes (HTTP 400).
  HTTP 429 on concurrency/hourly session limits (back off and retry); realtime
  and file transcription share one budget.
- Output is turn-level timestamps only — no word timestamps, confidence scores,
  emotion/sound-event detection, or reformatting.

Minimal call (from the docs):

```bash
curl -X POST "https://api.meta.ai/v1/asr/transcribe" \
  -H "Authorization: Bearer $MODEL_API_KEY" \
  -F 'request={"model":"muse-voice-transcribe-1.0","audioEncoding":"WAV","mode":"PUSH_TO_TALK"};type=application/json' \
  -F "audio=@recording.wav;type=audio/wav"
```

### 1.3 Pricing and credit behavior ([pricing page](https://dev.meta.ai/docs/pricing-rate-limits), read 2026-11-02)

- **$0.18 per hour of audio processed**, metered in whole seconds (rounded down).
  Streaming and file transcription cost the same.
- Audio time is a **separate line item** from token usage; other endpoints are
  never billed for audio time. Short phone utterances cost fractions of a cent
  each (whole-second rounding means a 3.5 s utterance bills 3 s).
- No minimums or upfront commitment. **Contributor mode is not available** for
  Voice Transcribe, and zero data retention (ZDR) is priced at parity with
  Standard — so no training-discount trap like the chat Contributor variants
  the Meta adapter refuses.
- Rate limits: 256 concurrent streams, 16,000 streams/hour; no token/RPM limits.
- Same key and billing account as chat (`MODEL_API_KEY` / Meta API billing);
  judge "bring your own key" flows would charge the judge's account, matching
  the operator's existing key model. Meta has no hard provider spending cap
  (per catalog notes), so local admission bounds remain the only guard.

## 2. Free post-Nov 9 alternative

Requirement: $0, no paid inference. Two candidates.

### Option A — Browser Web Speech API (recommended)

`SpeechRecognition` (Chrome/Edge/Safari; `webkitSpeechRecognition` prefix) runs
entirely in the phone's browser: press mic button, speak, interim/final
transcript lands in the textarea. No server endpoint, no dependency, no audio
upload to our PC.

- Cost: $0. Server work: none. Latency: good for short utterances (streaming
  partials). Accuracy: strong for short dictated commands in major languages.
- Requirements: a **secure context** (HTTPS or localhost) and mic permission.
  The operator already supports an explicit private HTTPS proxy
  (`--public-origin`, "Exact HTTPS origin" in `cli.py`), so phone-over-HTTPS is
  the expected path; plain-HTTP LAN access would block both mic and recognition.
- Privacy caveat: in Chrome/Edge the audio is transcribed by the **browser
  vendor's cloud** (Google), not locally and not by Meta. Short planning
  messages/answers would pass through Google speech servers. Firefox desktop
  lacks usable support; Safari supports it with quirks. Test on the owner's
  actual phone browser.
- Failure mode is graceful: if the API is absent, hide the mic buttons and keep
  typed input as the only path.

### Option B — Local whisper-class model on the PC

`faster-whisper` (CTranslate2) running beside the operator server; phone uploads
a recorded clip, server transcribes, returns text. Fully offline and private.

| Model | Params | Disk (faster-whisper) | RAM/VRAM | Speed vs realtime | Fit for short utterances |
|---|---|---|---|---|---|
| tiny | 39 M | ~75 MB | ~1 GB | ~10x+ | Fast, weakest accuracy |
| base | 74 M | ~145 MB | ~1 GB | ~7x | Balanced default pick |
| small | 244 M | ~485 MB | ~2 GB | ~4x | Better accuracy, still light |
| medium | 769 M | ~1.5 GB | ~5 GB | ~2x | Overkill for dictation |

(Sizes from the official Whisper README figures via faster-whisper docs, corroborated
2026-11-02 across multiple sources; exact RAM depends on engine/quantization.)

- Cost: $0 after a one-time ~150–500 MB download. Privacy: audio never leaves
  the PC. Works without internet once downloaded.
- PC load: `base`/`small` transcribe a 5 s clip in ~1–2 s on CPU and idle at
  ~0; only transient CPU during transcription. No GPU needed at these sizes.
- Server work is real, though: new upload endpoint, audio validation/size caps,
  `ffmpeg` for container conversion, a `faster-whisper` (+ `ctranslate2`)
  dependency in the sibling, model download/caching, and concurrency handling.
  Estimated small feature, not a one-liner.

### Recommendation

**Ship Option A (Web Speech API, pure client-side) first.** Reasons:

1. Zero cost, zero server change, zero new dependency — smallest possible patch
   for a dictation nicety on two text inputs.
2. Short phone utterances are exactly what it does well (streaming partials,
   auto endpointing handled by the platform).
3. The operator's phone path is already HTTPS-proxy-oriented, satisfying the
   secure-context requirement.
4. The privacy trade-off (audio to browser-vendor cloud) is acceptable *if* the
   owner agrees — and if not, Option B stays available as a follow-up without
   reworking the UI (same mic buttons, different transcription backend).

Keep Meta Voice Transcribe (`$0.18/hr`, i.e. effectively free at this volume but
still paid billing) as the later upgrade path only if the owner wants
vendor-consistent transcription with diarization; it is not needed for the free tier.

## 3. Integration sketch (sibling repo, read-only analysis)

### 3.1 Where STT plugs into the UI

Targets from `src/remote_operator/index.html` + `app.js`:

- **Chat message**: `<textarea id="supervisorInput">` + `supervisorSend`
  → `POST /api/supervisor/threads/{id}/messages` with `{text}`.
- **Owner answer**: `<textarea id="answer-text">` + `send-answer`
  → `POST /api/tasks/{task_id}/answer` with `{text}`.

Both flows are "fill a textarea, click a button that POSTs `{text}`", so STT is
purely a textarea filler: add one mic toggle button beside each textarea. On
final transcript, append/insert into the textarea and let the user review before
pressing Send — never auto-send dictated text (dictation errors + approval
boundary). Show interim transcripts live in the textarea (marked provisional)
and a recording indicator; stop on second press or silence.

Out of scope for v1: `prompt` (demo playground task input) and `csv` (sample
data) — dictating CSV is not useful.

### 3.2 Server: no new endpoint for the recommended path

- Web Speech API: **pure client-side**, no server change at all. The existing
  `{text}` POSTs are untouched; the server cannot tell dictated from typed text.
- Only if Meta STT or local whisper is adopted later: add
  `POST /api/stt/transcribe` (multipart audio upload, same `Principal`
  auth/dep as other routes, strict size + duration + content-type caps,
  transcribe, return `{text}`, never persist the audio). Meta variant needs
  server-side `ffmpeg` → WAV 16/24 kHz mono → forward to
  `/v1/asr/transcribe` with the session's Meta key; whisper variant shells to
  `faster-whisper` locally. Both are separate patches with their own decision
  briefs (paid billing / new dependency).

### 3.3 Privacy notes

- Web Speech path: voice audio goes to the browser vendor (Google on
  Chrome/Android), not to our server or Meta. Transcripts then flow through the
  existing owner-reply handling (same as typed text). Judge the acceptability
  against the existing threat model: the operator already sends task text to
  Meta; this adds voice to Google. Mic use needs no server-side consent plumbing
  beyond the browser permission prompt, but the UI should label the button
  honestly (e.g. "Dictate (browser speech recognition)").
- Meta STT path (future): audio to Meta under Standard terms (no training;
  `sessionId` appears in server logs; ZDR available at parity). Fits the
  existing "judge's own key" model.
- Whisper path (future): audio stays on the PC; most private, at the cost of a
  new dependency and endpoint.
- Common: never store audio clips (transcribe-from-memory, delete temp files),
  never log transcripts beyond existing transcript handling, keep mic
  off-by-default with explicit per-utterance activation.

### 3.4 Patch scope (files in sibling `remote-ai-operator`)

Recommended v1 (Web Speech, client-only):

| # | File | Change |
|---|---|---|
| 1 | `src/remote_operator/index.html` | Add mic toggle buttons next to `supervisorInput` and `answer-text`; recording indicator element; `aria` labels |
| 2 | `src/remote_operator/app.js` | Shared dictation helper (feature-detect, start/stop, interim+final handling, error messages); wire both buttons; hide buttons when API absent |
| 3 | `src/remote_operator/app.css` | Mic button + recording-indicator styling, phone-friendly tap target |
| 4 | `tests/` (new or existing UI test file) | Static/harness checks: buttons present, helper degrades cleanly without API (exact file per sibling test layout at implementation time) |
| 5 | Sibling docs (`README.md` or `docs/`) | Short note: dictation needs HTTPS + supported phone browser; audio goes to browser vendor |

Explicitly not in v1: `web.py` (no new route), any Python dependency, any key
or billing handling, auto-send of dictated text.

Deferred (separate decisions): `src/remote_operator/stt.py` + `POST /api/stt/transcribe`
in `web.py` for the Meta/whisper backend swap; catalog + adapter entries in
ai-workbench (`model_catalog.toml`, new `adapters/meta_voice.py`) if Meta STT
joins provider routing.
