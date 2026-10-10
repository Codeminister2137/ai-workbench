# Daily CLI readiness — 2026-10-10

**Attended pilot: recommended. Full daily replacement and unattended migration:
INCOMPLETE.** This is an engineering recommendation, not an owner waiver of
ADR-049's quality requirement. No new live model allowance was granted by this
review. The previously bounded allowances are expired or used.

## What can be used now

The actual `ai-assistant --help` entry point runs with the configured SDK and
exposes `coding-chat`, session resume, scoped approvals and fallback options.
The foreground conversation retains owner decisions and host outcomes, refreshes
source/instructions, supports queued follow-ups, and reduces older assistant
reports while retaining the original local transcript. Interruption requires
effect reconciliation before resume; it does not replay uncertain work.

| Requirement | Evidence | Remaining limitation |
| --- | --- | --- |
| Inspect, plan, edit and validate | Real Codex scoped edits passed fixed host tests; matched full/reduced pairs passed three fixtures | These fixtures do not establish representative development quality |
| Follow-up and clean restart | Installed Codex two-turn follow-up and restart checks passed | Long real conversations and complex decision retention remain unverified |
| Physical approval handling | Attended fresh-ticket grant, queued steering and distinct-ticket denial verified | Physical stale-ticket refusal still needs a check; offline refusal already covered |
| Usage-limit fallback | Forced Codex limit followed by real Copilot and Kiro shared edits, host validation and polling the same process handle | Natural exhaustion and current installed-client end-to-end behavior need fresh acceptance; authentication does not prove available allowance |
| Safe partial-effect continuation | Scoped tools, observed effects, protected paths and synthetic quota/overload regressions covered | Native hidden conversation state is not portable; uncertain effects need inspection |
| Automatic allowance observation | Codex/Copilot native quota readers and pinned isolated Kiro estimates | Observe-only, in memory; Antigravity isolation unproved; estimates are not certified remaining balances |
| Long-history handling | Deterministic excerpts retain owner text/outcomes and original reports | Mandatory-context overflow refuses execution; excerpts do not preserve every old assistant plan automatically |
| Timed unattended operation | Execution and continuation deadlines, saved failure handoffs | No host-enforced continuous candidate-selection window; a maximum budget is not a minimum work duration |

Evidence: [acceptance checkpoint](coding-chat-acceptance-results.md),
[roadmap live fallback results](development-roadmap.md#2026-10-06-bounded-live-acceptance),
[conversation guide](coding-chat.md), and the corresponding regression suites.
Ignored artifacts retain raw receipts locally; their paths in those documents are
not public GitHub-hosted evidence. The report does not infer current account quota
or model quality from executable presence or successful authentication.

## Would fallback have prevented today's cutoff?

Possibly, if work had been running inside our CLI, the failed native client had
reported a recognized usage-limit error, and an authenticated, compatible,
same-tier route meeting the selected quality/privacy requirements remained
available. The current IDE assistant conversation is outside that controller:
our CLI cannot recover it merely because fallback code exists in this repository.

Default fallback preserves the declared quality grade, required tools and billing
tier. It does not spend on an unapproved route, override denied actions, invent
allowance, or recover when every eligible route is exhausted. Exhaustion tracking
is scoped to an execution/fallback session; each coding-chat turn creates fresh
execution scopes. It is not a persistent account-wide quota blacklist.

The forced-limit evidence demonstrates the continuation mechanism, not automatic
recovery from the exact usage-limit event that interrupted today's IDE session.

## Shortest responsible migration path

Recommend prioritizing one attended real-work CLI pilot tomorrow, rather than
waiting for every optional tool/provider integration. Keep PyCharm as editor and
temporary tool host, the owner at the approval terminal, strict quality/security,
and the existing same-tier fallback rules. This adds practical experience without
declaring full migration accepted or changing the 20% target's case-by-case review.

1. Select a small real repository task, primary route and eligible fallback routes.
   Confirm permitted repository context, privacy, maximum turns/time and model
   allowance before running it. Do not reuse yesterday's expired grants.
2. Prove the launch configuration and approval path in a disposable synthetic
   workspace. Include explicit stale-ticket refusal. Avoid new logins, installs,
   credential discovery or unsafe native diagnostics as readiness shortcuts.
3. Run inspect/plan/owner correction/edit/test/review on the selected real task.
   Save source/diff, unchanged independent checks, session ID, host receipts,
   route/model settings and outcomes. Test forced-limit continuation separately
   with a bounded synthetic fixture if the owner selects that scope.
4. Owner-review the result against their normal assistant workflow. Extend to
   larger attended work only if the result meets the same quality/security bar.
   Continue the accepted representative baseline/CLI/delegation comparison;
   this pilot alone does not prove parity or economic improvement.
5. Validate unattended operation separately. In particular, a coding-chat turn
   reaching its report returns to `You>`; it does not automatically choose the
   next candidate. `--away-minutes` supplies a per-turn maximum execution budget,
   not a host-enforced two-hour work window. Introducing such a controller would
   require a concrete owner decision about continuation and approval behavior.

Full adoption still needs the agreed representative cases, required installed
tool coverage, restart/fallback acceptance and measured economics. There is no
defensible percentage-complete or hours-to-migration estimate from the current
fixtures. The implementation is available; most remaining migration work is
evidence and operational validation, plus the unattended control gap above.

## Tomorrow's handoff and prompt

End-of-day offline gate: **1,976 passed, 3 Windows file-symlink skips**
(workspace1,862, Council33, job-search81). Pre-commit Ruff check/format passed;
Pyright reported zero errors/warnings; diff whitespace checks passed. The actual
entry-point help smoke passed without model inference. These results verify
software contracts, not model quality, account allowance or live-provider parity.

Recommend making this attended CLI pilot the first objective, with job-search
runtime adoption second. The owner has requested a readiness report; the pilot
scope and any change to the migration plan still need their selection. Prepare
the new-day launch prompt after that choice, rather than publishing commands
with guessed routes, private-data permissions or a fresh model allowance.
