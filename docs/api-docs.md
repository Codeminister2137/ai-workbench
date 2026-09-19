# API Documentation Workflow

The repository uses docstrings and type hints as the source for generated Python
API documentation.

## Tool

Use `pdoc` for the first API documentation workflow. It is a lightweight dev
dependency that can generate browsable HTML from the package module hierarchy
without requiring a larger documentation framework.

Sphinx remains a future option if the project needs a larger narrative
documentation site, intersphinx links, custom extensions, or multiple output
formats.

## Generate API Docs

From the repository root:

```powershell
python -m uv run pdoc -o docs\api-reference ai_provider ai_orchestrator
```

The generated `docs/api-reference/` directory is ignored by Git. Commit source
docstrings and narrative Markdown, not generated HTML.

## Docstring Scope

Prefer concise PEP 257-style docstrings for:

- public modules;
- exported classes, protocols, and enums;
- public functions and methods that form package or application boundaries;
- provider adapters, orchestration entry points, and privacy/security-sensitive
  behavior.

Usually skip docstrings for:

- tiny private helpers where the name and type hints are enough;
- tests whose names already explain behavior;
- boilerplate that would only repeat the symbol name.

Do not enable strict docstring linting until the current public API has a clean
baseline.
