# Decision brief — 5 route-family matcher disagreements (2026-10-23)

**Status:** PROPOSAL ONLY. No mapping, band or catalog change was applied.
`packages/ai_provider/docs/route-upstream-family-mapping.md` and
`packages/ai_provider/docs/model-catalog.md` are unchanged by this brief.

**Prepared:** 2026-10-23 (unattended window). **Owner decision required before any edit.**
**Snapshot:** `artifacts/model-capability-priors-20261022/` (Aider observed 2026-10-22,
SWE-bench observed 2026-10-22). **Checked date used by the matcher:** 2026-10-23.

## Why this brief exists

`propose_route_family` (offline, `packages/ai_provider/src/ai_provider/route_family_matcher.py`)
was accepted as a proposal-only helper. Reproduction against the hand table
(`tests/test_route_family_matcher.py::test_saved_reader_snapshot_reproduction`):

```text
13 / 18 routes agree (confidence AND cited row)
5 disagree: openai/api-gpt-5.1, openai/api-gpt-5-mini,
            requesty/openai/gpt-5.1, requesty/openai/gpt-5-mini,
            openai/codex-gpt-5.5
```

In all five the matcher found a **different source row**, not a looser match:
the hand table matched Aider's flagship `openai/gpt-5` (88.0 `percent_correct`,
`edit=diff; reasoning=high`), while the matcher matched a SWE-bench Verified row
whose model identity is closer to the route's own id.

## How the bands would change

Bands are per source, from fixed cutoffs, and are **never averaged or merged**
(`capability_bands.py`):

- Aider polyglot: `≥80 Frontier`, `≥70 Very strong`, `≥50 Strong`, `≥25 Mediocre`, `≥12 Weak`.
- SWE-bench Verified: `≥75 Frontier`, `≥70 Very strong`, `≥55 Strong`, `≥40 Mediocre`, `≥24 Weak`.

SWE-bench rows are *(model, scaffold)* pairs and are not comparable across rows;
Aider uses one harness. The two columns stand side by side on purpose.

## Per-route analysis

### 1–2. `openai/api-gpt-5.1` and `requesty/openai/gpt-5.1` (same upstream id `gpt-5.1`)

| | Hand table (today) | Matcher proposal |
| --- | --- | --- |
| Row | Aider `openai/gpt-5`, 88.0 `percent_correct`, `edit=diff; reasoning=high`, 2025-08-23 | SWE-bench `gpt 5.1`, **66.0** `percent_resolved`, mini-SWE-agent, 2025-11-20 |
| Confidence | `family` (version gap 5.1 vs 5.0) | `exact` (normalized identity match; no gap) |
| Published band | **Frontier (88)** | **Strong (66)** |

**What is at stake:** the route's only band would move Frontier → Strong, and its
confidence would become `exact`. This is a visible downgrade on a route the
selection prior currently prefers.

**Evidence quality:**

- The Aider row measures a *different version* (5.0, high reasoning, diff edit).
  Its 88.0 is the top published Aider score, so using it for 5.1 is optimistic by
  construction but is a same-task, same-harness comparison.
- The SWE row's identity is the same version, but the score is one
  (model, mini-SWE-agent) pair, not a controlled effort comparison.

**Recommendation: accept the matcher as an *additional* row, do not delete the Aider row.**
Add SWE-bench `gpt 5.1` (66.0 → Strong) and keep Aider `openai/gpt-5` (88.0 →
Frontier) as the family row with its version-gap note; set confidence `exact`
because exact identity now exists for one source. Result: both columns shown, no
number averaged, no evidence discarded.

### 3–4. `openai/api-gpt-5-mini` and `requesty/openai/gpt-5-mini` (same upstream id `gpt-5-mini`)

| | Hand table (today) | Matcher proposal |
| --- | --- | --- |
| Row | Aider `openai/gpt-5` (flagship), 88.0, `edit=diff; reasoning=high` | SWE-bench `gpt 5 mini`, **56.2** `percent_resolved`, mini-SWE-agent, 2026-02-17 (older run 59.8, 2025-08-07) |
| Confidence | `family` (flagship stand-in; mini tier unmeasured) | `exact` (normalized identity match; no gap) |
| Published band | **Frontier (88)** | **Strong (56.2)** |

**What is at stake:** the current Frontier band comes from the *flagship* model,
not from the mini tier. The table already warns that "the mini tier is
unmeasured". A reader choosing a cheap route sees Frontier.

**Evidence quality:** the SWE row is the mini tier itself under one scaffold;
both of its published runs land in Strong (56.2 / 59.8). This is the clearest
substantive defect of the five: the current band substitutes a different size
tier that the doc's own cautions forbid.

**Recommendation: accept the matcher and replace the flagship row for the mini routes.**
Cite SWE-bench `gpt 5 mini` (56.2 → Strong, exact). Dropping the flagship Aider
row removes a band that measures a different model tier. Result: Frontier → Strong
for both mini routes.

### 5. `openai/codex-gpt-5.5`

