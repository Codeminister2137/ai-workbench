---
name: python-env
description: Place Python environments with the project, never in scratch or system interpreters. Use when creating a virtualenv, choosing an installer, or writing run instructions.
---

# Python environment placement

The environment belongs with the project. Create it inside the
project directory (`.venv`) or let the project manager own it.
Never in a scratch directory, never by forcing an install into
the system interpreter.

Use the shared `read_file`, `find_files` and `run_command`
operations only to inspect the project's declared Python setup
and run its documented environment commands. This skill provides
instructions, not authorization or tools.

Prefer the project's own entry points (documented setup scripts,
lockfiles, test runners) over inventing install steps. When run
instructions are needed, name the exact commands and the
directory they run in. Do not upgrade, pin, or add packages as a
side effect of setting up the environment; dependency changes
are a separate decision.
