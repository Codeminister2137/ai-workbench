# Clone scan centralization ? 6dd14173

Owner decision: **Approve centralization**, source inbox item
`6dd14173bac94765b3a429a5da49584a` (2026-11-22).
Implementation run: `f50ef99f3df24f19a5d2024583438066`.

## Resolution

Centralized the dashboard UI tests' identical Node discovery, subprocess execution
and exit-status assertion in `_run_node_driver`; 25 existing invocations now use
it. Specialized invocations retain their existing arguments. Every JavaScript
assertion driver was compared through Python AST constants against HEAD and is
unchanged.

Extracted `_check_t1_namespace` for the identical T1/T1b held-edge checks.
T1 still uses its original `_grade` path; T1b retains its separate extraction
and computational builtin policy. No dependency or public contract changes.

## Proving checks

- Pytest: dashboard UI, route evaluation, execution sandbox, scheduled clone scan:
  **208 passed**, 10.74 seconds.
- Ruff check and format check: passed on both changed Python files.
- Targeted Pyright: 0 errors, 0 warnings; configuration reported the worktree
  `.venv` absent (checks used the main checkout's existing Python environment).
- `git diff --check`: passed.
- Scanner on the affected files: all three original signatures
  `069ec6cc6efd8280`, `1115ad0276653c34`, `bae369e53d9cc181` absent.

The scanner still finds shape-equivalent test wrappers because normalization
replaces distinct JavaScript strings with the same constant. These represent
separate behavioral assertions, not remaining duplicated execution mechanics;
no assertions were merged or discarded. The scheduled scan baseline was not
rewritten. Full repository tests and integration into develop are outside this
worktree closeout.
