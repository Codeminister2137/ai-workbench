# ADR-019 - API Documentation With pdoc And Targeted Docstrings

**Status:** Accepted

**Date:** 2026-09-19

## Context

The repository is intended to become portfolio-quality and publishable. Public
provider and orchestrator APIs should be understandable from source, and future
generated documentation should be able to use Python docstrings as its source.

The current codebase has useful type hints and README-level documentation, but
many public modules, classes, and functions do not yet have docstrings. Adding
strict docstring linting immediately would create broad churn and force low-value
boilerplate before the public API surface has a clean baseline.

## Options Considered

### Targeted Docstrings Only

Add concise PEP 257-style docstrings to public modules, exported contracts,
provider adapters, orchestration entry points, and application boundary classes.

This improves source readability without adding tooling, but it does not provide
a generated API documentation workflow.

### Add pdoc And Targeted Docstrings

Add `pdoc` as a lightweight dev dependency, document the generation command, and
begin with targeted docstrings instead of a repository-wide rewrite.

This creates a publishable API documentation path while keeping setup and
maintenance cost low.

### Add Sphinx Now

Sphinx can support a larger documentation site, cross-project references,
extensions, and multiple output formats.

It is more powerful, but it is heavier than the repository currently needs.

### Enable Strict Docstring Linting Now

Ruff can enforce pydocstyle-compatible docstring rules.

This would make gaps visible, but it would currently create noisy failures and
encourage boilerplate docstrings before the intended baseline is in place.

## Decision

Use `pdoc` as the initial generated Python API documentation tool and add
targeted PEP 257-style docstrings to high-value public surfaces.

Do not enable strict docstring linting yet.

Generated HTML output belongs in `docs/api-reference/` and is ignored by Git.
Commit source docstrings and narrative Markdown, not generated output.

## Rationale

The owner wants docstrings because they improve source readability, support
future generated documentation, and make the repository stronger as a portfolio
project.

`pdoc` is a good first fit because it is lightweight, type-hint friendly, and can
generate useful API documentation without introducing a larger documentation
framework. Sphinx remains available later if the project grows into a broader
documentation site.

Targeted docstrings control maintenance and token cost by documenting important
contracts first instead of rewriting every small helper.

## Consequences

Public package APIs should receive useful docstrings as they are added or
modified.

Future documentation work can generate local API docs with:

```powershell
python -m uv run pdoc -o docs\api-reference ai_provider ai_orchestrator
```

Strict docstring linting remains deferred until the public API has a clean
baseline and the expected level of enforcement is clear.

## Related Decisions

- `docs/decisions.md` ADR-013 - Repository Layout And Workspace
- `docs/decisions.md` ADR-017 - Dependency Selection Balances Simplicity And Maintenance Cost

## Related Projects / Documents

- `docs/api-docs.md`
- `packages/ai_provider/`
- `packages/ai_orchestrator/`
