# ADR-046 — Explicit Interpreter for Default Validation

**Status:** Accepted
**Date:** 2026-10-06

## Context

The repo assistant's default pytest validation used the executable running the
assistant process. `python_runtime` could report a workspace `.venv`, but there
was no way to choose that interpreter for validation without spelling a custom
validation command. Automatically selecting a detected environment could
silently run tests under a stale or unintended interpreter.

## Options considered

- **Keep the current behavior.** This avoids a public CLI change, but selecting
  another interpreter requires a custom validation command.
- **Add an explicit per-run interpreter override.** This makes selection
  predictable and advances IDE independence, but adds a public CLI option and
  must preserve custom validation commands.
- **Automatically prefer the workspace `.venv`.** This is convenient for common
  projects, but changes the default implicitly and does not define precedence
  for conda or other environments.

## Decision

Add `--validation-python PYTHON` for the default pytest validation command. If
omitted, the current repo-assistant process executable remains the default.
When the caller supplies one or more `--validation-command` values, they remain
unchanged and `--validation-python` does not rewrite them. Research profiles
that do not select the default pytest command do not use this option.

## Rationale

The owner selected explicit per-run interpreter choice for predictable
selection without silently guessing, and because it advances IDE independence.
This preserves existing defaults and custom command behavior while allowing the
caller to select the project interpreter directly.

## Consequences

- Default validation receipts continue to record the executable actually used.
- The plan output reports the effective default validation interpreter.
- This is an explicit executable selection, not environment discovery or
  interpreter installation.
- The option does not change provider/model routing or execute workspace code
  beyond the already selected validation command.
