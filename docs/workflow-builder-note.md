# Workflow builder — decomposition note (loop9, idea 9b22ac09)

Owner want: a graphic way to build workflows (e.g., a research loop
with extra scrutiny passes), reusing agent skills/runs in full or parts.

## Decomposition (build bottom-up; UI last)

1. **Skill registry (first, unlocks everything).** A machine-readable
   list of reusable skills/runs with inputs/outputs/cost. Half exists:
   tool classes + run records + receipts. Missing: one registry file
   and a "reused by" link. Slice: `docs/skills-registry.md` generated
   from tool definitions + run records. No new runtime.
2. **Workflow spec (second).** A small TOML/JSON schema: ordered steps
   referencing registry entries + per-step scrutiny passes. Validated
   by a stdlib checker. No executor yet.
3. **Runner (third).** Executes a spec: calls tools/runs in order,
   records receipts. Reuses delegation + run tracking. Approval gates
   stay per-step (no blanket pre-approval).
4. **Graphic builder (last).** Only after 1–3 prove the model: a
   dashboard page that edits the spec visually (list/columns, not
   free canvas — stdlib UI constraint).

## Why this order

Steps 1–2 are useful without any UI (auditable, testable specs).
Step 4 without 1–3 is a drawing tool that builds nothing. Each step
is independently shippable; stop after any of them with value kept.

## Proposed first slice (when approved)

Skill registry generator + checker (~2h). No runtime, no UI, no new
dependencies.
