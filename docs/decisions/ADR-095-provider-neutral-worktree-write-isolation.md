# ADR-095 - Provider-neutral worktree write isolation

**Date:** 2026-11-19

**Status:** Accepted direction and Docker Linux backend prototype selection; enforcement INCOMPLETE.

## Owner decision and intent

Inbox `49413c4932ab454082060b3ad65229f4` selected worktree-only writes.
The owner requested guardrails while retaining useful coding tools, including
analysis of the repository's shared-output directories. Inbox
`bedd17b747a64506ad8358541c660cc5` subsequently selected **B: Provider-neutral
OS isolation**, rather than restricting admission to verified native sandbox
clients. No additional rationale was supplied for B.

The B brief explicitly leaves isolation technology, costs and verification to
selection. This ADR records the direction, not an implemented security guarantee
or approval of a particular backend, credential grant or installation.

## Observed implementation

- `apps/workbench_dashboard/run_isolation.py` creates a retained Git worktree
  and copies `user-config.toml`. Its `.git` file references shared Git metadata.
- `apps/workbench_dashboard/mai_run.py::build_mai_executor` chooses the worktree
  and `run_mai_subprocess` starts Mai with that working directory. There is no
  OS isolation launcher at this seam. In-process execution cannot enforce it.
- File-path checks and a pinned shell working directory do not confine arbitrary
  shell code or descendants. Provider-native sandbox settings cannot establish
  a provider-neutral boundary by themselves.
- Chat has a separate executor/worktree composition path. Both paths, nested
  agents, fallback clients, validation and runtime tools need coverage.
- Generated outputs belong under `artifacts/<run>/`; ongoing state belongs under
  `data/` (project map and architecture). These conventions are not write grants.
  The dashboard also owns progress/inbox/run records under its own data root.

Private plan context inspected: `interactive-mai-plan.md` and
`mai-dashboard-wiring-plan.md` describe dashboard/chat composition;
`mai-supervision-design.md` concerns supervision rather than containment;
`cli-development-readiness-review.md` is historical acceptance context, not an
isolation implementation. None selects an OS backend.

## Proposed execution boundary (not yet implemented)

Place the full task executor and its descendants inside the selected OS boundary,
before model-controlled tools or external clients can execute. Keep the trusted
supervisor outside. Do not sandbox only one shell tool while leaving runtime,
validation, external CLI or fallback paths executing as the owner on the host.

Provide a writable run workspace and private scratch/profile/temp directories
inside the boundary. Keep other worktrees, owner profile and shared state outside
its write authority. Read access and provider credentials must be scoped explicitly;
this write-boundary decision does not expand existing privacy or billing grants.
No Docker socket, broad host mounts, inherited privileged handles, or unrestricted
host-command endpoint may be exposed to the worker.

Git's shared metadata must not receive a general writable host grant. Prototype
with worker-private Git metadata and host-owned import/export of reviewed changes;
prove normal branch/diff/test workflows before selecting its production contract.
Junctions, symlinks, hard links and reparse points must not turn a writable workspace
into write authority over host files.

Shared outputs cross a narrow host boundary: task-scoped artifact publication,
progress events, receipts and source-item resolutions. Reuse existing dashboard
stores and result collection where possible. Publication must validate ownership,
destination, size and link handling; worker text must not become arbitrary host
paths or commands. No blanket write exception for `docs/plans/`, `data/`, dashboard
data or `artifacts/`. Host logs and session bookkeeping remain explicitly distinct
from worker edits. The transport/authentication contract needs design alongside
the selected backend; an unrestricted localhost dashboard API would be a bypass.

Any eventual enforcement path must refuse unavailable/failed isolation and retain
that failure's evidence, with no unsandboxed fallback. Current execution behavior
has not been changed by this ADR. ADR-067's temporary native-client sandbox bypass
is not containment; the future outer OS boundary must contain such clients too.

## Original backend alternatives (before owner answer)

