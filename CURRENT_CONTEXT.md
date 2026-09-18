# Current Context

This file is the immediate handoff for future Codex sessions. Read it before implementation work, along with `AGENTS.md`, relevant docs, and relevant project plans in `docs/plans/`.

Keep this file short and current. It is not a historical decision record; durable architecture decisions belong in `docs/decisions.md` and detailed ADRs belong in `docs/decisions/`.

## Last Completed Work

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

Last known root provider result on 2026-09-18:

```text
python -m uv run pytest              # 15 passed, 1 skipped
python -m uv run ruff check .        # passed
python -m uv run ruff format --check . # passed
python -m uv run pyright             # passed
```

The skipped test is the optional live Ollama integration test.

## Current Boundaries

- Root lint/type checks intentionally exclude prototype apps until their migration/cleanup is planned.
- `ai_provider` core must not depend on LangChain or LangGraph initially.
- Existing AI Council direct LangChain/Ollama usage is tolerated only because the app is currently a prototype.
- First provider milestone is Ollama only; Requesty and direct hosted providers come later.
- Privacy classes are prototypes and should be treated as provisional until cloud routing exists.
- Do not plan AI Council migration until `ai_provider` and `ai_orchestrator` are usable enough to support it.

## Open Conflicts Or Risks

- The old Poetry lockfiles remain in prototype apps. The workspace now uses `uv`; decide later whether to remove or preserve prototype lockfiles during app migration.
- AI Council project docs and code are not fully aligned with the new provider boundary yet.
- Job-search automation beyond `job-email` is still planned, not implemented.
- AI Council app tests were not rerun after the provider hardening change because application code was not modified in that step.

## Next Plan Of Action

Before each non-trivial step, read the relevant `docs/plans/` file and report which plan informed the work.

1. Finish `ai_provider` to a usable local stage:
   - add a one-page interface/capability spec;
   - add backend capability matrix for Ollama and planned placeholders;
   - add a small CLI or executable test client if useful;
   - decide whether to keep stdlib HTTP or switch to `httpx` before streaming/retries grow.
2. Start `ai_orchestrator` MVP from `docs/plans/05_AI_Orchestrator_Project_Plan.docx`:
   - define task profile, prompt issue, judge result, and recommendation data models;
   - implement deterministic prompt judge heuristics without external AI calls;
   - implement a transparent model/backend recommender over a small configured catalog;
   - keep execution through `ai_provider`; no provider adapters inside orchestrator.
3. Add orchestrator tests for privacy-first filtering, capability filtering, user override, and explainable rejection reasons.
4. Only after `ai_provider` and `ai_orchestrator` are usable, plan application migration. AI Council migration is explicitly not part of the immediate next phase.

## Maintenance Rule

At the end of any non-trivial task, update this file with:

- what was completed;
- newly discovered conflicts or risks;
- current validation status;
- the next recommended plan of action.
