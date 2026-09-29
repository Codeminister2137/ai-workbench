# ADR-029 - Orchestrated Repo Assistant Supervised Validation

**Status:** Accepted
**Date:** 2026-09-30

## Context

The repo coding assistant is moving from a single model response toward an
orchestrated foreground implementation workflow. The workflow needs cheap/local
delegated support, deterministic validation, bounded repair policy, and a final
handoff that tells the returning user what still does not pass.

Model claims are not sufficient evidence of completion. Validation must come
from deterministic local checks and be recorded in the run metadata.

## Options Considered

- One supervised repair pass after implementation.
- Multi-pass supervised workflow with local/cheap delegated support.
- Fully autonomous background repair loop.
- Deterministic validation inside the assistant wrapper only.
- Deterministic validation delegated entirely to pre-commit.

## Decision

Use a multi-pass supervised workflow as the default orchestrated direction.
Local or cheaper delegated passes are part of the loop for bounded scrutiny,
focused checks, risk review, test suggestions, and small validation support.
The primary route remains responsible for implementation. Deterministic
validation remains the source of truth for completion.

The default repair-cycle limit is three. The CLI must allow a different value,
including an explicit unbounded cycle setting that still respects the
`--away-minutes` wall-clock budget. When delegation is unavailable or disabled,
the workflow degrades to one supervised repair pass.

The default deterministic validation command is:

```powershell
python -m pytest -q
```

Ruff and Pyright should normally run through the repository's pre-commit
configuration because Ruff has an auto-fix mode and Pyright is already a
pre-push hook. Orchestrated runs may opt into broader validation by passing an
explicit pre-commit command as a validation command.

## Reason

The CLI assistant should behave more like a supervised coding session:
local/cheap delegated agents handle bounded review and validation support, while
the primary route handles implementation, and deterministic checks decide
completion.

Pytest is the right default wrapper validation because it is deterministic,
directly tied to behavior, and does not rewrite files. Ruff and Pyright already
have an established hook boundary, and Ruff's fix behavior makes it better
suited to pre-commit or an explicit validation command than a silent default
wrapper check.

## Consequences

- Orchestrated run metadata must distinguish model execution success from
  deterministic validation success.
- Failed validation must be handed back with command details, blockers, and a
  concrete next action instead of reporting clean completion.
- Repair loops remain bounded by default and configurable per run.
- Removing the repair-cycle cap does not remove the wall-clock budget.
- Pre-commit remains the preferred place for Ruff auto-fix and Pyright unless a
  run explicitly opts into those checks.