1. **Windows AppContainer prototype (technical recommendation).** Keeps Windows
   Python, PowerShell and native clients, avoids a guest installation and can use
   OS access checks. Costs: Windows-specific launcher/ACL/handle lifecycle work;
   executable, authentication, loopback/network and subprocess compatibility are
   unproven. Private writable profile/temp storage is necessary; a literal rule
   forbidding every write outside the checkout would break ordinary tools.
2. **VM-based worker prototype.** Offers a separate kernel and explicit shared
   folders. Costs: guest toolchain/authentication provisioning, memory/startup,
   lifecycle and host-output transport. A Linux guest changes Windows CLI and
   PowerShell compatibility; a Windows guest has provisioning/licensing questions.
   The actual VM backend still needs selection before installation.

Recommend a bounded, synthetic AppContainer feasibility prototype first, with no
provider calls or broad profile/key grants. It best preserves the present Windows
workflow if it passes. This is a recommendation, not the owner's backend decision.
If compatibility requires weakening containment, return the evidence for a VM
decision rather than silently broadening privileges.

## Backend selected on 2026-11-19

Owner answer on inbox `683ccfbf97b9422b927d1b1f2a41de76` prefers familiar
Docker/Kubernetes infrastructure if suitable, otherwise A (AppContainer).
Docker is suitable for a bounded **Linux worker feasibility prototype** on
Docker Desktop's Linux VM. Select Docker; Kubernetes is unnecessary for one
local worker and is not selected. Owner rationale: existing Docker/Kubernetes
experience. This supersedes the earlier AppContainer recommendation, not the
provider-neutral containment requirements.

Docker offers familiar packaging, reproducible toolchains and explicit mounts.
Costs: Linux does not preserve native Windows executables, guest dependencies
and client authentication need validation, and daemon access is privileged.
AppContainer remains an alternative if Windows compatibility proves essential;
it avoids a Linux toolchain migration but requires custom launcher/ACL work.
A dedicated VM remains stronger kernel separation between workers with higher
provisioning and lifecycle costs. Docker containers share their Linux VM kernel;
selection is not proof of resistance to kernel/container-runtime exploits.

Prototype contract: synthetic local inputs only; pinned existing image; private
Git metadata and writable worker scratch; non-root user, dropped capabilities,
no-new-privileges, read-only root, no network, bounded CPU/memory/PIDs/time.
No Docker socket, host PID/network namespace, privileged mode, owner profile,
credentials or shared Git mounts. Copy a synthetic checkout into private worker
storage; host controls bounded result collection. Prove ordinary coding plus
negative host-write/descendant/link/lifecycle cases before production integration.
No image pull, installation, paid inference or credential provisioning occurred
in this selection closeout. Production authentication/network mediation remains
unimplemented and is not implicitly authorized by backend selection.

Selection checks: `docker context show` returned `desktop-linux`; `docker version
--format '{{json .Server}}'` returned null and a missing named-pipe error for
`dockerDesktopLinuxEngine`. The selected engine endpoint is absent; the command
did not reach a Docker server. This proves no usable server at that endpoint,
not the underlying reason the engine is unavailable. Official troubleshooting
search for that pipe name yielded no result. Do not reinterpret this as Docker
being unsuitable or silently switch to AppContainer. No containment probe ran.
Next action: establish Docker Desktop engine readiness, inspect existing image
inventory, then implement/run the bounded synthetic prototype and preserve an
independent host audit. Do not pull an unreviewed image as a readiness check.

The backend-selection source may close as **decided**. Original enforcement
sources `49413c4932ab454082060b3ad65229f4` and
`bedd17b747a64506ad8358541c660cc5` stay answered/open and INCOMPLETE until the
actual containment and full route/host mediation checks pass.

