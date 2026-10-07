# Python semantic rename preview and apply

**Option A accepted by the owner on 2026-10-06; offline implementation complete.**
The owner selected this direction to advance IDE independence. PyCharm remains
permissible during the transition, but the long-term goal is for project tools to
work independently of it. See [ADR-045](../decisions/ADR-045-ide-independent-semantic-rename.md).

## Why a decision is needed

The available PyCharm `rename_refactoring` accepts a project path, old symbol
name and new name, then applies the rename. Its schema has no preview parameter.
Wrapping it would not provide the rename preview promised by the foundation plan.
Renaming and then reverting the working tree is not a reliable preview: it would
temporarily mutate user files and could overwrite concurrent editor changes.

The choice affects a new dependency, public tools, approval scope and eventual
independence from the IDE. Existing interpreter/diagnostics/symbol wrappers and
the temporary PyCharm bridge remain available during migration.

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

Accepted v1 contract:

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

Implementation detail: the `rename-preview` optional extra pins Jedi 0.20.0;
without it the tools remain discoverable but preview reports the installation
command. `rename_preview` is read-only and returns the complete diff plus a
five-minute, one-use plan handle. `rename_apply` is a WRITE tool. Under
interactive approval the callback receives the plan digest and complete diff,
not only the opaque handle. The plan is process-local and owner/task/workspace
bound; route changes within the foreground owner may reuse it, but process
restart cannot. Preview verifies that each current file still matches Jedi's
source snapshot before preparing the plan. Application rechecks all original
digests before writing, then uses atomic per-file replacements and reports
partial effects without rollback.

Acceptance should cover cross-file imports/calls, duplicate names in separate
scopes, Unicode/newlines, unchanged preview bytes, outside/link refusal, stale
files, expired handles, denied/no-human approval and partial-write reconciliation.
An isolated temporary-package preview passed through both the native registry
and foreground HTTP MCP transport using a synthetic MCP client; the fixture
remained unchanged. Interactive denial also passed through the shared transport
and left the fixture unchanged. After the owner approved the exact displayed
`Widget` -> `Gadget` diff, apply through that transport succeeded under the
interactive permission policy; both changed files and their effect receipts
were verified, then the disposable fixture was cleaned up. The owner's approval
was supplied in chat and relayed to the exact-diff callback. This is bounded
synthetic-client acceptance, not proof of physical terminal input, a live
third-party client, or overall IDE independence.

Offline implementation plus bounded native/shared-transport acceptance are
complete; installed-client/attended acceptance remains separate. The owner selected the standalone
preview/apply direction because project tools should eventually be independent
of PyCharm, while allowing PyCharm to host tools during the transition. This
choice advances that goal for Python rename but does not itself complete IDE
independence.

## IDE-independent navigation extension

The current continuation adds a read-only `python_navigate` tool to the native
and shared coding profiles. It accepts `definitions` or `references`, resolves
an identifier at a one-based file position with the same pinned optional Jedi
dependency, and returns up to 100 workspace-relative Python results with short
snippets. Results outside the workspace, non-Python files and invalid positions
are excluded and counted. The read-only inspection profile is unchanged.

This is a bounded convenience for ordinary Python projects, not a language
server or a completeness guarantee: dynamic imports, generated code and other
runtime behavior can make Jedi references incomplete. It adds no dependency,
persistent state, write authority or PyCharm requirement. Installed-client
acceptance remains part of the broader C5/M5 work.
