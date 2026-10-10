# Coding-chat acceptance checkpoint: 2026-10-09

Migration acceptance remains **INCOMPLETE**. Quality parity and delegation
savings have not been established.

## Attended preparation and live continuation checks: 2026-10-10

The approved Codex gpt-6.1-sol/medium batch began at 14:39:31 UTC, with a
15:09:31 UTC deadline and an eight-turn maximum. No automatic retries or billing
fallback are permitted. Fresh settings preflight recorded zero inference requests.

The reduced boundary fixture passed both genuine follow-up and clean-restart
checks. Each used two native turns; the batch has used four. Planning read the
source without edits; the subsequent correction passed unchanged host tests.
Protected files and fixture paths were unchanged, and observed operations stayed
within the shared read/edit contract. Saved receipts:
`artifacts/coding-chat-acceptance/synthetic-coding-chat-s47h1smv/results.json`
and `synthetic-coding-chat-k3go1low/results.json` in the same artifact directory.

The subsequent physical run used one turn (batch total five). Its terminal log
records an incomplete approval-command refusal, then a fresh-ticket grant and
completed edit. The first-turn report was followed by `You>` and `/exit`; no
steering request or second edit ticket occurred. The owner confirmed no denial
prompt appeared. Grant is verified; denial, queued steering and explicit stale
ticket refusal remain untested. Host tests passed; protected files were unchanged.
The operator instructions now require steering before the first grant and explain
how to submit the second request at `You>` if it was not queued. No live retry
followed this correction. Receipt: `synthetic-coding-chat-rl9moryv/results.json`
and `reduced.log` in the same acceptance artifact directory.

After the owner explicitly confirmed readiness again, the corrected physical
check used two turns (batch total seven). Its log records queued `/steer`, a
fresh-ticket grant, a second distinct fresh-ticket denial, then `/exit`. The
second host edit receipt is failed with `authorized=false`; the proposed comment
is absent and the saved source matches the first approved correction after
normalizing LF/CRLF. Host tests and protected-file/path checks pass. Receipt:
`synthetic-coding-chat-axr25xac/results.json` and `reduced.log` in the same directory.

This verifies physical steering, grant and denial. Explicit stale-ticket refusal
remains untested, and the driver retains `attended_arbitration_verified=false`
because it does not automatically certify physical input. Raw CLI status is one
after the expected denial; the wrapper currently labels every nonzero as failure.
The wrapper message was subsequently corrected to require inspection of results
and the ticket log before classification, explicitly explaining that a deliberate
denial returns nonzero. The exit code, raw receipts and conservative automatic
verification flag are preserved; genuine failures are not converted to success.
This is not evidence of an authorization failure. No additional retry/model call
followed. These results do not complete every criterion of the arbitration case.

These checks establish
narrow installed-client continuity evidence, not broad migration parity or the
20% savings target. Token counters are available per turn; allowance delta and
API spend remain unknown. A prepared visible-terminal wrapper reserves at most
two more turns and refuses startup with fewer than five minutes remaining.

## Prepared comparison

`scripts/coding-chat-acceptance.py` prepares equivalent synthetic fixtures for
cases 6–8: preserve dependency/API decisions, honor a correction about negative
input, and fix an exclusive-end boundary. Full-history and 4,000-character
reduced-history arms use identical code, tests and synthetic prior messages.
Offline preparation confirms that the five-case test fixture detects the bug.

Live execution uses the actual coding-chat CLI and scoped shared tools. Only
synthetic source/instructions/conversation are supplied to the client; fixtures
live outside the private repository. Codex native execution remains read-only;
project tools use `workspace_write`. The request permits editing only the function
module, prohibits model-run commands/delegation/network tools, and leaves the
unchanged tests to the host. This compares context reduction; it does not supply
the assistant baseline or delegation arm required for full acceptance.

