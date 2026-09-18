# Git Workflow

Use Git history as part of the project design. The repository should be easy to
review by the owner, future Codex sessions, and portfolio reviewers.

## Branches

Use `master` as the stable base branch.

For non-trivial work, create a focused feature branch:

```powershell
git switch -c feature/short-purpose
```

Use branch names that describe the work, such as:

- `feature/provider-ollama-adapter`
- `feature/orchestrator-routing-mvp`
- `docs/architecture-decisions`
- `fix/provider-timeout-errors`

Small documentation or mechanical fixes may happen directly on the current
feature branch when they support that branch's work.

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

Run the narrow relevant checks while iterating. Before committing behavior
changes, run the configured project checks unless the change is documentation-only
or the user explicitly waives them:

```powershell
python -m uv run pytest
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run pyright
git diff --check
git status --short
```

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
