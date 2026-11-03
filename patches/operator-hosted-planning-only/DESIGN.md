# H1 hosted-drain patch — design

Base: `remote-ai-operator` at `cc3577e`. This bundle implements fix **(b)**
(planning-only enforcement for hosted principals) and scopes fix **(a)**
(hosted multi-subject drain) as a designed follow-up. Fix (a) is **not**
implemented here.

## 1. The verified bug

Approving a plan with `execute=true` through the hosted app queues a supervisor
run job that sits in `queued` forever with no error — a silent dead end.

Evidence (read-only, base commit):

- `src/remote_operator/cli.py`, `serve --hosted` branch: builds
  `ScopedOperators` + `create_hosted_app` and calls `uvicorn.run`. It never
  starts a drain worker.
- `src/remote_operator/cli.py`, local `serve` branch: calls
  `supervise_drain_worker(operator, factory)` and passes a `drain_snapshot`
  into `create_app`. Only the owner path drains.
- `src/remote_operator/web.py`, `_supervisor_routes.approve_plan` (shared by
  both apps): forwards `body.execute` straight to
  `Supervisor.approve_plan`, which writes a `supervisor_runs/<run_id>.json`
  job with `status: queued` (`src/remote_operator/supervisor.py`).
- `src/remote_operator/supervisor_runner.py`, `SupervisorRunner.drain`:
  documented "one worker only" against one operator's store and lock. No
  caller exists on the hosted path — neither a worker thread nor a route —
  so nothing ever reconciles, drains, or refreshes visitor jobs.

Result for judges: plan approved, run "queued", nothing ever happens, no
message explains why.

## 2. Fix (b): planning-only enforcement (implemented)

### Decision

Enforce planning-only for hosted principals server-side, at the shared HTTP
boundary in `web.py`:

- Hosted approve with `execute=true` (including the `PlanApproval` default
  when the field is omitted) returns **409** with `HOSTED_PLANNING_ONLY_MESSAGE`.
- Hosted approve with `execute=false` proceeds and records the plan approval
  with no run queued (`run_id: None`, `status: approved`).
- The 409 is raised **before** touching `Supervisor`, so the pending approval
  survives: the caller retries the same nonce with `execute=false`.
- The owner path is untouched: `execute=true` still queues exactly as before.

### Why server-side, why 409

- The UI already sends `execute` from its run-mode selector (`app.js`) and
  already renders planning-only success, but client state must never be the
  enforcement point: any HTTP client can send `execute=true`.
- 409 matches the codebase's existing "refused state transition" convention
  (`ValueError` → 409 handler, `attach_key` 409s, settings 409s).
- Failing loud beats silent coercion: quietly rewriting `execute=true` to
  `false` would report "approved" while doing something the caller did not
  ask for. The 409 names the mode and the exact recovery action.

### UI flow (no client change required)

`api()` in `app.js` throws `data.detail` verbatim on non-OK responses and
`guarded()` shows it in the message line, so the 409 detail is the UI-facing
text. The constant `HOSTED_PLANNING_ONLY_MESSAGE` pins that contract for
clients and tests:

> Hosted mode is planning-only: runs are not executed here, so this approval
> was not recorded. Approve again with execute=false (planning run mode) to
> record the plan without queuing a run.

### Behavior matrix

| Principal | Request | Result |
| --- | --- | --- |
| Hosted | `execute=true` | 409 planning-only, nothing queued, approval still pending |
| Hosted | no `execute` field (defaults true) | 409, same as above |
| Hosted | `execute=false` | 200 approved, `run_id: None`, nothing queued |
| Owner | `execute=true` | 200 queued, `run_id` set (unchanged) |
| Owner | `execute=false` | 200 approved, nothing queued (unchanged) |

Judge principals (`judge-*` subjects) are hosted principals and are covered by
the same branch — no separate handling.

### Regression tests

`tests/test_hosted_planning_only.py` proves queued jobs are impossible via
hosted approve, checking both the API (`GET /api/supervisor/runs`) and the
disk (`supervisor_runs/*.json` anywhere under the temp root):

1. `execute=true` → 409 with the exact pinned message, zero runs, zero job files.
2. Omitted `execute` → 409, zero runs, zero job files.
3. After a 409 the thread is still `planned`; retrying the same nonce with
   `execute=false` → 200 approved, zero runs, zero job files.
4. `execute=false` → 200 approved, thread `approved`, zero runs, zero job files.
5. The 409 message names the mode and the recovery action (UI contract).
6. Owner `execute=true` still queues (fix is hosted-scoped; no local regression).

### Alternatives rejected

- **Silent coercion** (`execute=true` treated as `false`): lies about what was
  requested; rejected in favor of a loud 409.
- **Enforcing inside `Supervisor.approve_plan`**: `Supervisor` is per-operator
  and does not know the principal; the `who.hosted` flag exists only at the
  web boundary, which is the correct enforcement point.
- **Starting a drain worker for hosted now**: that is fix (a) — a larger,
  riskier change (below). Fix (b) removes the silent dead end today without
  taking on multi-subject execution semantics under time pressure.

## 3. Fix (a): hosted multi-subject drain (designed follow-up, NOT implemented)

Nothing in this bundle implements, wires, or activates a hosted drain. This
section scopes the follow-up so it can be built and reviewed separately.

### Goal

Queued jobs from hosted subjects (visitors, judges) drain to a terminal or
owner-action state (`completed`, `failed`, `cancelled`, `awaiting_approval`,
`waiting_on_owner`) within a bounded number of worker passes, without breaking
isolation, allowance accounting, or single-writer storage.

