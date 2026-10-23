# ADR-067 — Temporary: Codex write delegation runs with the sandbox bypass

**Status:** Accepted as a **temporary workaround**, explicitly flagged for
replacement

**Date:** 2026-10-23

## Context

The owner's delegation policy sends work that is too hard for the current agent
to Codex. On this machine Codex is delivered in two places:

- the PyCharm 2025.3 bundled agent binary (`...PyCharm2025.3\aia\codex\...`,
  0.137.0), which authenticates but rejects every requested model id with
  "not supported when using Codex with a ChatGPT account" and reports
  `sandbox backend: disabled` in `codex doctor`;
- the PyCharm 2026.2 ACP-bundled binary
  (`...PyCharm2026.2\acp-agents\codex-acp\2.2.2\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin\codex.exe`,
  0.160.1), which authenticates and defaults to `gpt-6.1-sol`, but whose
  sandbox backend is also disabled: `--sandbox workspace-write` flips the
  approval policy to `Never` yet both `exec` writes and `apply_patch` report
  "writing is blocked by the read-only sandbox".

With no functioning sandbox backend, a Codex delegation can analyse but cannot
produce any file change, which defeats the point of delegating implementation.

## Decision (owner, 2026-10-23)

Run Codex write delegations with `--dangerously-bypass-approvals-and-sandbox`
on the 0.160.1 binary — **temporarily**, and only while the sandbox backend
stays broken. The owner chose this as option 1 and required it to be flagged as
a temporary solution rather than adopted as the normal setup.

## Consequences and required compensating controls

- Codex runs unsandboxed with full write access to the repository while the
  owner's ~55-file uncommitted work is checked out. Every delegation therefore
  carries real destructive-edit risk.
- Required controls while this lasts: the human owner stays the acceptance
  boundary; every Codex write is reviewed through `git status`/`git diff`
  against the pre-run snapshot before anything is accepted; prompts restrict
  Codex to named new/changed files; no secrets or credentials are placed in
  delegation prompts; a failed or suspicious run is stopped and reported, not
  retried blindly.
- Read-only analysis delegations keep their normal `--sandbox read-only`
  invocation; the bypass is not used when no writes are requested.

## Exit condition (why this is temporary)

Replace this workaround when any of the following lands: a functioning sandbox
backend in the Codex build PyCharm actually invokes (workspace-write with an
enforcing backend), a fixed/updated PyCharm 2025.3 bundled binary, or Codex
running as a proper CLI install with its default sandbox. Until then this ADR
is the standing flag that the bypass is a deviation, not the intended setup.
