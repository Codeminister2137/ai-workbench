# Unified visual style — translation brief (loop9, idea cc3857e9)

Goal: one professional look across personal projects. Constraint: our
stack is Python stdlib UIs (no npm, no Percy, no build step).

## Proposal (small, reversible)

1. **`shared/style-tokens.css`** — one file with CSS custom properties
   only: `--wb-bg`, `--wb-fg`, `--wb-muted`, `--wb-accent`,
   `--wb-danger`, `--wb-radius`, `--wb-font`. No components, no layout.
2. Each project links the tokens file and uses `var(--wb-*)` instead of
   literals. Existing per-project CSS stays; only literals migrate.
3. **`scripts/check_style_tokens.py`** — stdlib checker: fails when a
   project's CSS uses color/radius/font literals covered by a token.
   Runs in the existing gate like ruff. No screenshots, no Percy.

## Non-goals

No shared component library, no JS framework, no visual-regression
screenshots. Tokens + a literal linter get 80% of "looks professional"
for ~2h of work.

## First slice (when approved)

Add the tokens file with the dashboard's current values, migrate the
dashboard CSS, add the checker + gate entry. Other projects adopt by
copying two lines.
