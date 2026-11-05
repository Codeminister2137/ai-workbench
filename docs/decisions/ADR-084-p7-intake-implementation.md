# ADR-084: P7 client intake implemented as validate → review → approve-to-plan

Status: Accepted direction (implementation), 2026-11-05. The P7 proposal's
owner questions Q1/Q2/Q4/Q5/Q7 remain open; Q3/Q6 are resolved below as
implementation defaults, reversible on owner correction.

## Decision and intent

Implement `docs/plans/p7-project-file-format-proposal.md` v1.0.0 as a
dashboard Intake flow (`apps/workbench_dashboard/p7_intake.py`): intake files
in gitignored `p7-projects/` validate against the closed schema plus all 13
actionability rules (rule 10 untestable-success and rule 13 PII stay
warnings, per the proposal), list with valid/draft verdicts, and the owner
approves valid files into `proposed` dashboard plans. Approval moves the file
to `p7-projects/approved/` (post-approval immutability). Nothing auto-executes
and no credits are spent.

## Resolved defaults (reversible)

- Q3 (intake location): files on disk under `p7-projects/`; the human
  capture flow is dropping a file there. API/email intake is not built.
- Q6 (approval UX): manual approve click opens the draft plan — no automatic
  project creation, which answers the accidental-spend concern by construction.
- Client PII (`client_contact`) never leaves the PC: the intake dir is
  gitignored alongside the private library, and secrets/PII patterns are
  validation failures/warnings per the proposal.

## Consequences

- The client-file → project-base leg of the owner's vision works up to the
  draft plan; plan authoring from chat and plan-step execution remain.
- Follow-ups: owner answers to Q1/Q2/Q4/Q5/Q7 (filed to inbox 2026-11-05),
  chatbot producer (out of scope), intake expiry sweeper (validation flags
  expiry; no automatic purge yet — Q5 pending).
