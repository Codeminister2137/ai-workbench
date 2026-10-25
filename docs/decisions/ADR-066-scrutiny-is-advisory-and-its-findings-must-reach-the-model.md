# ADR-066 — Scrutiny is advisory; its findings must reach the model

**Status:** Accepted (advisory policy); revision-loop extension design
confirmed by owner 2026-10-23 (Option B minimal loop; Option B
`format_issues` rendering)

**Date:** 2026-10-23

**Amends:** ADR-062 (optional completion evidence) and the acceptance boundary
set by the repo-assistant acceptance criteria. This ADR changes *when* scrutiny
may block an outcome, not what counts as evidence.

## Context

Orchestrated runs end with a `scrutiny` stage: a local review model reads the
observed implementation evidence and emits a report with a `VERDICT`, a score,
`ISSUES`, a `RECOMMENDED_NEXT_ACTION` and a `REVISED_RESPONSE`.

Two problems surfaced in the 2026-10-23 Option A baseline run and the
subsequent review:

1. **It falsely blocks.** A non-`pass` verdict sets
   `completed_with_scrutiny_findings` / `completed_with_scrutiny_errors`, which
   forces `final_answer_available = false` and relegates the agent's work to an
   "unaccepted draft" (`ai_provider.closeout`). The owner reports this blocks
   too much in practice.
2. **The outcome can be decided by a formatting failure rather than a quality
   judgement.** `parse_response_scrutiny_report` requires all six headings in
   order and raises `ValueError` on a missing heading. A local model that
   produces a sound review but omits or mis-formats one heading produces a
   *parse failure*, and that failure — not the review — is what the run
   records. The gate is a hard requirement on a local model emitting an exact
   6-heading format.

## Investigation

Reading the code establishes that scrutiny is **terminal, not a feedback
loop** — which is the opposite of the intended design.

- `repo_coding_assistant.py` calls `_run_orchestrated_repair_loop` (line 2134)
  and *then* `_run_orchestrated_scrutiny` (line 2185), followed directly by
  `record_final_handoff_stage` (line 2197). Nothing runs after scrutiny.
- `repair_workflow.py` contains **no reference to scrutiny at all**, so the
  repair stage cannot consume scrutiny findings even in principle.
- The report's `issues`, `recommended_next_action` and `revised_response` are
  written into stage details and printed. `closeout.py` renders
  `revised_response` under the heading *"Reviewer-proposed revision (not
  applied or independently verified)"*. It is never delivered to the primary
  model and never becomes the final answer.

**The intended mechanism already exists — for the research profile only.**
`ai_provider.research_refinement.run_research_refinement` implements exactly
the loop the owner describes: it runs `scrutiny`, reads the resulting `issues`
and `next_action` from the stage record, feeds them back to the primary agent
as *"Reviewer advice (untrusted suggestions...)"*, runs a repair attempt,
re-validates, and re-scrutinizes — bounded by a review-time reserve, the
configured `max_repair_cycles`, and a repeated-no-progress fingerprint that
stops after two consecutive no-change attempts. In
`repo_coding_assistant.py` this path is only taken when
`args.tool_profile == "research"` (line 2166); the coding profile takes the
`else` branch (line 2184) and gets a single terminal scrutiny.

So the feedback design is not a greenfield question. It is a bounded extension
of a pattern already implemented, tested and guarded in this repository.

## Decision

1. **Scrutiny is advisory by default.** A non-`pass` verdict records findings,
   risks and a `next_action`, but does not by itself decide that the work is
   unaccepted.
2. **A hard requirement remains available as an explicit option.** The default
   changes; the gate is not deleted. Turning scrutiny into a blocking
   requirement is a configuration choice to be implemented, not the default.
3. **A parse failure must not stand in for a quality verdict.** When the review
   model fails to produce the required report shape, that is recorded as a
   *review failure* with its reason, distinct from a review that reached a
   non-`pass` verdict. The distinction must be visible in the stage record and
   the closeout.
4. **Scrutiny findings must reach the model.** The owner's intended design is a
   corrective loop, not a terminal judgement: the primary model is prompted
   with the reviewer's findings and gets a bounded chance to fix its mistakes.
   The research profile's refinement loop is the reference implementation to
   extend to the coding profile.

## Owner-confirmed design (2026-10-23)

Two implementation-shape decisions were put to the owner as briefs and decided:

**Decision 1 — revision loop shape: Option B (minimal loop).** Implement the
minimal coding scrutiny→repair loop: one extra scrutiny-fed repair pass gated
on the existing `--max-repair-cycles`, reusing the research profile's cycle
cap and no-progress stop. The full `research_refinement` guard set (review-time
reserve, repeated-no-progress fingerprint) is *deferred* until live signal
shows it is needed. Rationale: smallest reviewable slice that establishes the
loop; the guards can be ported later without changing the loop's shape.

**Decision 2 — `format_issues` rendering: Option B (non-empty on `pass`).**
Render the `format_issues` list in the closeout only when it is non-empty on a
`pass` verdict. On a non-`pass` verdict the existing rendering is unchanged.
Rationale: a clean pass should not surface an empty section; a pass that still
carries format issues should surface them so the owner can see the review's
residual caveats.

## Consequences

- The three findings above become work items: (a) soften the format gate so a
  malformed review is a *review failure*, never a silent quality verdict;
  (b) make the advisory/blocked choice configurable; (c) extend the bounded
  refinement loop to the coding profile, reusing the research profile's
  budget reserve, cycle cap and no-progress stop.
- The published closeout wording ("not accepted completion") must follow the
  advisory default rather than being unconditional.
- A run where scrutiny found real problems and the model fixed them is a
  *successful* run, not a blocked one. The refinement attempts are the
  evidence.
- A malformed review is still a real signal — it is just a signal about the
  *reviewer*, and must not be discarded or conflated with the candidate's
  quality.
- Nothing here changes what counts as independent verification. Advisory
  means "does not block by itself", not "unreviewed work is accepted".

## Implementation corrections — 2026-10-25

A failed scrutiny repair may already have changed files. Earlier validation and
review then describe an older state, so the retained report is a draft and has no
accepted outcome preview until current checks/review exist. Earlier validation
receipts remain preserved as history; current validation is marked not run. A
failed attempt with no observed changes retains the existing advisory policy.
This qualifies missing current evidence, not the reviewer's non-pass judgement.

Recent tool observations now have budget priority while selected receipts remain
in execution order. Successful edits are visible and long excerpts retain both
head and terminal summary, explicitly marking omitted middle text. This fixes a
demonstrated omission of later passing tests/diffs/status without increasing the
evidence budget or claiming a reviewer will interpret it correctly. No new repair
allowance, automatic model/billing change or retrospective trial promotion.
