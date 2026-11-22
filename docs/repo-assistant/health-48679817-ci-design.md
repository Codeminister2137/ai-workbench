# Clean-checkout CI design spike (not deployed)

Run `4867981737e24307ac79391b04b4acf7`, 2026-11-22. Design investigation is
authorized; hosted execution, gate adoption, runner installation and spending
are not. The private main-checkout `docs/plans/repo-health-scan.md` informed
scope; application plans do not prescribe these gates. ADR-087 keeps `develop`
as integration target; the older plan's “main” does not mean `master`.

## Local probe and its limits

The experiment archived tracked HEAD into a fresh directory, resolved the suite
manifest there, and ran `tests/test_document_status.py` and
`tests/test_test_suites.py` serially using the existing main-checkout virtualenv.
Result: **32 passed, 1 skipped**, 5.027 seconds including process overhead.
Neither `.env` nor `docs/plans` was present. The skip is the explicit private-plan
check. An installed private tree is still validated by fixture-based contracts.

This validates the tested public/private asset distinction and ownership
manifest from clean source. It does not validate a fresh dependency installation,
Git-dependent checks from an archive, the full suite from clean source, a remote
runner, or its runtime/cost. The archive intentionally has no Git metadata.
The regular full-suite baseline is separate evidence from the isolated worktree.

## Proposed executable contract, pending authorization

Use a disposable Windows runner, a normal Git checkout of the exact revision,
Python within the committed `>=3.13,<3.15` constraint (pin one minor for the first
acceptance), Node for existing JavaScript checks, and a pinned uv release.
Do not copy the owner's virtualenv, `.env`, private plans, databases, logs,
native-client configuration or model files. Install from the committed lockfile:

```powershell
python -m uv sync --locked --group dev
python -m uv run --no-sync ruff check .
python -m uv run --no-sync ruff format --check .
python -m uv run --no-sync pyright
python -m uv run --no-sync python scripts/generate_skill_registry.py --check
python -m uv run --no-sync python scripts/check_style_tokens.py --check
python -m uv run --no-sync python scripts/run-tests.py full -- -q --junitxml=reports/offline.xml
```

These are design commands, not a record of executed installation or checks.
The runner already separates JUnit filenames by workspace/Council/job-search.
Start with no dependency cache so stale environments cannot hide missing setup.
Record interpreter/Node/uv versions, lockfile hash, exact Git SHA, collection
counts, skips, failures and elapsed time. Fail visibly on missing tools or
installation problems; do not convert them to skips. GPU and live suites are
outside this contract. Establish parity before choosing a worker count for CI;
the current runner defaults to eight workers, not serial execution.

Use `permissions: contents: read`, no provider credentials, no checkout credential
persistence, no untrusted privileged workflow trigger, and pinned action SHAs.
Proposed first acceptance cap: one Windows job, 20 minutes, no retries, no
scheduled runs; retain only reviewed JUnit and aggregate reports for seven days.
These caps are a proposal, not an allowance or an implemented workflow.
Repository code and dependency requests leave the machine; GitHub receives code,
job metadata and retained reports. Test output must be inspected for private
paths/data before choosing retention. Dependencies come from the configured
package registries. Do not upload whole scratch worktrees or host records.

Require the full check on the exact candidate merge revision before merging to
`develop`; invalidate it after any source/base change. Always emit the required
status. Path filters that skip the whole workflow are unsuitable enforcement.
Branch protection/merge-queue configuration and access are separate owner
decisions; a nightly check or passing local hook does not supply remote merge
enforcement. No `.github/workflows` file was created by this spike.

## Exact tier membership proposal

These are test-gating tiers, separate from ADR-087 change-risk tiers.

| Tier | Proposed membership | Adoption status |
| --- | --- | --- |
| Commit | Existing Ruff lint with fixes and Ruff formatting, changed Python files | Preserve current hooks |
| Push | Pyright; skill-registry check; style-token check; current full offline test runner | Recommended now; preserve current hooks |
| Optional affected push | Same three non-test checks; union of groups from the frozen selector; unknown/shared/deleted paths fall back to full | Not adopted |
| Merge to `develop` | Full offline suite on the exact merge candidate; lint, formatting verification, Pyright, skill-registry and style-token checks; review required by ADR-087 risk tier | Full-suite invariant retained; remote enforcement not deployed |
| Scheduled diagnostic | Optional full suite/coverage for drift, never a substitute for merge validation | Not scheduled |
| Live/model quality | Existing explicit opt-in suites and separately bounded evaluations | Excluded from offline tiers |

The exact expanded file membership is preserved in `health-48679817/membership.json`
and raw `.tmp/health-48679817/membership.json`, rather than an ambiguous “fast tests”
label. At the baseline: provider 56, orchestrator 18, agent 70, CLI 103, research
13, dashboard 65, Council 12, job-search 20: **357 offline modules**. Three live
modules are excluded. Workspace is the first six groups (325 modules).
The current selector maps agent/dashboard source to all workspace groups;
provider/orchestrator/shared/unknown paths to all offline groups; Council and
job-search source to their own group plus workspace consumers. Directly owned
test edits select their group. Multiple paths take the union. This remains a
shadow prototype; its CLI compares committed base-to-HEAD and ignores uncommitted
edits. The experiment calls its function with the precise prospective source path.

## Hosting choices and owner boundary

Official sources refreshed 2026-11-22:

- [GitHub hosted runners](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners):
  disposable hosted VMs and managed Windows images support off-PC execution.
- [GitHub billing](https://docs.github.com/en/actions/concepts/billing-and-usage):
  standard hosted usage is free for public repositories; private account
  allowances and overage depend on the plan. No account allowance was inspected.
- [Jenkins on Windows](https://www.jenkins.io/doc/book/installing/windows/):
  service installation requires a JVM and a service account/logon permission.

GitHub hosted Windows is the technically preferable first hosted candidate:
independent reports and no controller maintenance, at the cost of external code
execution/data boundaries and potentially billed minutes. An isolated self-hosted
runner gives environment control but needs isolation, patching and cleanup; an
owner-PC runner retains contention. Jenkins gives operational control but adds
controller/JVM/plugin/service maintenance without an evidenced distinct need.

Estimate hosted cost only after choosing repository visibility, runner rate,
measured hosted minutes, job frequency, report storage and current allowance.
Local seconds measured here are not hosted minutes. No numerical cost saving or
free-account eligibility is established by this spike.

Recommendation: retain current full gates while reviewing prospective evidence.
If PC contention is the deciding problem, authorize one bounded hosted acceptance
after agreeing data, permissions and spending; selection alone does not move work
off the PC. The existing G3 owner gate remains the decision surface. This design
adds no new standing owner action and does not assert an owner choice.
