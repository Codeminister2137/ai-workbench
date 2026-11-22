# Deep health evidence and gate adoption brief

Run `4867981737e24307ac79391b04b4acf7`, 2026-11-22; baseline source
`2459d6470169c91b870a76a4da4efdef3ca857a8`, branch
`docs/health-deep-48679817`. This is an evidence slice, not gate adoption,
production fixes, dead-code removal, or sweep integration.

## Scope and evidence provenance

The relevant private plan is the main checkout's `docs/plans/repo-health-scan.md`.
It authorizes deep evidence and gate research; application plans do not determine
this slice. ADR-087 makes `develop` the integration target. The plan's older
reference to merging to "main" does not authorize changes to `master`.

The resumed checkout contained scripts, completed receipts, and an interrupted
cross-component mutation. The original incomplete log is preserved, unscored.
Process inspection found no active experiment Python process. The mutation was
verified against HEAD (accounting for CRLF) and restored; see
`interruption-recovery.json`. The cause of the earlier interruption is not
established by its truncated log. No claim is made about prior host effects.

Original bounds: two source mutations, one deletion, at most 18 test processes,
300 seconds per process, 2,400-second outer allowance, zero retries. The fresh
continuation has its own baseline, one cross-component mutation, one focused
coverage run and one deletion: at most 11 processes, 300 seconds per process
(120 for focused checks), 1,200-second foreground-supervised allowance, zero
retries. Process timeouts are enforced by subprocess; the outer allowance is
supervised, not a separately installed watchdog. Expected assertion failures
under mutation are observations. Unexpected infrastructure/baseline failures
stop admission. Both mutation paths restore original bytes in `finally`.

Receipts from before resumption are identified as saved observations; current
handler hashes and source restoration are checked independently. The executed
continuation script is preserved separately from its lint-cleaned readable
version; cleanup does not change or regrade consumed results.

## Residual handler triage and import graph

The finite handler sample covers **21 lexical handlers in 11 named functions**;
all recorded source hashes match current files. It distinguishes explicit
failure exits, best-effort socket cleanup, fail-closed authorization, and
convenience readers that fold errors. It is not a census of 372 scan signals.

A saved synthetic PermissionError probe shows `read_dotenv_values(...,
missing="raise")` returning `{}` while `secret_status` reports `unreadable`.
This establishes an ambiguity in the convenience-reader contract, not missing
credentials. Caller notes identify `loop_notify.read_gmail_config` and
`alternate-agent-acceptance.load_dotenv_secrets` for a separate fix slice.
No actual credential-store observation is represented by that probe.

The dotted lexical graph resolves **435 modules and 900 edges**, with **nine
nontrivial strongly connected components**. It records 7,916 unresolved targets,
including external modules and imported symbols rather than just missing imports.
It includes deferred and TYPE_CHECKING imports; dynamic imports, runtime aliases,
implicit package initialization and complete import-system semantics are not
modeled. Roots are apps/packages/scripts with hidden/vendor exclusions. These
counts are not directly comparable with the earlier coarse 335-file graph, and
neither proves a harmful runtime cycle or dead code. Raw edges/SCCs are retained.

## Prospective selection evidence

Selection is frozen from source paths before each mutation. Existing tests are
unchanged; selected and full runs use the same mutated source, serial command
invocation and the test runner's default eight workspace workers. Selection uses
the prototype, not a deployed hook. Case identity is classname plus test name;
failure-set comparison is limited to collected cases and these injected faults.

The saved source-only mutation sets workflow graph node allowance from 50 to 0.
Both runs detect the same five failures, including two dashboard consumer tests:
**zero observed misses**, 5,881 selected versus 6,220 full cases. Selected time
113.923s versus full 130.512s: **16.589s (12.7%) saved** in one unreplicated pair.
This is wall-clock execution time, not CPU, hosted cost, historical failure recall
or a population recall estimate. The selection is deliberately broad.

The saved source-only JUnit files were independently re-parsed on resumption:
case counts and all five failure identities agree with the comparison receipt.

### Final resumption and fresh bounds

