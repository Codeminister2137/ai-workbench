# Parallel pilot 2026-11-01: two worktree-isolated workers

## Setup

Two subagents spawned together, each confined to its own git worktree on its
own branch, each committing there (no push/merge by workers):

- Worker A: `ai-workbench` worktree, `feature/parallel-a-digest-probe` —
  digest slice 1 (local IMAP probe + offline fetch, `scripts/mail_digest.py`,
  8 tests, doc). Committed 16:40:25Z.
- Worker B: `remote-operator` worktree, `feature/parallel-b-admission` —
  D3 strict `.js`/`.html` admission + D2 60 min task approvals
  (`control.py`, 12 tests, doc). Committed 16:42:04Z.

Repo-first split: disjoint repositories, so no file overlap by construction.
Workers shared only the parent `.venv` interpreters (read-only use).

## Verification and merge (parent, serial)

Parent independently re-ran each gate, reviewed both diffs, then merged:
A → `develop` (`e74fabc`), B → operator `main` (`1364de8`). Follow-ups found
in review: test-group assignment for the new digest test (pre-push hook
requirement), and separate task/plan approval minutes in `/api/settings`
plus UI label (`9c0e2ec`). Full gates green after merge (operator 394).
Both repos pushed; serve restarted and live-verified (60/10 windows).

## Honest speedup note

Wall-clock for both slices was ~max(A, B) instead of A+B: commits landed
99 s apart after concurrent execution. Coordination cost stayed serial
(worktree setup, independent verification, review, merging) and dominated
the small slices. Parallelism paid off here because the slices were
genuinely independent (separate repos); same-file slices would still
serialize on review/merge. No clobbering, no cross-worker interference.
