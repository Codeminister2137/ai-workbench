# Test selection, timing, and CI assessment

## Measured checkpoint (2026-10-05)

The initial root run collected 1,132 cases: 1,125 passed and seven skipped in
158.63 seconds with the IDE SDK installed. Parametrization contributes to that
count; it is not 1,132 separately written test functions. Profiling one mocked CLI
test showed 8.03 seconds in real Ollama identity probes. Several orchestration
tests also fingerprinted the actual development workspace, including its local
environment, instead of a small fixture directory. The diagnose-mode boundary
test ran real machine and installed-client discovery.

The fixes keep production behavior unchanged:

- CLI regression fixtures report an unavailable fake runtime for fallback probes;
  dedicated native admission, runtime and readiness tests retain their contracts.
- Orchestration/repair tests use their temporary workspace while still executing
  the actual fingerprint, persistence, repair and handoff logic.
- The diagnose boundary and local-capability composition tests use explicit
  metadata fixtures rather than the owner's running services and hardware.

The initial verified offline workspace check passed **1,154 tests, with one
Windows symlink-permission skip**: root component suites took 56.14 seconds and
Council took 1.92 seconds. Six live-provider cases are excluded from this command. The root
portion is about 65% faster than the baseline despite eight additional regression
cases. An intermediate run took 93.32 seconds before the remaining workspace and
diagnostics fixture fixes; these are machine measurements, not latency guarantees.

The fresh plan-audit fixes increased coverage to **1,287 passed**, with the same
Windows symlink-permission skip: 58.56 seconds for root suites and 2.23 seconds
for Council. The extra coverage did not make the roughly one-minute full gate a
bottleneck. The group table below preserves the earlier profiling checkpoint.

| Group | Modules | Collected cases | Sum of measured case times |
| --- | ---: | ---: | ---: |
| provider | 11 | 80 | 0.13 s |
| orchestrator | 12 | 164 | 10.01 s |
| agent | 16 | 162 | 18.76 s |
| cli | 22 | 318 | 5.78 s |
| research | 12 | 410 | 19.97 s |
| council | 6 | 21 | 1.82 s |

Case times include pytest setup/teardown but exclude collection/startup. These
are aggregates from one full run, not separately benchmarked group wall times.
Baseline CLI case time was 103.31 seconds. Remaining slow checks largely exercise
real local processes, timeout cleanup, Git fixtures and HTTP/session boundaries.
Keep those checks: replacing their effects with mocks would weaken coverage.
Ignored local XML/profiling evidence is under `artifacts/local-tool-host-acceptance/`.

## Run relevant groups while iterating

The 2026-10-08 audit adds `job-search` to the full offline gate. Root, Council,
and job-search run in separate processes to avoid legacy top-level import
collisions. Discovery checks root tests plus all applications/packages and fails
on unassigned modules. JUnit output preserves `workspace`, `council`, and
`job-search` reports when multiple groups execute.

CLI tests import the package implementation directly. Synthetic external-client
process execution is injected through its runner argument, preserving actual
foreground scopes and session receipts. Examples no longer copy test patches
into production globals.

The standard-library runner selects explicit files; it does not guess coverage
from changed Git paths. Its group manifest fails if a discovered test module is
unassigned or belongs to multiple groups. Group ownership follows the behavior
under test and includes several composition boundaries, rather than promising
one-to-one package dependency isolation.

```powershell
python -m uv run --no-sync python scripts/run-tests.py --list
python -m uv run --no-sync python scripts/run-tests.py cli -- -q
python -m uv run --no-sync python scripts/run-tests.py agent cli -- -q
python -m uv run --no-sync python scripts/run-tests.py full -- -q --durations=20
```

Use the configured interpreter when running these commands from an IDE agent.
After an intentional dependency change, synchronize the required extras first.
Everything after `--` is forwarded to pytest. With multiple pytest processes,
`--junitxml=report.xml` produces separate `report-workspace.xml`,
`report-council.xml` and `report-job-search.xml`, preserving all three reports.

The pre-commit stage still runs fast Ruff checks. Pre-push runs Pyright and the
full offline workspace runner. Council runs in its own pytest process because
it has a legacy top-level `tests` package. The previous root `pytest` command
omitted these 21 Council cases; that command's discovery remains unchanged.

