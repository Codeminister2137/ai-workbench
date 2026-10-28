# Git Workflow

Use Git history as part of the project design. The repository should be easy to
review by the owner, future Codex sessions, and portfolio reviewers.

## Branch strategy

This repository uses a two-branch integration model.

### `master` — stable, portfolio-facing

`master` always contains complete, validated, presentable work.

- Recruiters and reviewers land here.
- Only promoted from `develop` at an explicit stable milestone.
- Never the direct target of feature branches.
- Never force-pushed.

### `develop` — integration branch

`develop` is where all feature branches are merged and integrated.

- Every new feature or fix branch is created from `develop`.
- Merge feature branches into `develop` when work is complete and validated.
- `develop` is periodically promoted to `master` via fast-forward or a clean
  merge commit when the accumulated work is stable and presentable.
- `develop` is never deleted; it is the permanent integration branch.
- Investigate read-only here if useful, but create or resume a focused working
  branch before editing. Do not implement or commit task changes directly here
  without an explicit owner exception for that task.

### Feature branches

Before the first repository edit, verify the branch and create a focused branch
from `develop` (or resume the applicable existing working branch):

```powershell
git switch develop
git switch -c feature/short-purpose
```

Use branch names that describe the work, such as:

- `feature/provider-ollama-adapter`
- `feature/orchestrator-routing-mvp`
- `docs/architecture-decisions`
- `fix/provider-timeout-errors`

This applies to documentation and mechanical fixes too. A clean checkout, branch
cleanup or handoff saying "continue/work only on develop" identifies the base and
integration target; it does not authorize direct development there. Only an
explicit owner request for direct edits on `develop` waives the rule for that task.

If edits already exist on `develop`, create the focused branch at its current tip
with `git switch -c ...` and verify the changes carried over. Preserve all work;
do not reset, discard or stash it merely to change branches. After validation,
merge through the normal integration workflow. Start any further fix on a working
branch rather than editing `develop` after the merge.

### Promoting `develop` to `master`

When `develop` is stable and the accumulated work is complete:

```powershell
git checkout master
git merge --ff-only develop   # prefer fast-forward; use a merge commit only
                               # if the histories have genuinely diverged
git push origin master
```

Do not promote to `master` mid-feature or to satisfy a deadline. The goal
is that `master` always reflects a coherent, working state.

### Retiring working branches

Use commit ancestry and the current roadmap, rather than age alone. A merged
branch with a completed purpose can be removed locally with `git branch -d`
after verifying its tip is contained in `develop`. Preserve `develop` and
`master`. A branch still representing an active milestone may be fast-forwarded
to `develop` and retained; incomplete goals belong in the roadmap and handoff,
not in divergent stale branches.

Remote deletion needs an explicit owner request and a fresh remote/ref check.
Publish reviewed integration work before removing its old remote branch names.
Do not delete a branch with unique work, an active worktree, or an unresolved
review. Detached review snapshots and private backup refs are separate from
completed feature branches and must not be included in automatic cleanup.

## Commits

Commit often enough that each commit has one coherent purpose. Prefer several
small reviewable commits over one mixed checkpoint.

Good commit messages are imperative and specific:

```text
Add neutral orchestrator execution targets
Document dependency selection policy
Fix provider timeout validation
```

Avoid vague messages such as:

```text
updates
misc fixes
work in progress
```

## Validation Before Commit

The repository uses `pre-commit` for repeatable local checks:

```powershell
python -m uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

The `pre-commit` stage runs fast file-oriented checks:

- `ruff check --fix`;
- `ruff format`.

The `pre-push` stage runs slower repo-wide checks:

- `pyright`;
- `scripts/run-tests.py full`, covering the offline workspace and Council suites.

See [test selection and timing](test-workflow.md) for focused component commands,
class-level selection, profiling evidence and the separate live test boundary.

Live integration tests stay out of Git hooks. They may require Ollama, external
services, credentials, network access, or local state, so run them explicitly
when working on the relevant integration boundary.

Run the narrow relevant checks while iterating. Before committing behavior
changes, make sure the relevant hook stage has passed unless the user explicitly
waives it.

For documentation-only changes, at minimum inspect the diff and run
`git diff --check`.

## History Hygiene

Do not rewrite, reset, or discard user work without explicit approval.

Before final reporting, inspect:

```powershell
git diff --stat
git status --short
```

Report the branch, commits created, validation performed, and any known skipped
checks.
