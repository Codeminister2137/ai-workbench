# ADR-030 - Persistent Local Chat Transcripts

**Status:** Accepted
**Date:** 2026-09-30

## Context

The repo assistant has reached the point where the CLI-first execution,
approval, delegation, validation, and handoff workflow is predictable enough to
start the first thin interactive-chat slice.

Architecture notes already say that application chats should be represented as
provider-neutral local transcripts, that a model change should keep the same
chat, and that any future truncation or summarization must be visible when a
model cannot fit the full history.

The decision boundary was whether the first chat slice should stay in-memory or
persist local chat transcripts. The selected direction is persistent local chat
transcripts because it aligns with those architecture notes and makes resume and
eventual model switching meaningful.

## Options Considered

- In-memory chat only for the first slice.
- Persistent local chat transcripts in SQLite.
- Plain JSONL or Markdown transcript files.
- External or cloud-hosted transcript storage.

## Decision

Use a local SQLite-backed provider-neutral transcript store for repo-assistant
chat sessions and ordered messages.

The initial default database is `data/repo-assistant-chats.sqlite3`, with
`--chat-db PATH` available for explicit local override. The transcript stores the
message content actually sent to the provider, including selected repository
context, plus assistant responses and secret-free provider/model metadata.

The first CLI surface is `--mode chat`. It can create a new session, resume the
latest repository session with `--chat-session last`, resume a specific session
ID, and list recent sessions with `--chat-list`.

## Reason

SQLite fits the current local, single-developer workflow and matches the storage
approach already accepted for orchestrated repo-assistant run records. It gives
structured, inspectable local persistence without introducing a daemon, queue,
external service, credentials, or remote transcript storage.

Persisting the actual provider-neutral messages keeps resume behavior honest:
later turns see the same retained context that was previously sent. Storing only
short summaries or raw user prompts would make resume less reliable and would
hide context-loss behavior behind an implementation detail.

## Consequences

- Chat transcripts are local runtime data and remain ignored by Git.
- Transcript databases may contain user prompts and selected repository context,
  so they should be treated as private local files.
- This decision does not approve personal memory, semantic search, background
  scheduling, autonomous external actions, cloud transcript sync, or external
  storage.
- The first implementation supports provider API and local runtime routes. Codex
  CLI/external-agent chat transcript integration can be added later when its
  resume semantics are designed explicitly.
- Future truncation, summarization, deletion/export, and model-switching
  behavior should build on this provider-neutral transcript boundary rather than
  inventing a separate chat state format.
