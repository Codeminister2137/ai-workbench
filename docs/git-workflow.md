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
