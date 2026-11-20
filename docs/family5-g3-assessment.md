# Family-5 G3: gate and CI decision brief

Research checked 2026-11-20. Status: research complete; adoption requires owner
choice. Source: inbox `951734be035d42dab81c08132cf1c9e7`, whose answer requested
further investigation, internet evidence and fuller explanation, not A/B/C adoption.

## What the repository establishes

The pre-push configuration runs Pyright, skill-registry and style-token checks,
then the full offline test runner. Affected selection is a standalone shadow
prototype comparing committed base-to-HEAD paths; it neither runs tests nor
accounts for uncommitted changes. Its conservative fallbacks preserve consumers
but can select the entire suite, limiting savings. Unknown paths select full.

The saved observations in [test workflow](test-workflow.md#family-5-follow-up-2026-11-20-adoption-pending)
are 407.8s serial and 86.3s eight-worker workspace execution. Both were red;
workspace pass counts differ by five. The older roughly 652s total also included
135 scratch worktrees. These are historical reports, not measurements reproduced
by this investigation or comparable green acceptance runs. This worktree does
not contain those trial logs. No cause for the count difference is established.

The historical selection check includes three sampled failure modules plus one
new regression module, using fixing diffs and today's ownership manifest.
That is inclusion evidence with selection bias, not measured failure recall.
An edited test naturally helps select its own group. Source-only changes and
cross-component effects are the harder cases that need prospective evidence.

No private `docs/plans/` directory is present in this worktree. Inspection of the
main checkout's private `repo-health-scan.md` confirms investigation is authorized,
adoption is pending, and all tests must run before merge. Its historical "main"
wording must be read with the current `develop` integration policy, not as
permission to skip checks until promotion to `master`. The private
`evening-loop-20261120.md` records a 33-minute contended gate and gate/worker
contention as an additional cost signal, not an isolated suite benchmark.
Other application plans do not determine G3. ADR-087's tiered merge rules do not
by themselves configure a remote required full-suite check.

## What external evidence adds

- [pytest-xdist limitations](https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html)
  require workers to collect matching test counts and order. Its
  [distribution modes](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
  change scheduling. Parallel execution therefore needs collection equivalence
  and resource-isolation evidence; worker count alone is not a correctness proof.
  This does not explain the saved serial/parallel discrepancy.
- [GitHub-hosted runners](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners)
  ordinarily provide fresh VMs. Moving these tests there requires an explicit
  install/asset contract; ignored owner files must not be uploaded simply to
  make tests pass. Tests of local private assets need fixtures or a separately
  defined local check. Windows process and filesystem behavior warrants a
  Windows job before claiming equivalence to the development environment.
- [GitHub billing](https://docs.github.com/en/actions/concepts/billing-and-usage)
  makes standard hosted runners free for public repositories; private repositories
  have plan-dependent allowances and potential overage. Repository visibility,
  account allowance and spending settings have not been checked here. No claim
  of zero cost or approved spending follows from public pricing documentation.
- [GitHub security guidance](https://docs.github.com/en/actions/reference/security/secure-use)
  warns that self-hosted runners can remain compromised by workflow code.
  Running one on the owner's PC retains PC contention and exposes its environment;
  an isolated disposable runner is a materially different setup.
- [Workflow path filters](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
  can leave required checks pending when an entire workflow is skipped. A future
  selection design needs a reliable full-suite status for the exact merge commit,
  rather than assuming path filters or a locally passing hook enforce merging.
- [Jenkins administration](https://www.jenkins.io/doc/book/managing/) includes
  controller, plugin, security and node administration. It offers control but
  introduces ongoing operational work; no unmet Jenkins-specific need is shown.

## Decision and trade-offs

These choices address different costs: selection reduces repeated execution;
hosted CI moves execution off the PC and adds remote reports. Neither guarantees
a shorter time to a verified merge. Parallelization is a separate optimization.

| Choice | Benefit | Cost and risk |
| --- | --- | --- |
| A: Retain serial full gates; collect prospective shadow evidence | Preserves existing coverage and access boundaries; reversible, no service setup | Repeated full-suite cost remains; collecting comparisons takes work |
| B: Affected pre-push tests plus mandatory full merge gate | Faster push feedback when selection is narrow; complete merge coverage if enforced | Selection can omit consumers; conservative fallback may erase savings; full checks still cost time; exact merge enforcement must be designed |
| C: Authorize a GitHub Actions design spike | Can investigate off-PC execution, reproducibility and independent reports | Requires clean-checkout assets/dependencies and runner/data choices; setup latency, possible billing and maintenance; a design spike is not runner deployment |

Technical recommendation: **A now**. The evidence does not justify weakening the
existing gate. Before revisiting B, compare shadow selections with serial full
results on the same prospective revisions and environment; retain node IDs,
failure sets, selected fraction and wall time, including source-only and shared
consumer changes. A missed failure or unavailable comparison is not a success.
No numerical adoption threshold has been owner-approved; a small all-green sample
cannot establish recall. Fix existing red results and reconcile collection before
assessing parallelization. These are proposed next steps, not completed trials.

If the owner's primary problem is PC contention or independent merge enforcement,
**C can be preferable to selection research**: first design a secret-free,
clean-checkout Windows check with read-only permissions and minimal reports,
then obtain approval for its runner, transmitted data and spending boundary.
Do not install a runner on the owner's everyday PC as an implicit compromise.
Jenkins is not recommended without a requirement that outweighs its maintenance.

Owner question: choose **A**, **B**, or **C**, and say which constraint matters most:
push waiting time, PC contention, or independent merge assurance. B additionally
needs the full-suite merge enforcement agreed; C needs runner/data boundaries
before setup. Existing serial full gates remain in effect pending that choice.

## Exact gate implications and verification

The current pre-commit stage runs Ruff lint with fixes and Ruff formatting.
Pre-push runs Pyright, skill-registry consistency, style-token consistency and
the full offline test runner, in that order. A retains that membership. Under
the proposed B, only the pre-push test invocation would become affected selection;
the other checks would remain, and the full offline runner would be required
before merging to `develop`. A nightly run alone cannot satisfy that invariant.
C authorizes design work only; it does not move or remove any current gate.

For a hosted design, the explicit data inventory is checked-out repository code,
dependency downloads, test output and any retained reports. Private owner assets,
credentials and live-provider inference are outside the proposed initial check.
GPU execution has no demonstrated need in this offline gate; model-quality trials
are a separate acceptance category. Estimate cost only after choosing visibility,
runner OS, job duration/frequency and retention, using current account allowances.

This continuation independently ran `pytest tests/test_test_suites.py -q` using
the main checkout's existing virtualenv: **19 passed**. That verifies the covered
runner/selection contracts, not full-suite health or prospective failure recall.
Official source pages above were fetched again during this continuation. The
existing draft and workflow link were present at initial inspection; this section
is the continuation's addition. No full benchmark was repeated for this research
closeout. Adoption remains **INCOMPLETE**: obtain the owner's A/B/C choice and
driving constraint before implementing a gate or runner change.
