# Current Context

This file is the immediate handoff for future Codex sessions. Read it before implementation work, along with `AGENTS.md`, relevant docs, and relevant project plans in `docs/plans/`.

Keep this file short and current. It is not a historical decision record; durable architecture decisions belong in `docs/decisions.md` and detailed ADRs belong in `docs/decisions/`.

## Last Completed Work

- Removed root Ruff/Pyright exclusions for prototype apps. Prototype app lint/type cleanup is allowed before application migration when changes are mechanical and behavior-preserving.
- Added `packages/ai_provider/docs/interface.md` with the provider interface boundary, core type summary, capability matrix, and HTTP-client decision.
- Kept the Ollama adapter on standard-library HTTP for now; revisit `httpx` only when streaming, richer retries, or async behavior creates a concrete need.
- Added initial `ai_orchestrator` MVP:
  - task profile, prompt issue, prompt judge result, and model recommendation data models;
  - deterministic prompt judge heuristics with no external AI calls;
  - transparent model/backend recommender over a caller-provided catalog;
  - tests for prompt judging, privacy-first filtering, capability filtering, user override, and no-match failures.
- Ran root validation with prototype apps included in Ruff/Pyright.
- Created initial Git commit `9964e69` for the workspace/restructure/provider baseline.
- Read planning input for the current provider/orchestrator phase:
  - `docs/plans/01_AI_Provider_Agnostic_Infrastructure_Plan.docx`;
  - `docs/plans/05_AI_Orchestrator_Project_Plan.docx`.
- Skipped AI Council, Job Search, and IT Services plans for the current phase because provider and orchestrator are the priority before application migration.
- Added `packages/ai_provider/README.md` and `packages/ai_provider/examples/minimal_chat.py`.
- Added `create_chat_client()` provider factory.
- Tightened `BackendConfig.from_env()` validation for unsupported providers, invalid timeouts, empty models, and non-positive timeouts.
- Tightened Ollama adapter error handling for malformed response payloads and timeout-like `URLError`s.
- Added optional live Ollama integration test gated by `AI_PROVIDER_RUN_OLLAMA_INTEGRATION=1`.
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

Last known validation result on 2026-09-18:

```text
python -m uv run pytest              # 22 passed, 1 skipped
python -m uv run --package ai-council pytest apps\ai_council\tests # 18 passed
python -m uv run ruff check .        # passed
python -m uv run ruff format --check . # passed
python -m uv run pyright             # passed
```

The skipped test is the optional live Ollama integration test.

## Current Boundaries

- Prototype apps are included in root Ruff/Pyright checks. Mechanical lint/type cleanup is allowed before application migration, provided behavior is not changed unnecessarily.
- `ai_provider` core must not depend on LangChain or LangGraph initially.
- Existing AI Council direct LangChain/Ollama usage is tolerated only because the app is currently a prototype.
- First provider milestone is Ollama only; Requesty and direct hosted providers come later.
- Privacy classes are prototypes and should be treated as provisional until cloud routing exists.
- Do not plan AI Council migration until `ai_provider` and `ai_orchestrator` are usable enough to support it.

## Open Conflicts Or Risks

- The old Poetry lockfiles remain in prototype apps. The workspace now uses `uv`; decide later whether to remove or preserve prototype lockfiles during app migration.
- AI Council project docs and code are not fully aligned with the new provider boundary yet.
- Job-search automation beyond `job-email` is still planned, not implemented.
- AI Council project docs and code are still not aligned with the new provider boundary, but migration remains deferred until provider/orchestrator are more usable.

## Next Plan Of Action

Before each non-trivial step, read the relevant `docs/plans/` file and report which plan informed the work.

1. Continue `ai_orchestrator` toward a usable MVP:
   - add a minimal configured model catalog loader or fixture format;
   - add a small execution planner that converts a recommendation into `ai_provider.BackendConfig` without executing provider calls;
   - add tests for quality threshold, latency preference, and sensitive-review rejection.
2. Continue `ai_provider` local usability:
   - optionally add a tiny module entry point around `examples/minimal_chat.py`;
   - keep stdlib HTTP unless streaming/retries/async create a concrete need for `httpx`.
3. Keep AI Council migration out of scope until `ai_provider` and `ai_orchestrator` are usable enough to support it.

## Maintenance Rule

At the end of any non-trivial task, update this file with:

- what was completed;
- newly discovered conflicts or risks;
- current validation status;
- the next recommended plan of action.