The runner permits at most two client invocations, stops after a failed arm,
uses 120-second timeouts and never switches billing sources. It selects
`gpt-6.1-sol`, medium reasoning, no daemon and isolated client configuration.
`--preflight` queries the installed foreground client's `config/read` without
`thread/start` or `turn/start`; only selected model/reasoning/client metadata is
saved. The actual local check verified Codex 0.159.3 with the requested settings.

Use the configured interpreter with existing project dependencies/import paths.
For source-checkout execution under a system interpreter, the acceptance driver
forwards its explicit `PYTHONPATH` to the MCP child alongside the invocation-token
environment name. This fixture-only adjustment changes no production settings or
grant boundary. Use a native client executable so the preflight owns its process.

```text
<configured-python> scripts/coding-chat-acceptance.py --preflight --codex-command <native-codex-executable> --effective-settings <receipt.json>
<configured-python> scripts/coding-chat-acceptance.py
<configured-python> scripts/coding-chat-acceptance.py --live --codex-command <native-codex-executable> --effective-settings <receipt.json>
```

Each run retains a separate receipt under ignored `artifacts/coding-chat-acceptance/`:
reported usage, latency, source before/after, immutable-test checks, host validation
and client diagnostics. API spend and allowance changes remain unknown.

## Attempts and corrections

- The first client attempt failed, then its driver waited for idle input because
  the terminal reports stdin as interactive. The owned driver was stopped before
  diagnostics were flushed. Source remained unchanged; its interrupted session
  is not automatically reconciled or replayed.
- The second, single-arm attempt used isolated input and exited promptly. Codex
  reported that required `repo_shared` MCP initialization failed before a model
  turn. No model response, tool effects or token usage were captured. This does
  not establish unavailable account allowance.
- The source-checkout setup needs explicit MCP import-path forwarding. The driver
  now forwards it while preserving scoped tokens, isolates stdin, flushes client
  evidence immediately and keeps separate receipts. Offline tests cover these
  contracts; the next installed-client attempt verified that MCP starts and
  `read_file` works with this adjustment.
- Automatic approval review rejected another pair because earlier attempts
  consumed the announced two-invocation cap. No retry or alternate execution
  followed the rejection. The owner subsequently authorized two additional
  attempts while present; one was used as described below.

## Renewed installed-client attempt

The full-history arm reached a model turn and read the synthetic source through
`repo_shared`. It returned the correct proposed fix, including the latest owner's
negative-size correction and the dependency/API constraints. However, it inferred
that the native read-only sandbox prohibited all writes. No shared edit was
attempted, and no tool denial established that inference. Source and tests stayed
unchanged. Host validation failed four of five cases, despite client exit code 0.
The runner stopped before the reduced-history arm.

The receipt is under ignored
`artifacts/coding-chat-acceptance/synthetic-coding-chat-u83dwjzu/`. Elapsed time was
20.65 seconds; reported input tokens 63,116, cached input tokens 52,736, output
tokens 288 and reasoning output tokens 67. These are client usage fields, not
independent billing measurements or context-reduction savings.

The production execution prompt now describes the native sandbox and effective
shared profile/policy separately for primary, repair and fallback. It preserves
task restrictions and per-call enforcement, grants no new authority, and prohibits
retrying actual denials through another execution surface. Deterministic tests
cover the distinction, scoped primary turns and actual partial-effect fallback.
The fixture driver additionally supplies an overall 120-second deadline and
preserves any shorter outer deadline. Host failure stops the comparison even
when the client returns zero.

## Reduced-history verification after the prompt fix

The owner confirmed readiness again and clarified that no terminal approval
prompt had appeared. The remaining authorized attempt ran the reduced-history
arm with the corrected production prompt. No physical terminal approval was
requested or claimed; shared writes used the selected `workspace_write` policy.