Read-only capability observations on 2026-11-19: Docker and WSL commands are
present, WSL lists Ubuntu and docker-desktop, Docker's selected context is
desktop-linux; `hns` is running and `vmcompute` stopped. The conventional
`C:/Windows/System32/WindowsSandbox.exe` path was absent. These observations do
not prove daemon readiness, feature availability elsewhere or a usable boundary.
No worker, VM, AppContainer profile or ACL grant was created by this investigation.

## Proving checks required before enforcement completion

### Restricted proxy transport selected and proved (2026-11-20)

Owner approved a model proxy and the four-phase rollout on inbox
`d5e377d5139e48e6bf4753b2030c006c`, then selected **B: restricted network
proxy** on `d2780a18acf840c7960ab9c1800b924f`. This explicitly replaces
`network none` for the future inference-enabled worker with restricted
networking. The owner also requested consideration of Docker Compose because
it is familiar and manages container networks. No further rationale for B
was supplied. Existing provider/privacy/billing admission remains binding.

Compose is suitable for this transport: one project per run, a worker and
its inference endpoint on an `internal` bridge with IPv4/IPv6 gateway mode
`isolated`, no published ports, no default network, and no Docker socket.
An ordinary internal bridge is insufficient: its host bridge address can expose
host listeners. Isolated mode removes that address. These options require a
supporting Docker Engine; failure must refuse execution, never weaken the network.
Both services keep non-root, read-only root, dropped capabilities,
no-new-privileges and CPU/memory/PID limits.

`apps/workbench_dashboard/inference_proxy.py` implements the narrow HTTP
endpoint: one run/model fixed by trusted composition, bearer capability with
expiry/revocation, bounded message-only JSON, bounded replies, and redacted
failures. It has no URL forwarding, CONNECT, dashboard API or worker-selected
provider/model. Tokens/prompts are not access-logged. The trusted completion
callback must retain existing inference admission, cancellation and timeout
policy. Revocation denies subsequent admission; it does not cancel work already
admitted. Responses are currently buffered; streaming is not implemented.

`scripts/docker-proxy-probe.py` generates an exact Compose JSON recipe and
exercises this endpoint with synthetic completions only. It uses the existing
approved image pinned by digest, refuses pulls, retains receipts, and removes
its unique project in `finally`. Synthetic tokens are public test fixtures,
never production capabilities. The probe does not mount a checkout, provider
credentials or host state; only the endpoint source is mounted read-only.

Native evidence on Docker Desktop Engine 29.2.1 / Compose 5.1.0: inference HTTP
succeeded; wrong token, foreign run, dashboard paths, absolute forwarding URLs,
CONNECT, upstream selection and oversized requests were refused. Direct public
IP, external DNS, host dashboard/gateway/loopback and a live host sentinel were
unreachable. A separate trusted bridge control first verified that the same
loopback sentinel was reachable through Docker Desktop. No default route and
the network's internal/isolated settings were independently checked. Cleanup
verified no remaining project containers or networks. Evidence is retained under
`artifacts/docker-proxy-ad7784-host-control/receipt.json` (and the final proof
receipt named in the source-item resolution). This is bounded transport evidence,
not resistance to kernel/runtime exploits or every possible network attack.

Private plans inspected: `os-isolation-integration.md` is the relevant design,
but its saved text is truncated and its localhost/network-none proposal is
superseded by this answer. `mai-dashboard-wiring-plan.md` and
`interactive-mai-plan.md` provide executor/chat context; they do not override
the accepted transport. Unrelated business/provider/evaluation plans were skipped.

The transport decision item may close as **decided and transport-proved**.
Full production integration remains **INCOMPLETE**: the callback has not been
wired to host inference admission across this network, nor have drain/chat,
native-client routing, private workspace import/export, streaming/cancellation,
artifact mediation and the full containment matrix been proved. No production
default is enabled. Keep the design-rollout and original enforcement sources
answered/open; the next action is to implement that admitted host/executor bridge
and run the approved four-phase rollout. Do not interpret this transport closeout
as completion of those separate sources.

Sources checked for the selected network on 2026-11-20:

