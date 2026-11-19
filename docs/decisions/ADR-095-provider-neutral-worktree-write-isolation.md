# ADR-095 - Provider-neutral worktree write isolation

**Date:** 2026-11-19

**Status:** Accepted direction; backend selection pending; enforcement INCOMPLETE.

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

## Backend decision needed

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

Backend choice is filed as inbox `683ccfbf97b9422b927d1b1f2a41de76`, stamped
with registered owner gate `worktree-os-isolation-backend`. Both original sources
retain answered status and an INCOMPLETE resolution; neither is closed as implemented.
Next action: obtain the backend choice and implement its bounded feasibility
prototype. Completion requires the actual containment checks below, followed by
production route integration and host-output mediation checks.

Read-only capability observations on 2026-11-19: Docker and WSL commands are
present, WSL lists Ubuntu and docker-desktop, Docker's selected context is
desktop-linux; `hns` is running and `vmcompute` stopped. The conventional
`C:/Windows/System32/WindowsSandbox.exe` path was absent. These observations do
not prove daemon readiness, feature availability elsewhere or a usable boundary.
No worker, VM, AppContainer profile or ACL grant was created by this investigation.

## Proving checks required before enforcement completion

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