The client read, edited and reread `range_tools.py` through `repo_shared` (three
completed calls, six start/completion events). The edit receipt reports an
authorized write. The saved code honors the exclusive boundary, raises
`ValueError` for negative size and accepts zero. Tests and API remained unchanged,
with no added dependencies. All five immutable host tests passed; client exit 0.

Evidence is under ignored
`artifacts/coding-chat-acceptance/synthetic-coding-chat-k3oqm24j/`. Reduced history
including the current request was 4,000 characters. Elapsed time was 20.81 seconds;
reported input tokens 96,975, cached input tokens 87,808, output tokens 308 and
reasoning output tokens 0. No command or web-search events were recorded.

This completes the bounded prompt-fix verification: two model turns and one
successful edit/validation arm. Both renewed attempts have been used, and no
further live run was started. Installed-client mutation and correction retention
are evidenced for this synthetic fixture only. The full and reduced runs are
not a controlled quality/economics comparison: the prompt changed between them,
and the successful run made more tool calls. Client token totals include those
calls; a shorter supplied history does not imply lower total consumption.

## Broader pilot preparation

The owner requested broader planning and execution with minimal interruptions.
The existing runner now supports three fixed cases: `boundary`, `configuration`
and `extraction`. Each has equivalent full/reduced starting inputs and independent
immutable tests. Offline checks demonstrate failure on each original defect and
success on the reference correction. A reference is a local test oracle, not a
model comparison baseline. Receipts fingerprint inputs and the execution module.
Changed tests, fixture instructions or routing prevent host acceptance.

All three real offline preparation commands ran without inference, each retaining
separate receipts. Full-context characters: boundary 23,145, configuration 23,293,
extraction 23,412; each reduced arm is 4,000. The actual-CLI regression matrix now
also covers long-history native restart and scoped partial-effect fallback with
retained corrections/outcomes and unchanged transcript originals. External
clients are synthetic in those deterministic tests; actual tool effects are local.

The prepared live batch has six calls: one matched full/reduced pair per case,
using the same corrected execution prompt and pinned settings throughout. Stop
the entire batch on its first failed arm, with no retries or billing fallback.
The owner subsequently approved this batch; its completed results are below.
See [the staged plan and proposed acceptance rubric](coding-chat-quality-cases.md).
Overall quality/economics thresholds remain owner decisions, not implemented facts.

## Approved six-call pilot: complete

A fresh no-inference preflight confirmed installed Codex 0.159.3,
`gpt-6.1-sol` and medium reasoning. Exactly six model calls ran: two per fixture,
with no retries, delegation or billing fallback. All six arms passed. Each
performed `read_file`, `edit_file`, `read_file` on its one permitted module;
each edit receipt reports an authorized write. Original tests, instructions and
route catalog stayed unchanged. No command or web-search events were observed.
The production execution-module fingerprint was identical across all three pairs.

| Case / arm | History + request chars | Host tests | Seconds | Input tokens | Cached input | Output tokens |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| Boundary / full | 23,145 | 5 passed | 23.29 | 110,111 | 98,432 | 299 |
| Boundary / reduced | 4,000 | 5 passed | 23.88 | 96,989 | 84,736 | 303 |
| Configuration / full | 23,293 | 4 passed | 28.79 | 110,842 | 98,688 | 532 |
| Configuration / reduced | 4,000 | 4 passed | 30.15 | 97,618 | 84,864 | 522 |
| Extraction / full | 23,412 | 4 passed | 22.98 | 110,959 | 98,816 | 383 |
| Extraction / reduced | 4,000 | 4 passed | 23.94 | 97,673 | 80,768 | 374 |

Receipts, before/after source, client events and host validation logs are under
ignored `artifacts/coding-chat-acceptance/` in these directories:

- Boundary: `synthetic-coding-chat-d63z1d95`
- Configuration: `synthetic-coding-chat-b5zevnb5`
- Extraction: `synthetic-coding-chat-p5xepw6o`