### Hard problems to solve

1. **Subject enumeration.** `ScopedOperators` resolves subject → workspace but
   lists nothing; workspace dirs are `sha256(subject)` hashes (no PII in
   paths, one-way mapping). Live subjects exist only in the in-memory session
   registry (plus signed-token resume). The design must choose: drain only
   subjects with live sessions (snapshot under the hosted lock), or scan
   `visitors/*/supervisor_runs/*.json` for work (survives restarts but loses
   the subject→grant→key bindings the job needs).
2. **Key continuity.** Visitor/provider keys are process-local by design, never
   persisted, and dropped on logout/restart. A post-restart drain cannot run
   keyed jobs until the subject re-attaches. The design must define job
   parking semantics for missing keys (park with a clear status, never fail
   the job for an environmental absence) and whether scripted/keyless jobs
   drain independently of login state.
3. **Grant resolution per subject.** `effective_grant` is per subject (owner
   grant shared vs judge self-grants per subject store). An owner grant
   consumed across per-subject stores fragments the allowance ledger
   (`Store.reserve_allowance` is per-sqlite-file); the design must define
   where shared-grant accounting lives before draining under it.
4. **Lifting the (b) refusal.** Fix (a) must explicitly relax the 409 — e.g. a
   drain-capability flag threaded from the hosted serve path into the approve
   route — so that `execute=true` 409s when no drain is active and queues
   when one is. Silently reintroducing queueing without the drain would
   resurrect this exact H1.
5. **Notifications.** Owner mail (`notify_send`) is owner-scoped; hosted
   subjects have no mailbox. Hosted drain outcomes surface through the
   existing per-subject run-status APIs only, unless an explicit opt-in mail
   path with abuse caps is designed separately.

### Concurrency and lock considerations

- **One subject lock at a time.** `Operator.lock` is a per-subject-dir
  `ProcessLock`; `SupervisorRunner` assumes one operator/lock ("one worker
  only"). The sweeper must never hold two subject locks at once: sequential
  per-subject passes (reconcile → drain → refresh) preserve the existing
  single-writer-per-directory invariant. No lock ordering scheme is needed if
  nesting is simply forbidden; assert or structure the code so nesting is
  impossible.
- **Single sweeper thread, round-robin.** Prefer one daemon sweeper (mirroring
  `start_drain_worker`/`supervise_drain_worker`) iterating subjects
  round-robin over one-thread-per-subject: thread count then stays constant
  under unbounded subject growth, and per-pass budgets compose. Per-subject
  parallelism would additionally need an atomic job-claim protocol (the
  current claim — write `status: running` to the job file — assumes a single
  worker) and is rejected for the first version.
- **Bounded budgets, busy-tolerant sweep.** Cap subjects-per-pass,
  jobs-per-subject-per-pass, and total pass wall-time. A subject whose lock
  is busy (or whose dir is unreadable) is skipped with a counter, never
  allowed to stall the sweep; `OPERATOR_BUSY` already releases claims
  (`_release_claim`) — reuse that path.
- **Key-borrow races.** The model actor borrows the session key per request;
  logout/revocation mid-drain raises `SessionUnavailable`. The drain must
  catch that at the job boundary, park the job as queued/waiting with a
  "key detached, re-attach to resume" note, and continue — never mark the
  job failed for revocation, and never retain the borrowed key past the call.
- **Fairness and starvation.** Round-robin with per-subject caps prevents one
  subject's backlog from starving others. Track per-subject consecutive skips
  (busy/missing-key) for observability; consider jittered ordering only if
  adversarial subject timing is in scope (it is not for the first version).
- **Crash safety.** Reuse `reconcile_jobs` per subject before draining it
  (never replay); keep `_finish_job`'s notify-never-breaks-the-drain
  discipline for any new per-subject bookkeeping.
- **Storage single-writer.** Each subject `Operator` carries its own store and
  optional `durable` commit hook through `ScopedOperators`; sequential passes
  keep the Modal single-writer volume discipline intact. Parallel writers
  across subject dirs would need volume-level review first.
- **Observability.** Extend `DrainWorkerStatus` with per-pass subject counts
  (drained/skipped/busy/key-missing) for the owner window; subjects keep
  reading their own runs via the existing run-status APIs.

### Acceptance criteria for (a)

- A queued hosted job reaches a terminal/action state within N sweeper passes.
- Two subjects with backlogs both make progress (fairness test).
- Logout mid-drain parks the job; re-attach resumes it (no failure, no replay).
- Restart without keys parks keyed jobs with a clear status; scripted jobs
  still drain (or are explicitly defined not to).
- A lock-busy subject is skipped without stalling others.
- No cross-subject leakage: job files, tasks, keys, and grants stay bound to
  their subject (negative test: subject B cannot read subject A's runs).
- `execute=true` 409s when the drain is disabled and queues when it is
  enabled (the (b) refusal becomes drain-conditional, covered by tests).

### Non-goals for (a)

Persisting provider keys, cross-subject priorities, owner-funded inference
(see the judge-pool funding decisions), and per-subject mail.

## 4. Why (b) is safe to apply

- Two added behaviors, both hosted-gated on the existing `who.hosted` flag;
  the owner route returns through the identical call as before.
- No new dependencies, no storage or schema change, no background threads, no
  config, no secrets, no network, no inference.
- The 409 reuses the app's existing `HTTPException` → `{"detail": ...}` path
  that the UI already renders.
- Regression tests pin both the refusal and the unchanged owner behavior, at
  the API and on-disk levels.
