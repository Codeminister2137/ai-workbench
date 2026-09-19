# Prompt Library Guide

`docs/prompt-library.md` is the canonical prompt library for this repository.

Use this guide for how to apply those prompts in PyCharm AI Assistant or in this
Codex chat.

## Repository Source Of Truth

- `docs/prompt-library.md` contains the full prompt text.
- The PyCharm AI Assistant prompt library is an IDE-side copy and may drift until
  manually synced.
- `docs/pycharm-ai-prompt-library.md` was the earlier local summary and should
  be treated as superseded by these two files.

## Using Prompts In This Codex Chat

When asking Codex to use a prompt, name it directly:

```text
Use Codex: Investigate First for this request.
```

Codex should read `docs/prompt-library.md` and follow the named prompt. If the
prompt references `$SELECTION`, Codex should use the current request,
conversation context, or explicitly provided selected text as the selection.

## Using Prompts In PyCharm

The PyCharm Prompt Library is separate IDE state. To use the same prompts there:

1. Open PyCharm AI Assistant prompt/library settings.
2. Create or update a prompt with the same `Codex: ...` name.
3. Copy the corresponding prompt body from `docs/prompt-library.md`.
4. Keep `$SELECTION` where the prompt expects selected code or text.

## Suggested Prompt Flow

For larger tasks:

1. `Codex: Context Primer`
2. `Codex: Investigate First`
3. `Codex: Decision Brief`, if a material decision appears
4. `Codex: Implement After Decision`
5. `Codex: Test Plan`, if test coverage is unclear
6. `Codex: DoD Closeout`

For transition points after commits, before a new slice, or after resuming:

1. `Codex: Prompt Library Check`
2. Follow the smallest useful prompt sequence it recommends.

For architecture-heavy work:

- `Codex: ADR Gap Check` checks for missing or stale ADR coverage.
- `Codex: ADR Capture` records an approved durable decision.

For scope control:

- `Codex: MVP/Stop Review` checks whether the current plan is becoming too broad
  or speculative.