Source review confirms the boundary corrections in both arms. Configuration
rejects booleans, malformed and nonfinite/out-of-range values, normalizing
conversion errors to `ValueError`; both implementations also catch overflow.
Extraction preserves the constructor and method and delegates current object
values to the reusable function, without extra rounding or validation policy.

Across the three pairs, reported total input was 331,912 full versus 292,280
reduced (11.94% lower). Input minus cached input was 35,976 versus 41,912, higher
for reduced history. Summed elapsed time was 75.05 versus 77.97 seconds. These
are derived from client-reported usage and driver time, not independent billing
or allowance measurements. Each pair ran full first, with one run per arm;
cache conditions, order and sampling remain confounders. No cost/allowance or
delegation savings claim follows from lower total input alone.

This establishes correctness for these three single-real-turn fixtures with
synthetic prior history. It does not establish 20-case migration parity, genuine
multi-turn conversational quality, current-assistant baseline parity or delegated
quality/economics. The approved six-call allowance has been fully used.

After the pilot, the existing runner gained an offline-verified genuine two-turn
mode: inspect/discuss without edits, then apply the owner's correction in the
same CLI conversation. It refuses a two-arm invocation to retain its two-call
cap. Planning requires an observed successful read and inspection-only events;
failed reads, commands/network/mutation events or file changes suppress the
follow-up. Per-turn logs and usage remain separate, with last-turn scope explicit.
The initial offline preparation ran with zero live calls. The subsequent
four-call conversation comparison received separate owner authorization; its
results are below.

After resuming from a usage-limit interruption, the full local gate passed
1,736 tests with three Windows symlink privilege skips. The subsequent absolute
source-path normalization is covered by the focused acceptance suite (24 passed).
Root Ruff lint/format and both root and explicit runner Pyright checks passed.
These checks validate software contracts, not additional model-quality cases.

## Approved four-call two-turn comparison: complete

The owner authorized continuation of the prepared boundary conversation pair.
A fresh local settings preflight confirmed Codex 0.159.3, `gpt-6.1-sol` and medium
reasoning without inference. Exactly four calls ran, two in each arm. Both arms
passed all five unchanged host tests. Input, execution-module and runner hashes
match across the pair. Original tests, instructions and catalog stayed unchanged.

Each planning turn performed one authorized `read_file` on `range_tools.py`,
identified the exclusive-end defect and proposed clamping negative size under
the earlier owner decision. Neither planning turn edited files or ran commands.
Each second turn followed the explicit owner correction instead: negative size
raises `ValueError`, zero size remains valid, and the end is exclusive and capped.
Both produced the same four-line correction, using authorized read/edit/read
calls on that module alone. Receipts retain one conversation task ID per arm
and fresh run IDs per turn. No command, native file-change or web-search events
were observed. Model reports accurately left host test results unverified.

| Arm / turn | Input tokens | Cached input | Output tokens |
| --- | ---: | ---: | ---: |
| Full / planning | 63,380 | 52,864 | 333 |
| Full / correction | 112,896 | 100,608 | 308 |
| Reduced / planning | 55,526 | 40,704 | 343 |
| Reduced / correction | 98,895 | 81,152 | 304 |

Receipts and per-turn events are under ignored
`artifacts/coding-chat-acceptance/synthetic-coding-chat-ix37_omq` (full) and
`synthetic-coding-chat-sez9cmj2` (reduced). Summing both turns gives 176,276 versus
154,421 input tokens (12.40% lower for reduced), but 22,804 versus 32,565 input
minus cached tokens (higher for reduced). Elapsed time was 64.40 versus 46.30
seconds. Full ran first; each arm has one sample. Cache/order/sampling remain
confounders, and cost/allowance savings remain unproven.

This adds narrow live evidence for source-grounded planning, waiting before
implementation, and later owner corrections within a real two-turn conversation
under reduced history. It does not establish representative quality or baseline
parity. All four authorized calls are used; no further call was started.