The runner removes Git's repository-local hook variables from pytest child
environments, including repository/index paths and scoped configuration entries.
Otherwise fixture Git commands can operate on the publishing repository instead
of their temporary directories. Ordinary tool settings and noninteractive Git
controls are preserved. A local-only push-hook regression checks that fixture
commits and bare-repository initialization leave the sender's HEAD, index and
configuration unchanged. This isolation does not replace tool permissions.
The Council private-config assertion was stale and now matches the documented
ignored `council.json` / committed `council.example.json` policy.

With installed pytest 9.1.1, mixed explicit selections can lose package autouse
fixtures when a root-level file is selected between files from that package.
Collection diagnostics reproduced two `tests/repo_assistant` package collectors:
the fixtures belonged to the earlier object, outside the later test's ancestry.
This caused synthetic native-model admission failures, rather than an admission
regression. Put root-level modules before nested package selections, keep package
selections together, or use separate scoped invocations. The root-first control
retained the fixtures and passed 23 core/native completion tests. Do not weaken
runtime admission or duplicate its mocks to work around collection order.
No dependency or package-layout change was needed. Evidence and the installed
collector/fixture source trace: `artifacts/cli-pytest-fixture-investigation-20261020cw/`.

Choose groups by the affected contract. Provider changes often warrant provider
plus agent/CLI composition checks; routing changes warrant orchestrator plus the
affected consumers. Shared approval/session changes warrant agent and CLI.
Always run the full workspace gate after the focused checks pass. A group passing
does not establish that unrelated consumers or live model quality passed.

Live integrations retain their existing explicit environment opt-ins:

```powershell
python -m uv run --no-sync python scripts/run-tests.py live -- -q
```

Selecting `live` alone does not set flags, start Ollama, load models, or enable
hosted spending. Inspect the integration module's requirements before enabling it.

## Class-level tests

Baseline JUnit evidence contained zero collected test classes. The IDE tests now
group coherent contracts into `TestConfigurationImport`, `TestReadOnlyWrappers`
and `TestSdkFailures`; runner selection uses `TestSuiteSelection`. For example:

```powershell
python -m uv run --no-sync pytest tests/test_ide_bridge.py::TestConfigurationImport -q
```

Classes improve navigation and allow a whole contract to be selected by node ID.
The fresh audit's JUnit report contains 16 coherent class groups covering 145
cases, including SDK failures, receipt admission, streamed calls, hard latency
and report continuation. These group related behavior rather than merely wrapping
each existing function in a class.
They do not reduce execution count or automatically share fixture setup. Existing
fixtures remain function-scoped to preserve permission/session independence.
Use a class when a file contains several recognizable contracts with related
tests. Function-based tests and parametrization remain appropriate for a cohesive
module. A mechanical conversion of every test would add churn without a measured
benefit. Pytest documents [selection and durations](https://docs.pytest.org/en/stable/how-to/usage.html)
and [class node IDs and markers](https://docs.pytest.org/en/stable/example/markers.html).

## CI recommendation and decision boundary

The current approximately one-minute offline gate is manageable for a single
developer. Keep focused local checks plus the full pre-push gate. No extra test
plugin, Jenkins installation, service, account, or remote runner was introduced.
The owner accepted this recommendation on 2026-10-05. Jenkins and hosted CI are
deferred until a concrete requirement justifies their infrastructure and access.

| Option | Benefit | Cost / decision needed |
| --- | --- | --- |
| Existing local hooks and grouped runner | Immediate focused feedback; no new infrastructure | Full verification still depends on local execution |
| Hosted repository CI | Independent PR checks and retained reports | Choose provider, repository access, execution/data boundary and allowance |
| Jenkins | Owner-controlled scheduling, runners and reports | Java/controller/service, permissions, updates, credentials and maintenance |

Jenkins schedules test execution; speeding the tests still requires fixing
fixtures or safely parallelizing independent work. Its Windows installation
introduces a service account and listener, described in the
[official installation guide](https://www.jenkins.io/doc/book/installing/windows/).
Defer that infrastructure until independent checks or scheduled automation have
a concrete requirement. If requested, choose the CI host and its access boundary
first; the grouped runner and JUnit reports already provide reusable commands.
Investigate parallel pytest execution only if deterministic suite latency becomes
a material bottleneck again and isolation is verified for process/port/SQLite tests.
