# Multilingual input requirement (owner, 2026-11-02)

## Rule

- **Input is multilingual:** any user (e.g. the owner's friend handed the
  phone) can submit ideas in their native language, by STT dictation or by
  typing.
- **Development and planning stay in ONE language** (English) to avoid
  confusion for AI and humans alike.

## Consequences

1. STT v1 must support choosing the dictation language (Web Speech `lang`
   per utterance; NOT English-only). Owner to confirm the day-one language
   set (Polish + ?).
2. Typed non-English input must be accepted wherever ideas are entered
   (chat message, owner answer; demo prompt stays English-only).
3. A **normalization step to English** is required between input and
   planning/dev: dictated/typed native-language text is preserved verbatim
   as the source, and an English working translation accompanies it into
   threads, plans, and runs. The translator (paid Meta chat vs free local
   option) is an open design point with billing/dependency trade-offs —
   needs a decision before implementation.
4. Transcripts/threads should tag the source language so the pipeline and
   reviewers can distinguish source text from working translation.

## Scope note

Items 1–2 ride with STT v1 (client-side). Item 3 is server/pipeline work and
is NOT part of STT v1; it needs its own brief (translator choice, where the
step runs, how mistranslation risk is surfaced).
