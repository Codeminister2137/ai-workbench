# ADR-087: Tiered merge gates with use-based promotion to master

Status: Accepted by owner, 2026-11-14 (chat; per-merge approval of every
merge to develop was theater — the owner approves without reading, and
for AI-driven development the only feasible review is using the product).

## Problem

With agentic development producing most diffs, per-merge approval gates
on `develop` do not function as review: the owner cannot read thousands
of lines, so approvals became automatic. Meanwhile `master` had no
meaningful promotion rule. Industry practice (DX Heroes' four gates,
Ennen's tier policy, Sonar's agentic pipelines) converges on: tiered
autonomy by risk, plan approval before code, agent never merges its own
unreviewed work, and approval sized to blast radius.

## Decision

Three tiers, plus a use-based promotion gate:

- **Tier 1 — agent merges on green:** docs, tests, formatting, dependency
  bumps with passing CI, internal tooling. Rule (Ennen): if CI cannot
  tell whether the change is safe, it is not Tier 1. No owner approval;
  briefs optional, batch-reported.
- **Tier 2 — agent drafts, owner uses, then promotes:** features and
  behavior changes merge to `develop` after green agent gates (tests,
  lint, typecheck, scoped agent review). `develop` auto-deploys to the
  served dashboard, which the owner uses daily. Promotion
  `develop` → `master` requires a passed per-behavior E2E checklist
  (see below). `master` is the stable, portfolio-facing line.
- **Tier 3 — explicit pre-merge approval stays:** auth, secrets,
  credentials, money/billing, data deletion/migration, architecture
  changes, external data routing. Unchanged: owner reads and approves
  before merge.
- **Plan approval before code** for features is unchanged (existing
  decision rules): new behavior needs an approved plan/slice first.

## E2E promotion checklist

Each promotion generates per-behavior checklist items from the merge
diff plus the touched goal/plan docs. Items auto-pass ONLY by linking
a prior E2E report for the same behavior on an ancestor commit, and
only with an attached no-diff proof for that behavior's code — because
checklist generation is diff-scoped, ancestor matches arise for
regression-scope (neighbor/shared-dependency) items. Every
ancestor-approval is visibly marked as such with a warning ("passed on
<commit>, code untouched since — not re-tested"), never silently green.
Unmatched items become one E2E task for the owner with per-item
pass/fail/notes inputs; submitting auto-builds the report. A failed E2E
blocks only its own merge's promotion, never the whole line.

Manual-testing methodology follows: the owner spends time testing and
noting observations; report assembly, evidence linking and promotion
state are automated.

## Consequences

- `AGENTS.md` Git rule "merging to develop needs explicit owner approval
  per merge" is superseded by this tier policy (this ADR + inbox briefs
  for Tier 3 and promotions).
- `master` gains a real meaning: every commit on it passed E2E review.
  A backlog exists: current `master` predates the policy (grandfathered;
  first E2E promotion under this policy starts the guarantee).
- The agent must classify every change into a tier in its merge brief;
  misclassification toward lower tiers is itself a review failure.
- Rejected alternative: keep per-merge approval for everything (proven
  theater); reviewer-assigned PRs (no second human exists).