| | Hand table (today) | Matcher proposal |
| --- | --- | --- |
| Row | Aider `openai/gpt-5`, 88.0, `edit=diff; reasoning=high`, 2025-08-23 | SWE-bench `gpt 5.2`, **72.8** `percent_resolved`, mini-SWE-agent, 2026-02-17 |
| Confidence | `family` (version gap 5.5 vs 5.0) | `family` (version gap 5.5 vs 5.2) |
| Published band | **Frontier (88)** | **Very strong (72.8)** |

**What is at stake:** confidence does not change; only which source supplies the
family row. The matcher's row is version-closer (0.3 vs 0.5) and task-closer
(repo issue resolution rather than polyglot editing), but slightly further from
Frontier.

**Evidence quality:** both are family matches. Version numbers are not
commensurate across sources; Aider carries a controlled reasoning level
(`high`), SWE carries a scaffold. The route is a Codex CLI coding agent, so
SWE-bench is the more representative task, but the Aider row is not wrong.

**Recommendation: add the SWE row as a second column, keep Aider as primary.**
`Very strong (72.8)` becomes visible next to `Frontier (88)`, confidence stays
`family`, and the version gap note names 5.2. This adds information without
silently weakening the current prior.

## Options

**Option A — accept all five matcher proposals uniformly (replace rows).**
- Pros: one consistent rule ("closest published identity wins"), simplest to
  explain and to test; the matcher's own output becomes the table.
- Cons: throws away the Aider evidence for 5.1 and 5.5; converts single-source
  bands into single-source bands from the noisier, scaffold-specific source.
- Consequence: 5.1 → Strong, mini → Strong, 5.5 → Very strong.

**Option B — accept by evidence quality (recommended).**
- 5.1 routes: add SWE exact row, keep Aider family row → SWE Strong (66) appears;
  confidence `exact`.
- mini routes: replace flagship row with SWE exact row → Strong (56.2); no Aider band.
- 5.5: add SWE family row, keep Aider → Very strong (72.8) appears; confidence `family`.
- Pros: fixes the real defect (flagship band on a mini route) while keeping every
  legitimate measurement; matches the doc's "two columns, never one number" design.
- Cons: the table gains per-route variation that a simple "matcher wins" rule
  cannot reproduce, so the matcher test's agreement target needs re-specification
  (e.g. "proposal must be *cited*, not necessarily sole").
- Consequence: mini routes are downgraded; 5.1/5.5 gain a SWE column and keep
  their Aider band.

**Option C — keep the table unchanged, record the rationale.**
- Pros: no published band moves; the current table remains internally consistent
  in preferring one harness for these GPT routes; zero test churn.
- Cons: a known better-supported mini row stays unused and a Frontier band keeps
  describing a model tier nobody measured; future readers must rediscover this brief.
- Consequence: no band change; the matcher test keeps its expected 13/18 result.

## Recommendation

**Option B.** It corrects the one likely-misleading band (mini = flagship
stand-in), keeps the strong Aider evidence where it is genuinely comparable
(same task/harness), and adds the exact/nearer SWE rows where they exist. It does
not average scales or invent a single composite number.

If the owner prefers a single mechanical rule, Option A is defensible, but it
should be paired with an explicit note that the Aider rows for these families
were deliberately dropped despite being the only high-reasoning, diff-edit
measurements.

## Exact edits that Option B would make (NOT applied)

1. `route-upstream-family-mapping.md` mapping table:
   - `openai/api-gpt-5.1`, `requesty/openai/gpt-5.1`: add the SWE `gpt 5.1` row;
     confidence `exact`; gap "Aider row is version 5.0; SWE row is exact identity";
     keep the Aider row in the same cell.
   - `openai/api-gpt-5-mini`, `requesty/openai/gpt-5-mini`: replace the Aider
     flagship citation with SWE `gpt 5 mini` (56.2; note the 59.8 run); confidence
     `exact`; gap "none on identity; scaffold-specific score".
   - `openai/codex-gpt-5.5`: add the SWE `gpt 5.2` row; confidence stays `family`;
     gap "version 5.5 vs 5.2 (SWE) and vs 5.0 (Aider)".
2. `model-catalog.md` per-route band table: add the corresponding SWE cells
   (`Strong (66)`, `Strong (56.2)`, `Very strong (72.8)`); remove the Aider
   `Frontier (88)` cell only for the two mini routes; update the coverage counts
   (Aider 10 → 8, SWE 6 → 11, routes with both 2 → 5) and the explanatory note
   about `api-gpt-5-mini`.
3. `tests/test_route_family_matcher.py`: re-specify "agreement" as *the proposal
   row must be cited in the table cell* rather than *the cited row must be the
   only/primary row*; expected agreements then become 18/18 under Option B.

## Owner question

Which option do you want: **A** (matcher wins uniformly), **B** (recommended:
exact SWE rows added; mini routes replaced), or **C** (no change, rationale
recorded)? If B, confirm that the mini routes may lose their Aider `Frontier`
band, because that is the one published band that actually moves.

## Limitations

- Analysis used only the saved 2026-10-22 snapshots; both leaderboards are stale
  by construction and are selection priors, never acceptance evidence.
- No live provider request or band recomputation was run; band arithmetic is from
  the published cutoffs in `capability_bands.py`.
- The matcher ranks rows by identity/version/size/diff/effort, never by score, so
  its "latest run wins" tie-break for `gpt 5 mini` selects 56.2 over the older
  59.8; either keeps the same band.
