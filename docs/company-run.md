# Company run: intake to invoice inputs (G12, 2026-11-09)

One end-to-end checklist for running a client project through
ai-workbench. Pricing/line details inherit the private offering
draft; this page holds structure + commands only.

## 1. Intake

1. Client answers the guided chatbot (form-first v1; bot later).
2. Brief lands as a project file under `p7-projects/` (gitignored:
   client PII never committed).
3. Validate: dashboard → project → intake-approve button runs the
   validator (closed schema, secrets-reject, PII-flag, PL+EN v1).
4. Owner approves a valid file → becomes a `proposed` plan.

## 2. Plan

1. Dashboard Plans → open the proposed plan, phase checklist.
2. Scoping questions go back via inbox (owner) or discovery call.
3. Owner approves the plan in a review window.

## 3. Execute

Options, narrowest first:

- Attended: `.\scripts\repo-assistant.ps1 "task" --execute`
  (read the script help for modes; approvals stay interactive).
- Unattended loop: owner-scoped window with deadline, heartbeat
  mail, and sleep closeout (see `docs/workflow.md`).
- Scheduled: NL proposal → inbox order → (slice 2 pending owner
  choice of auto-run vs explicit start).

## 4. Verify

Per slice, before any push:

- Focused pytest for touched files.
- `.venv\Scripts\python.exe scripts\run-tests.py full` for the gate.
- `ruff check`, `ruff format --check`, `pyright` (bare, as the hook).
- Push: green gate first; `--no-verify` retry only after green;
  verify `rev-list 0` + `ls-remote` match (transport is flaky).

## 5. Report

- Run `report` field + inbox close with resolution (final-report
  artifact awaits the audience decision, brief a96f576b).
- Merge under the tier policy ([ADR-087](decisions/ADR-087-tiered-merge-gates-e2e-promotion.md)):
  Tier 1 auto-merges on green, Tier 2 merges to `develop` on green agent gates,
  Tier 3 still needs explicit owner approval per merge.

## 6. Invoice inputs

- Accepted SOW/quote → draft invoice (auto-invoice idea: draft
  only, founder reviews; KSeF-first; accountant-verified
  template before first real use).

## Troubleshooting subset

- Ollama down: `ollama list` must answer; restart the Ollama app.
- Allowance exhausted: dashboard Home spend panel shows buckets;
  billable calls are denied by default until grants exist.
- Token expiry (Meta/grants): re-check provider docs
  `packages/ai_provider/docs/source-state.md`, refresh the grant.
- Push transport drops: retry `--no-verify` only after a green
  gate; always verify with `ls-remote`.
- Dashboard unreachable: `curl http://127.0.0.1:8766/api/status`.
