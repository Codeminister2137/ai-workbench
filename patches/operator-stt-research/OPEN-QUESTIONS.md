# Open questions for the owner (operator STT research)

Research: `RESEARCH.md` in this directory. No code written; sibling untouched.

## Decided (owner, 2026-11-02)

- Q1: browser-cloud STT accepted for hackathon/personal use with mitigations
  (short utterances, per-tap mic, honest label); company product gets the
  whisper/DPA-covered path later. Matches the hackathon/company split.
- Q2: test phone is Xiaomi Redmi Note 13 Pro 5G, mobile Chrome. PC browser
  is Firefox (dictation v1 targets the phone; Firefox desktop lacks the API).
- Q3: answered by verification -- phone route is Tailnet HTTPS (secure
  context satisfied).
- Q5: NO auto-send, ever for v1. Dictation fills the textarea; the user
  reviews AND can edit before Send (STT is never trusted verbatim).

1. **Browser-vendor cloud STT acceptable?** The recommended free path (Web Speech
   API) sends short voice clips to the phone browser's vendor (Google on
   Chrome/Android) for transcription. Typed-equivalent transcripts then flow as
   today. Is that within the privacy boundary, or must voice stay on-device/PC
   (which forces the local-whisper path with server work)?
2. **Target phone browser/OS?** Web Speech quality and API availability differ
   (Chrome/Edge best, Safari quirkier, Firefox desktop effectively absent).
   Which phone + browser will actually use dictation, so v1 can be tested there?
3. **Phone access goes over the HTTPS proxy?** Mic + Web Speech require a secure
   context (HTTPS). Is the `--public-origin` private proxy the intended phone
   route, or is there a plain-HTTP LAN flow that would block dictation?
4. **Scope: only the two owner inputs?** Proposed v1 covers the Chat message
   (`supervisorInput`) and the parked-work answer (`answer-text`). Should the
   demo-playground `prompt` input also get dictation, or stay typed-only?
5. **Never auto-send dictated text — confirm?** Proposal: dictation fills the
   textarea; the user always reviews and presses Send. Confirm no hands-free
   auto-send mode is wanted (it would bypass the review-before-approval habit).
6. **Meta Voice Transcribe later?** At $0.18/hour of audio (≈ fractions of a
   cent per utterance, separate line item, no Contributor variant, ZDR at
   parity), Meta STT could replace browser STT later with a server endpoint +
   new ai-workbench adapter. Wanted on the roadmap, or is free-only a hard
   constraint for this UI?
7. **Polish dictation needed?** Both Web Speech and whisper handle Polish, but
   accuracy testing and `languageBias` settings differ. Is English-only v1
   acceptable, or must Polish work from day one?