- [Docker gateway modes](https://docs.docker.com/engine/network/port-publishing/#gateway-modes)
  documents `isolated` on internal networks and the removed bridge address.
- [Compose networking](https://docs.docker.com/compose/how-tos/networking/)
  documents service discovery and isolated internal network composition.

### Host-side provider proxy selected; connection boundary pending (2026-11-20)

Owner selected **B: host-side proxy** on inbox
`98654698af0b458492b0bb74ddd3c5e3`, adding: "I think B, but this decision
needs better pros/cons. Also check our brief instructions cause lack of thos
in decisions is bad". This accepts the deployment direction, not a waiver of
the host-listener containment requirements. No further owner rationale was
supplied; keeping credentials on the host is a technical benefit, not an
attributed owner motive.

The original brief's recommendation of A is superseded by the owner's B.
The omitted trade-offs are:

| Option | Benefits | Costs and risks |
| --- | --- | --- |
| A: egress-allowlisted proxy container | Compose owns lifecycle; provider client is isolated from host processes; worker can retain its internal network. | Credentials enter the proxy container; provider DNS/CDN changes complicate destination restrictions; Compose alone does not implement an API-host allowlist; additional filtering and proof are required. |
| B: host-side proxy (accepted) | Provider credentials and existing admission remain on the host; avoids provider egress and credential distribution in containers. | Adds host process lifecycle and a worker-to-host connection; a host-gateway mapping alone does not restrict destination ports or preserve denial of other host listeners. Windows/Docker Desktop reachability and filtering need native proof. |
| C: defer real inference | Preserves the already-proved synthetic boundary and avoids premature credential exposure. | Does not deliver real worker inference or advance production rollout. |

Technical recommendation: retain accepted B, with explicit connection
containment. The initial statement that worker threat posture is equivalent
under A and B was unsupported: equivalence depends on proving the connection
controls, not merely trusting the host.

**BLOCKED for implementation and final source closure:** the existing isolated
bridge deliberately removes the host bridge address. Replacing it with ordinary
host reachability changes the proven boundary. Bearer authentication protects
the inference endpoint but cannot block requests to unrelated host services.
Do not add unrestricted host-gateway reachability as an implementation detail.

Decision needed: choose how to connect the worker to accepted host-side
inference while preserving denial of other host listeners and public egress.

- **D: filtered direct host connection.** Benefit: follows the source brief's
  direct HTTP topology and avoids a relay. Cost: platform-specific network
  policy, potentially privileged setup, lifecycle/rollback and native IPv4/IPv6
  bypass proof; mapping a hostname is insufficient.
- **R: host-initiated relay on the isolated worker network.** Benefit: worker
  need not receive a route to host listeners; host still owns credentials and
  provider calls. Cost: an additional relay protocol/component, bounded request
  and response mediation, cancellation and cleanup proof. Exact relay transport
  requires design before implementation.

Technical recommendation: R, subject to owner approval, because it preserves
the already-proved worker network rather than relying on new host-wide filter
rules. Neither option is implemented or natively proved by this closeout.
Question: approve R, or choose D and its network-policy setup scope? What
constraint drives the choice? This is a connection decision within B, not a
request to select A/B again. The corresponding dashboard gate is
`proxy-host-connection-boundary`.

Brief instruction audit: `AGENTS.md` (How to ask) and `docs/workflow.md`
already require pros and cons for every viable option and a recommendation.
`scripts/file-brief.py` checks explicit option count, not semantic completeness;
the original brief violated the existing writing rules. No new format or
heuristic prose validator is introduced.

Private plans inspected: `os-isolation-integration.md` remains relevant but
truncated; its transport correction remains authoritative pending this
connection decision. `mai-dashboard-wiring-plan.md` and
`interactive-mai-plan.md` provide rollout context, not permission to expose
unrelated host services. No private plans are present in this run worktree;
these were read from the main repository's local plans.

Official sources rechecked 2026-11-20:
[Docker gateway modes](https://docs.docker.com/engine/network/port-publishing/#gateway-modes)
describe isolated mode's removed host bridge address;
[Docker Desktop host connectivity](https://docs.docker.com/desktop/features/networking/networking-how-tos/)
describes host address resolution. Neither establishes per-port containment.

Next action: implement the owner-selected connection, run synthetic positive
inference and negative host/public/DNS/foreign-run tests plus lifecycle checks,
then perform separately admitted real-provider acceptance. Only close source
98654698 after those results and final diff review establish the selected path.
Prior synthetic container-proxy receipts are not host-side inference proof.

### P2 Mai inference composition (2026-11-21)

Owner answer `3dcbb514` requires full qualifying fallback for in-container Mai
over the proven file mailbox (relay R), with no new worker-reachable endpoint.
Credentials and live admission remain host-side. Owner answer `bd270333`
(Option 1, 2026-11-21) selects host Mai orchestration with isolated worker tools.
The existing inference-only implementation
uses host per-turn `FallbackSession` resolution, retaining failure state
across turns and existing orchestrator policy. This avoids stale policy in
worker grants at the cost of host mediation each turn; a snapshot tree was
considered and not chosen. See the
[design, composition and synthetic proof](../repo-assistant/mai-relay-fallback.md).
That seam leaves `AgentLoop` in the worker and does not implement the selected
host orchestration or external-client tool containment. See the
[placement implementation audit](mai-container-full-fallback.md).
Hosted P1 acceptance and production enablement are separate; supervisor
review (2026-11-21) verified composition, tests and the bounded container
proof. This does not close the full enforcement matrix below.

### Remaining full enforcement matrix

All checks below are **planned, not executed**. Mocks establish composition only;
native checks must run under the actual selected OS boundary.

| Area | Required positive and negative evidence |
| --- | --- |
| Coding tools | File edits, Python, shell, Git branch/diff and tests work inside the worker workspace. |
| Host writes | Create/overwrite/append/rename/delete outside-workspace sentinels fail; independently verify contents, existence and metadata. |
| Escapes | Absolute/relative paths, junction/symlink/reparse traversal, pre-existing hard links, child/grandchild and detached-process attempts remain contained. |
| Routes | Dashboard run, chat, shell/runtime, validation, external clients, delegation and fallback all enter the boundary; no provider-specific bypass. |
| Shared Git | Commits/diffs use private metadata; attempts to mutate the main index, refs, hooks and other worktrees fail. |
| Host mediation | Valid run artifact/progress/resolution succeeds; foreign run/item IDs, arbitrary paths, link escapes, oversized and malformed output fail. |
| Credentials/API | Required approved authentication works; owner profiles, unrelated secrets, host process handles and unrestricted dashboard endpoints remain unavailable. |
| Lifecycle | Startup failure refuses execution; timeout/cancel cleans up the owned process tree, handles and grants; retained evidence survives. |

Retain an independent host audit, exact backend/configuration, checks and results.
No paid/live inference is needed to prove filesystem enforcement. Model-quality
and live-client acceptance remain separate from deterministic containment checks.
Only close the original enforcement source after implementation, proving checks
and final diff review establish the boundary. Until then it remains answered/open.

## Sources checked 2026-11-19

- [Microsoft: AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
  describes file, process and network isolation.
- [Microsoft: Launch an AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
  describes token/capability/ACL setup. This is design evidence, not local proof.
- [Microsoft: Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/)
  describes a disposable VM, separate kernel, explicit guest software installation
  and the current single-instance limitation. That limits its fit for concurrent
  dashboard workers; generic VM isolation remains a viable alternative.

- [Docker Desktop Windows permissions](https://docs.docker.com/desktop/setup/install/windows-permission-requirements/)
  describes the Linux VM boundary and host sharing.
- [Docker Engine security](https://docs.docker.com/engine/security/)
  describes daemon authority and default isolation limitations.
- [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)
  describes writable host sharing; broad bind mounts are excluded here.
