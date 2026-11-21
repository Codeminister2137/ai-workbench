# Mai relay R with host fallback (P2)

Owner P2 answer `3dcbb514` (2026-11-21) requires the entire qualifying fallback
tree, rather than Ollama-only or one fixed model. Credentials and admission stay
on the host; the worker retains `network_mode: none`. Hosted acceptance uses
the separate P1 allowance; this work does not consume or renew it.

## Design selected for supervisor review

Resolve fallback host-side on every inference turn, retaining one host-owned
`FallbackSession` for the run. It delegates ranking to the orchestrator and
remembers failed routes/billing buckets across turns. There is no extra model
count limit. Existing quality, cost, privacy, capability, readiness, exclusion,
deadline and fallback-trigger rules remain authoritative. Full fallback means
all qualifying compatible routes, not bypassing those rules.

Compared with copying a tree into the grant, this keeps current policy, account
observations and failure state on the host and avoids stale worker policy. The
cost is host mediation on each turn. A grant-carried tree could provide a fixed
inspectable snapshot, but would need freshness and policy reconciliation and
still require host admission per attempt. P2 delegates this design choice;
supervisor review and hosted acceptance remain separate from these tests.

## Composition

- Worker: inject `ai_agent.relay_client.RelayChatClient(WorkerClient(mailbox,
  RelayGrant(run_id, policy_id)))` into Mai's existing `AgentLoop`.
- Host: `relay_inference.build_mai_relay(mailbox, grant, fallback_session,
  scoped_execute, privacy=...)` returns a `HostMediator`. Serve each turn while
  supervising the worker. The factory refuses legacy fixed-model bypasses.
- `scoped_execute(target, request)` must enforce live credentials, privacy,
  allowance, shared budget, timeout and cancellation on **every** attempt. It
  returns a neutral `AIResponse`; it must not execute worker tools on the host.
  This seam never creates an unrestricted provider client or treats a mailbox
  grant as funding. Compatible routes must support this neutral inference
  callback; native clients cannot gain host tool-execution authority through it.
- Run/model fields bind the host policy session. Workers cannot choose a target,
  endpoint, metadata override or different privacy class. Payloads carry messages,
  tools, tool-call/result identity, sampling and output settings.
- Responses carry neutral message/tool calls, backend identity and usage.
  Endpoints, raw metadata and opaque continuation never enter mailbox files.
  Continuation stays transiently in bounded request history on the host, is
  restored only for an unchanged observable prefix and removed on a route
  switch. Compaction or rewritten history invalidates it.
- Transport remains single-flight: fixed filenames, atomic publication, request
  IDs, 64 KiB request and 256 KiB response caps. Stream compatibility yields a
  final event; incremental token streaming is not implemented.

This is the inference composition seam, not production dashboard/container
launcher enablement. The worker image must include the new client before rollout.
Workspace import/export, full CLI setup/routing outside `AgentLoop`, lifecycle
supervision, live admission wiring and the wider ADR-095 matrix remain rollout
work. A mailbox wait timeout does not cancel a host call; the scoped executor
and supervisor must enforce cancellation and call deadlines.

## Synthetic proof and limits

`apps/workbench_dashboard/tests/test_relay_inference.py` exercises real Mai
`AgentLoop`, tool dispatch, mailbox files and host `FallbackSession` with
synthetic responses. Three distinct billing buckets fail before the fourth route
succeeds; the next turn carries the tool result and reuses that route. The test
independently reads the file created by `CreateFileTool`. Other cases cover
exhaustion across turns, exclusion, foreign runs, scope injection, deadline
refusal, non-fallback errors and host-only continuation. Existing relay tests
cover caps, bounded failures, response identity and timeout cleanup.

The opt-in native `test_native_container_mai_fallback_proof` uses the existing
Mai image, real tool execution, four-route synthetic host policy, two turns,
a 40-second worker command bound and 20-second teardown bound. For this proof
only it embeds the new client source into the worker program; it does not
rebuild the image or add boundary mounts. This is a proof fixture, not deployment.
It checks the file effect, response, missing default route, refused public/host
connections, minimal boundary mount and clean mailbox. Compose retains its
worker-only, non-root, read-only, capability-dropped, resource-bounded profile.
`receipt.json` records route attempts, worker output and teardown result.

To run it, set `RUN_P2_DOCKER_PROOF=1` and select that test with pytest, using a
fresh `--basetemp` directory whose parent exists. Ordinary runs skip it. These
synthetic checks do not establish hosted compatibility, model quality, production
admission correctness or the full containment matrix.

### Verified run 823dbefecc434dddabf9899e630d40a4 (2026-11-21)

The resumed worktree already contained the composition implementation. Review
added malformed tool-parameter rejection and overload fallback coverage.
The focused relay, execution-fallback and package-layering suite passed
118 tests (one opt-in container test skipped). The separately enabled native
container test passed; its receipt records attempts `route-0`, `route-1`,
`route-2`, `route-3`, `route-3`, two Mai iterations, the file effect,
network checks and teardown exit 0. Local receipt:
`.tmp/p2-proof-823dbefecc43-fresh-20261121/test_native_container_mai_fall0/receipt.json`
in the main checkout. Ruff lint/format checks passed for all five Python files;
targeted Pyright reported zero errors (the worktree has no local `.venv`, so
tools used the main checkout's environment).

Relevant private main-checkout plans inspected: `os-isolation-integration.md`,
`mai-dashboard-wiring-plan.md`, and `interactive-mai-plan.md`. The isolation
plan's older HTTP-proxy direction is superseded for this seam by P2; the other
plans describe subsequent rollout rather than authority to expand this change.

Status: **COMPLETE for the P2 composition and synthetic proof scope**.
Supervisor review, production launcher/scoped-executor integration and hosted
P1 acceptance remain unverified. Next integrate the seam through the existing
scoped admission callback and worker lifecycle; enable production only after
the separate acceptance and containment gates pass.
