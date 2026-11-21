# Repo health scan — 2026-11-21

Run: `dc86d9770a9d42f2bc889fa49756c5c8`. Inspected base: `67bc53f`.
Status: **INCOMPLETE** for the complete deep-scan plan; cheap scan and filing
slice executed. No production fixes, gate changes, CI deployment or sweep wiring.

The private authoritative plan was read from the main checkout's
`docs/plans/repo-health-scan.md`; it is absent in this isolated worktree.
Existing family receipts were treated as historical observations and rerun,
never overwritten. Application plans do not determine these scan criteria.

## Findings and filed AGENT tasks

| Finding | Evidence | Task id |
| --- | --- | --- |
| Full offline gate requires absent local documentation assets | `test_document_status.py` requires `docs/api-reference/` and private `docs/plans/*.md`; both fail in this worktree | `6a43eebb9c044459b7b964aefeeb5a8d` |
| Saved clone wrapper produces false-clean results | Wrapper parses human stdout as JSON, swallows ValueError, and records zero; direct relative-path scanner finds 21 groups | `5756732b6cf646a79890ec0ed36a0a06` |
| Deep and gating evidence remains incomplete | No coverage/deletion/mutation trial or prospective failure-recall measurement established in this slice | `c06a952e560c46c2bc9113626ba590d2` |

All three tasks were created through DashboardStores in the main checkout and
read back as open `type=task`, `assignee=agent`. No owner task was created.
The deep-evidence task records remaining work, not a verified production defect.

## Fresh scan receipts

Receipts and logs are in this run worktree's `.tmp/health-dc86d977/`.
The existing four AST detectors ran using the configured main-checkout venv
Python, with `--root .` and separate output paths. Detector family numbers differ
from plan ordering: detector 2 is dead code; detector 3 is smells.

| Family | Cheap detector | Result and interpretation |
| --- | --- | --- |
| Folded errors | AST silent/mixed exception-handler body classification | 372 signals across 695 files; not 372 defects; residual triage remains |
| Smells | LOC/nesting thresholds, coarse import cycles, normalized AST clones | 175 long/deep functions, 11 coarse cycles across 335 files; direct clone scan: 21 groups across 8,527 functions |
| Dead code | Definition/reference census | 17 candidates, all framework hooks or translation contract members; no new verified deletion target; zero coarse orphan signals is not proof of no orphans |
| Robustness | Assert-free tests, unnamed production modules, timing patterns | 357 test files: 4 assert-free, 75 unnamed modules, 123 timing signals; new assert-free UI test delegates assertions to Node; no assertion defect inferred |
| Gate cost | Full offline runner with per-case durations; historical shadow selection | Workspace 70.7s, Council 4.2s, job-search 2.1s; full run red |

Cheap scans pass as executions when a parseable receipt is produced; candidate
signals require code/consumer verification before becoming defect tasks.
The saved smell wrapper's clone result is **invalid**, not a passing zero.
`find-duplication.py --json -` writes a literal file named `-`; stdout is human
text. Its absolute-path traversal also excludes paths beneath hidden ancestors
such as `.tmp`. A direct relative-root scan bypassed both problems. An untracked
`-` existed at first inspection; its original creator is not established.
Preserve that file and the original receipts.

## Verify-first reconciliation

- F1: process probe now distinguishes failure with None; reaper skips that tick;
  regression tests cover failed and empty-success probes.
- F2: auto-check ValueError now stamps failure evidence and time.
- F3/F5: vendor construction/read failures emit type/reason diagnostics;
  credential tests cover duplicate, empty and unreadable synthetic stores.
- F4: model-list failure returns None and callers emit skip diagnostics;
  transport/invalid-JSON regression tests exist.
- D1–D5: the five previously named definitions are absent from current source;
  do not recreate removal tasks or infer that other public APIs are dead.
- T1: direct credential-path adversarial tests exist. T2: Council README now
  specifies explicit-start weekly maintenance cadence and bounded local eval.
- G1: repair fingerprints exclude scratch `.tmp`; current full run passed its
  covered repair contracts. S1: request phase helpers exist; `_execute_request`
  is 705 lines, versus the historical 1,291. Size alone does not justify another
  refactor. S2: acceptance storage and protocol constants have been separated;
  the approved neutral-import exception has a layering regression test.

Existing original finding tasks were already closed at inspection; no redundant
closures or duplicate original-finding tasks were issued. These observations
establish present source state and covered tests, not historical deletion trials.

## Validation and gating limits

Executed `scripts/run-tests.py full -- -q --durations=20` with the venv Python.
Workspace: **5,643 passed, 23 skipped, 2 failed**; Council: **82 passed**;
job-search: **249 passed**. Total: **5,974 passed, 23 skipped, 2 failed**.
Both failures originate in explicit local-asset assertions in
`tests/test_document_status.py`, matching absent paths. No retry or fix was made.
Slowest workspace case: sleep cancellation identity test, 5.38s. These measurements
use default parallel workers in this worktree and are not a controlled comparison
with historical serial runs or the populated main checkout.

Historical first-parent comparisons for `21f349a`, `8f57706`, and `74a4ced`
select their recorded failure-module groups. Initial `diff-tree` sampling omitted
merge-commit paths; the corrected `git diff REV^ REV` receipt is
`selection-first-parent.json`, alongside the preserved initial `selection.json`.
This is inclusion evidence, not replayed failures or prospective recall.

Existing `docs/family5-g3-assessment.md` already provides the CI design comparison.
Official research was refreshed: [GitHub billing](https://docs.github.com/en/actions/concepts/billing-and-usage),
[Windows runner choices](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job),
and [Jenkins Windows service requirements](https://www.jenkins.io/doc/book/installing/windows/).
No account allowance or spending setting was inspected. Hosted CI adds independent
off-PC reports but requires an explicit runner/data/cost boundary and reproducible
checkout; Jenkins adds service/controller maintenance. Recommendation remains to
retain existing full gates while gathering prospective selection evidence and
resolving the clean-checkout contract. No adoption is claimed or requested by this
findings-only slice.

Next action: execute the filed deep-evidence task with fresh finite bounds;
complete when residual triage, coverage/deletion trials, prospective recall,
exact gate-membership proposal and CI design evidence have receipts. GPU/live
model evaluations and deletion trials were not performed here. Production fixes
belong to later slices as requested.