Next: select the proposed representative quality bar and remaining acceptance
priorities. Preserve these comparisons as evidence; do not silently expand them.
Interactive approval, live steering/restart and cross-client fallback acceptance
remain separate gaps. API cost, current remaining allowance and allowance delta
are unknown. Representative baseline/delegation evidence is still required before
any migration parity or savings claim.

## Subsequent gap preparation: offline only

The runner now prepares clean restart and genuinely attended steering/approval
checks, with the same existing CLI, storage and two-call cap. No model call ran
while preparing them. Offline receipts: `synthetic-coding-chat-fo3o2jho` (restart),
`synthetic-coding-chat-_8ig3_tv` (attended), and `synthetic-coding-chat-sv3qx_p1`
(local PowerShell launcher preparation). These receipts are preparations, not
quality results. See [the planned checks](coding-chat-quality-cases.md#prepared-restart-and-attended-arbitration-checks).

## Approved restart check: complete; attended check failed safely

The owner approved up to four new Sol 6.1/medium calls for reduced-history clean
restart followed by attended arbitration. A fresh no-inference settings check
confirmed Codex 0.159.3 and the pinned settings. The restart used exactly two
calls and two foreground CLI invocations, retaining the same SQLite conversation.
Read-only planning made one authorized module read; the resumed correction made
authorized read/edit/read calls. Their task ID stayed stable and run IDs differed.
All five unchanged host tests passed; protected inputs stayed unchanged, with no
command, native file-change or web-search events. Receipt:
`artifacts/coding-chat-acceptance/synthetic-coding-chat-3pzu4vme`.

Reported input/cached/output: planning 55,547/40,704/313; resumed correction
98,848/85,888/322. Total input 154,395, cached input 126,592; elapsed 44.17 seconds.
This is clean restart evidence, not live interruption/partial-effect recovery.

The owner-controlled PowerShell window ran one attended call after another local
settings check. Its saved log records an exact edit ticket followed by bare
`yes`, which was queued as chat instead of granting permission. The client timed
out at 120 seconds while the edit remained unapproved. The owner exited; source
and protected inputs stayed unchanged, and host validation failed on the original
defect. Receipt: `synthetic-coding-chat-17pgbvf1`. The stage stopped after this
failure: three calls total, no retry or second attended call. Usage for the timed
out call is unavailable. The 165.22-second arm time includes later terminal input.

This supplies live evidence that ordinary chat text cannot grant an edit, not
successful steering/fresh-grant/fresh-denial acceptance. The timeout diagnostic
also overflowed the 4,000-character mandatory history budget; the host refused
the queued follow-up without discarding evidence. The user understood bare yes
as approval, so prompt guidance now explicitly requires the complete command.
The runner now saves partial timeout output and closes its attended reader on
client failure, suppressing queued execution. Offline regression tests cover
this cleanup and evidence retention; the live failure predates those fixes.

## Unattended local continuation

The owner requested unattended work and permitted scripted fixture approval
testing while away. Deterministic tests now exercise the actual coding-chat reader
and fresh approval tickets through real scoped HTTP MCP tool calls across
synthetic Codex/Copilot fallback. Plain chat, stale-ticket answers and in-flight
owner corrections precede exact fixture grants/denials; effects and hashed scope
receipts verify authorization. All tickets differ, queued corrections persist,
protected files stay unchanged and reader cleanup is verified. These are scripted
fixture decisions, not physical human terminal approvals or live model fallback.

A native-provider regression performs a real approved file edit, then interrupts
the synthetic client. Unreconciled resume refuses before model execution. After
explicit reconciliation, the same transcript and queued owner correction survive,
the source is reinspected, and a fresh edit denial preserves the partial effect.
No cloud client participates. This strengthens software recovery evidence, not
live interruption acceptance.

Bare yes/no during a pending ticket now shows the complete approval command
immediately. External-client timeout reasons also omit command arguments in
default failure output, conversation history and repair records. Regression
fixtures verify that long synthetic prompt arguments do not leak or overflow a
4,000-character history budget. Raw diagnostics retain their existing explicit
logging boundary. No new live calls, account changes or services were used.

Final unattended validation: workspace 1,687, Council 33 and job-search 37 tests
passed (1,757 total), with three Windows symlink privilege skips. Focused
conversation/input/history/acceptance/fallback checks passed 102 tests; targeted
timeout/reporting/repair checks passed 78. Ruff lint/format, root Pyright and
explicit acceptance-runner Pyright passed. The full gate was repeated after the
timeout reporting changes; its log is
`artifacts/coding-chat-unattended-final-validation.log`.

## Fresh unattended window: offline follow-up (2026-10-09)

Execution began at 16:19:17 UTC / 18:19:17 Europe/Warsaw, with a deadline of
18:19:17 UTC / 20:19:17 Warsaw. Existing uncommitted work was retained. No new
live calls, installations, account probes or physical approvals were performed.

The acceptance driver now requires matching host-observed source reads/edits and
rejects forbidden client operations, invented effect claims, writes before reads,
hidden restored-byte host edits and extra fixture paths. Host test success alone
cannot establish acceptance. Existing live receipts predate these checks and are
not retroactively certified by them.

Two additional offline fixture families prepare authenticated redirect and
resolved path containment comparisons. Their host checks use synthetic loopback
HTTP and temporary paths/junctions; original defects fail and reference corrections
pass. Reference corrections remain local oracles, not assistant baselines.

The runtime diagnostic now refuses an outside-resolving `pyproject.toml` before
reading it. Actual coding-chat/shared-host tests cover semantic rename preview
continuation through synthetic route exhaustion, stale-source refusal and restart
invalidation. Actual native CLI checks cover complete changed skill/repository
instructions after history reduction/next turn/restart, plus missing-skill refusal
before another provider call. Approval callbacks and model responses are synthetic.

Validation: workspace **1,715 passed / 3 existing Windows file-symlink skips**,
Council **33 passed**, job-search **37 passed**; **1,785 total passed**.
Log: `artifacts/coding-chat-window-20261009-final-gate.log`. Ruff lint/format,
root Pyright and explicit acceptance-runner Pyright passed. A test assertion's
optional metadata access was corrected after the full gate; the history suite
then passed all 11 checks and root Pyright passed again.

The [20-case local coverage map](coding-chat-quality-cases.md#local-preparation-coverage-2026-10-09)
distinguishes these contracts from conversational/model evidence. Genuine attended
grant/denial, live partial-effect recovery, newly selected cross-client comparisons,
matched current-assistant baselines and delegation economics remain gaps.
Quality parity and cost savings remain unproven.
## 2026-10-10 offline terminal polling correction

Fresh ADR-049/C4 comparison found two POSIX input defects: blocking `readline()`
could wait for the rest of an unfinished correction during reader cleanup, and
text buffering could strand additional pasted lines until a new keystroke.
Polling now reads at most 4096 ready descriptor bytes, retains incremental Unicode
decoding and complete lines across active/idle turns, and delivers final input
before EOF. A separate Windows regression reproduced dropped UTF-16 pairs;
console polling now combines them across polls before echoing or queueing text,
and backspace removes the complete decoded character. This follows the native
[CPython getwch implementation](https://github.com/python/cpython/blob/v3.14.3/PC/msvcrtmodule.c).

Five regressions use real OS pipes with controlled readiness on this Windows
host, covering pasted follow-ups, split UTF-8, partial input, CRLF/blank lines and
EOF. The original code failed pasted-line delivery and blocked the partial-input
test; the owned failing test process was stopped. The corrected terminal/input/
controller/acceptance selection passed 104 tests. This is offline contract
evidence, not an attended POSIX terminal or installed-client acceptance. The
Windows pair regression uses controlled getwch results, not a physical keypress.
