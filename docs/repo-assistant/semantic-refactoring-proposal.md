# Semantic rename preview: owner decision

**PROPOSED; not approved or implemented.** Investigated 2026-10-05 to make the
remaining C5/M5 boundary concrete. Neither candidate library is installed in the
workspace. Public package metadata and pinned source were inspected without
importing them or changing dependencies.

## Why a decision is needed

The available PyCharm `rename_refactoring` accepts a project path, old symbol
name and new name, then applies the rename. Its schema has no preview parameter.
Wrapping it would not provide the rename preview promised by the foundation plan.
Renaming and then reverting the working tree is not a reliable preview: it would
temporarily mutate user files and could overwrite concurrent editor changes.

The choice affects a new dependency, public tools, approval scope and eventual
independence from the IDE. Existing interpreter/diagnostics/symbol wrappers remain
the accepted working implementation.

| Option | Benefit | Trade-off |
| --- | --- | --- |
| A: Optional standalone Python rename preview, initially Jedi | Inspect actual proposed edits before applying; advances IDE independence | New library and a two-step plan/apply contract require approval and acceptance |
| B: Approved PyCharm rename followed by diff review | Smallest integration using the installed host | No true preview; depends on PyCharm and needs an explicit broad-effect/reconciliation contract |
| C: Keep read-only IDE tools and ordinary reviewed file edits | No new dependency or mutation surface | Semantic rename remains unfinished |

Recommendation: **A**, starting with one Python symbol rename rather than a
general refactoring framework. Keep the existing IDE bridge available. Choose C
if semantic rename is not yet worth another dependency; do not describe B as a
preview-based operation.

## Candidate comparison

Jedi 0.20.0 declares Python 3.14 support and has one runtime dependency, Parso.
Its published license is MIT. [Release notes](https://jedi.readthedocs.io/en/stable/docs/changelog.html)
and [package metadata](https://pypi.org/project/jedi/0.20.0/) support those claims.
The pinned source separates `get_changed_files()` / `get_new_code()` from
`apply()`. Our adapter would inspect proposed text and use the project's guarded
write path, rather than call the library's direct writer.
[Pinned refactoring source](https://github.com/davidhalter/jedi/blob/v0.20.0/jedi/api/refactoring/__init__.py).
It also offers references/navigation, making it a plausible future C5 backend;
complex references may be incomplete, and default parser caching is not thread
safe. [API documentation](https://jedi.readthedocs.io/en/stable/docs/api.html).

Rope 1.15.0 also declares Python 3.14 support. It depends on
`pytoolconfig[global]` and lists LGPL-3.0-or-later. [Package metadata](https://pypi.org/project/rope/1.15.0/).
It exposes change previews separately from applying them, with broader refactoring
operations. Its project setup normally creates `.ropeproject` and reads project
configuration; `ropefolder=None` avoids that folder. This is a capable alternative,
but requires more configuration/state investigation for the narrow initial task.
[Library documentation](https://rope.readthedocs.io/en/latest/library.html).

These are declared/source-level compatibility findings, not local acceptance.
After approval, verify the exact release on the configured Python 3.14 SDK before
claiming it handles this repository. No library is guaranteed to find every
dynamic Python reference.

## Recommended v1 contract

This is the proposed implementation scope for approval, not an accepted API:

1. Preview identifies an existing workspace Python file, symbol position and
   valid new identifier. Reject ambiguous selection, syntax failure and file/module
   moves initially. It returns the affected file list, complete bounded diff and
   an opaque, short-lived plan handle tied to the task/workspace/foreground owner.
2. The plan contains exact original file-byte digests and proposed contents.
   Reject outside-workspace paths, links, unsupported encodings and unrepresentable
   or oversized previews. Derive the diff from exact contents; do not assume a
   library-formatted diff preserves newline details.
3. Apply requires existing write authority and a fresh approval where the selected
   preset asks. Approval refers to the complete immutable plan, not just a new name.
   Restart expires the handle and approval; a handle alone grants no write access.
4. Verify every original digest before the first write. Changed files invalidate
   the preview. Use atomic file replacements and retain actual per-file effect
   receipts. Multiple files are not an atomic transaction: report partial failure
   and require reconciliation; never blindly undo user edits.
5. Keep plan state in the foreground owner; introduce no database, daemon or
   general language-server infrastructure. Preview must not execute project code,
   create project state or silently install packages. Interpreter, cache and
   concurrency isolation are part of acceptance, not assumptions about the library.

Acceptance should cover cross-file imports/calls, duplicate names in separate
scopes, Unicode/newlines, unchanged preview bytes, outside/link refusal, stale
files, expired handles, denied/no-human approval and partial-write reconciliation.
Run a real isolated fixture through native and shared MCP routes after approval.

Owner question: approve A with optional Jedi/Parso and this narrow contract,
choose B with its explicit lack of a preview, or defer via C? If selecting A/B,
record why that trade-off matters so the subsequent ADR preserves the owner's intent.