The final resumption found another abandoned mutation (`if False and
failure_changed`) and no experiment Python process in the process inspection.
Its selected log is incomplete; it has no full comparison and is unscored.
`final-interruption-recovery.json` preserves the observed source hash. The exact
single replacement was reversed only after verifying it reproduced HEAD modulo
CRLF. Earlier failures, timeouts and incomplete trials remain preserved.

The fresh `health-reserve-48679817.py` trial changes the shared review reserve
from ten to twenty percent, leaving progress classification intact. This is a
different fault, not a replay of either progress mutation. Bounds: at most nine
test processes, 300 seconds each (120 for focused checks), 900 seconds of
foreground supervision, no retries. It includes a focused unmutated baseline,
one selected/full comparison, one focused coverage run and one deletion trial.
The selector is frozen before mutation; all tests remain unchanged. All source
edits restore original bytes in `finally`. Unexpected baseline/infrastructure
failure stops admission. The outer bound is supervised rather than an installed
watchdog. Receipts live in `.tmp/health-48679817-reserve`.

The fresh trial finished all **nine** test processes with **267.156 seconds**
aggregate process wall time and zero retries. Focused unmutated repair baseline:
**33 passed**. Selected/full comparison: **6,220 cases each**, the same **three
reserve assertion failures**, and **zero observed full-only failures**.
Selected time **129.527s**, full **131.994s**; the **2.467s (1.9%)** difference is
execution variation in an unreplicated pair running identical membership, not
selection savings. One socket failure occurred only in selected (see below).
The red earlier full baseline remains red; neither pair is a green full-suite
acceptance. Full fallback gives zero membership misses by construction and does
not establish dependency precision or general recall.

Focused coverage: **19 passed**, **129/143 statements (90.2%)**, **42/50 branches
(84%)** in `aider_polyglot_scores`. `_PolyglotParser.handle_data` specifically
covered **5/5 statements and 4/4 branches**. Removing that method while leaving
tests unchanged produced **10 failed, 9 passed**: inherited HTMLParser behavior
does not preserve its text-collection contract. This rejects that sampled
dead-code candidate and demonstrates meaningful assertions on this callback;
it does not clear the other candidates or establish repository robustness.

`reserve-*.json` receipts retain selection, raw failure identities, timings,
coverage summary and restoration. The final verification confirms all three
experiment source paths match HEAD modulo CRLF, and `git diff --stat -- packages`
is empty. The executed runner was preserved before formatting its readable copy.
Ruff lint and formatting checks pass for all five evidence scripts. No new test
module or production code is introduced; configured Pyright includes packages,
apps and tests, not these documentation-side experiment scripts. No fresh
whole-repository type-check result is claimed.

`resumption-verification.json` independently confirms all 21 handler hashes and
the retained raw dotted-graph hash. These checks verify saved evidence against
the inspected source; they do not turn the sample into a repository-wide census.

### Preserved baseline failure and bounded diagnosis

The fresh full baseline in `.tmp/health-48679817-continuation` recorded
**6,194 passed, 25 skipped, one failed** in 132.811s across three commands.
`test_run_scope_auth_revocation_and_size` raised `ConnectionAbortedError`
(Windows 10053) in `http.client.getresponse` while waiting for a chunked-request
rejection. The experiment stopped before mutation admission; this remains a red
baseline. A separate one-test, 30-second serial diagnostic passed (0.56s pytest
time), which does not erase or explain the failure.

Inspection traced the synthetic client to `http.client._send_request`: explicitly
setting Transfer-Encoding suppresses automatic Content-Length, while
`encode_chunked=False` sends the string body without chunk framing. The server
rejects Transfer-Encoding, `_drain_body` reads zero without Content-Length, then
writes the rejection and closes. Unread-body close/reset timing is a plausible
mechanism; there is no socket trace establishing the originating abort or ruling
out other host causes. This is not evidence of downstream provider failure.

