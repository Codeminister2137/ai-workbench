# Current Context

This file is the immediate handoff for future Codex sessions. Read it before implementation work, along with `AGENTS.md`, relevant docs, and relevant project plans in `docs/plans/`.

Keep this file short and current. It is not a historical decision record; durable architecture decisions belong in `docs/decisions.md` and detailed ADRs belong in `docs/decisions/`.

## Last Completed Work

- Resolved bootstrap decisions for repository layout, package tooling, Python version, provider contract shape, first backend scope, existing prototype status, and prototype privacy classes.
- Initialized Git after adding root `.gitignore`.
- Restructured the repository into:

```text
packages/
  ai_provider/
  ai_orchestrator/
apps/
  ai_council/
  job_search/
tests/
```

- Added root `uv` workspace configuration and generated `uv.lock`.
- Added initial `ai_provider` package with:
  - neutral chat-first request/response contracts;
  - provider/backend identity;
  - usage metadata;
  - provider error categories;
  - prototype privacy classes;
  - local Ollama adapter.
- Added placeholder `ai_orchestrator` package.
- Moved existing AI Council and job-email code under `apps/` as prototypes.
- Kept `apps/ai_council/council.json` trackable as project configuration.
- Ignored private/local artifacts such as `.env`, PDFs, sent email history, SQLite data, caches, `.venv`, and IDE files.

## Current Validation Baseline

Run from repository root:

```powershell
python -m uv sync --all-packages --all-groups
python -m uv run pytest
python -m uv run --package ai-council pytest apps\ai_council\tests
python -m uv run ruff check .
python -m uv run ruff format --check .
python -m uv run pyright
```

Last known result: all commands passed on 2026-09-18.

## Current Boundaries

- Root lint/type checks intentionally exclude prototype apps until their migration/cleanup is planned.
- `ai_provider` core must not depend on LangChain or LangGraph initially.
- Existing AI Council direct LangChain/Ollama usage is tolerated only because the app is currently a prototype.
- First provider milestone is Ollama only; Requesty and direct hosted providers come later.
- Privacy classes are prototypes and should be treated as provisional until cloud routing exists.

## Open Conflicts Or Risks

- The old Poetry lockfiles remain in prototype apps. The workspace now uses `uv`; decide later whether to remove or preserve prototype lockfiles during app migration.
- AI Council project docs and code are not fully aligned with the new provider boundary yet.
- Job-search automation beyond `job-email` is still planned, not implemented.
- No initial Git commit has been created yet; all trackable files are currently untracked.

## Next Plan Of Action

Before each non-trivial step, read the relevant `docs/plans/` file and report which plan informed the work.

1. Review and commit the current repository baseline after confirming the trackable file list contains no private artifacts.
2. For provider work, read `docs/plans/01_AI_Provider_Agnostic_Infrastructure_Plan.docx`, then add concise provider package documentation and a minimal usage example.
3. Decide whether to add an optional real-Ollama integration test gated by environment variables.
4. Continue the AI Provider-Agnostic Infrastructure milestone by tightening config and adapter boundaries.
5. Before AI Council migration, read `docs/plans/02_AI_Council_Project_Plan.docx` and compare it with the current prototype.
6. Before job-search work, read `docs/plans/03_Job_Search_Automation_Project_Plan.docx` and compare it with the current `job-email` prototype.
7. Migrate AI Council to consume `ai_provider` only after the provider contract is stable enough.

## Maintenance Rule

At the end of any non-trivial task, update this file with:

- what was completed;
- newly discovered conflicts or risks;
- current validation status;
- the next recommended plan of action.