Required web investigation searched `site.github.com/python/cpython http.server
unread request body ConnectionAbortedError Windows 10053 send_error`.
[CPython issue 150499](https://github.com/python/cpython/issues/150499) discusses
unread request bodies and framing, but concerns persistent connections;
[Python issue 27682](https://bugs.python.org/issue27682) discusses 10053 error
handling in a different server. Neither establishes this failure's cause.
Next diagnostic if it recurs: capture synthetic client/server framing and
shutdown events with timestamps under the same worker setting. No production
HTTP or authorization change was made.

A fresh `.tmp/health-48679817-diagnostic` allowance uses the 33-test serial repair
baseline (33 passed), retains the complete selected/full suites under mutation,
and reports unrelated failures separately. It does not retry or regrade the red
baseline. Bounds: nine test processes, 300 seconds each (120 for focused checks),
900 seconds foreground supervision, no retries. The later full-fallback selection
runs all groups, so zero selection misses there would be true by construction,
not evidence of dependency precision or savings.

### Additional socket observation during reserve trial

The selected reserve trial also failed
`test_permissions_session_binding_deadline_and_shutdown`: initialization of an
already-expired scope raised Windows 10053 at `socket.recv_into` through
`urllib`/`http.client` instead of the expected HTTP 401. This is a separate
observation from the earlier chunked-request failure. Inspection shows
`ForegroundMcpHost.Handler.dispatch` rejects expired scope before reading the
POST body; `reply` writes a zero-length response and the default HTTP/1.0
handler closes. An unread-body close is a plausible mechanism, not an
established originating cause. No socket trace identifies the abort source.

Web search: `site.github.com/python/cpython http.server unread request body
Windows ConnectionAbortedError 10053 rejection`. Results included
[CPython 58779](https://github.com/python/cpython/issues/58779) (older
server-side disconnect handling) and
[CPython 150499](https://github.com/python/cpython/issues/150499) (persistent
connection framing). Neither establishes this client-side failure's cause.
Next diagnostic: one separately bounded expired-scope request with timestamped
client send/server rejection/close observations and request-status capture,
without logging credentials or request contents. No retry or transport fix was
performed in this evidence slice. Socket failures are reported separately from
the three reserve assertions; raw failure sets remain unfiltered in receipts.

## Adoption brief

Evidence slice status: **COMPLETE within the declared finite samples**. Gate
adoption, fixes, sweep wiring, a green full-suite baseline and full clean-checkout
dependency parity remain outside this result. Prior interrupted/timeout trials
remain unscored and are not erased by the completed reserve trial. The fresh
267.156s cost excludes those earlier consumed trials and the saved source-only
pair; it is not total workflow or inference cost.

Decision: retain full gates, adopt affected pre-push selection, or authorize a
separate bounded hosted acceptance. This affects missed-regression risk, PC
contention and (for hosting) external execution/data/cost boundaries.

- **A: Retain full gates and continue shadow comparisons.** Preserves present
  test coverage and introduces no service boundary; retains full local cost and
  requires further evidence. Recommended with this small, broad-selection sample.
- **B: Adopt affected pre-push, full suite mandatory before merge.** Can save
  repeated execution, but incomplete dependency knowledge can miss failures;
  this sample does not establish general safety, and merge enforcement must be
  agreed before adoption.
- **C: Authorize a separate hosted acceptance.** Can reduce PC contention and
  produce independent reports; adds external code execution, dependency setup,
  permissions and potentially metered usage. No deployment or spending follows
  from this report. First resolve a clean dependency installation and full-suite
  parity. Jenkins adds controller/JVM/service maintenance; no distinct need was
  established for it.

Technical recommendation: **A**. Consider C if off-PC execution is the priority;
selection alone does not address PC contention. Exact proposed tier/group/file
membership and the clean-checkout contract are in
[the CI design](health-48679817-ci-design.md). Its clean-source probe recorded
32 passed and one explicit private-plan skip in 5.027s using the existing venv,
not a fresh installation or full hosted run.

Owner question on the existing `family5-gate-ci-adoption` dashboard gate:
choose A, B, or a separately bounded C after reviewing these limits. This report
does not resolve that gate, change hooks, install a runner, or add sweep wiring.
The CI design links official GitHub/Jenkins sources; runner/service facts were
checked again during this continuation. No numerical hosted-cost claim is made.
