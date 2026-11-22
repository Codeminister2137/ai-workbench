# Shared outputs and write guardrails — design proposal

Date: 2026-11-22. Run: `5ed8bf66682e4a588bcb0a7beea40035`.
Status: design COMPLETE; proposed layout and publication rules await acceptance.
No enforcement, migration, retention policy or new storage contract is implemented.

## Authority and scope

Owner answer `49413c49` selects worktree-only writes while preserving useful AI
tools. [ADR-095](../decisions/ADR-095-provider-neutral-worktree-write-isolation.md)
records provider-neutral OS isolation and the selected Docker Linux prototype;
enforcement remains incomplete. This proposal supplies its shared-output design,
not a replacement backend decision. Related item: `dadde0c4`; its current runtime
record was not independently reconciled for this document.

[ADR-035](../decisions/ADR-035-run-artifact-layout.md) already selects ignored
`artifacts/<run>/` for generated output and `data/` for ongoing state. The
[project map](../project-map.md) agrees. The broader
[logging review](../logging-and-artifact-structure-plan.md) still has unresolved
readability, compatibility and privacy questions; this proposal does not claim
that review or a repository-wide migration is complete.

## Observed output inventory

This is a bounded source/path inventory, not a recursive private-content audit.
The older [writer inventory](../logging-artifact-inventory.md) supplies CLI,
scheduler, Council and outreach detail; its dated observations are historical.

| Output | Current location / writer | Proposed treatment |
| --- | --- | --- |
| Code, docs, patches and task drafts | `.tmp/run-worktrees/<short-id>/`; `run_isolation.py` creates retained worktrees from `develop` | Worker prepares freely within task scope; normal branch review promotes tracked changes |
| Dashboard run reports and receipts | Configured dashboard data root, normally `apps/workbench_dashboard/data/runs/<id>.json`; `DashboardStores` | Remain host-owned authoritative run records; link published evidence rather than duplicate authority |
| Inbox answers, resolutions and closeouts | Dashboard data root `inbox/`; store lifecycle methods | Host applies authorized transitions; a worker's proposed resolution is not an owner answer |
| Progress events | Explicit progress path or configured progress directory, `<id>.jsonl`; `mai_run.py` | Host captures bounded run-scoped events; no worker-selected host path |
| Research, eval and acceptance evidence | `artifacts/<run>/`, including historical scheduled-research and acceptance-jobs identity directories | Keep existing paths/readers; use proposed subdirectories for new publications only |
| CLI receipts and durable conversations | `data/repo-assistant-{runs,chats}.sqlite3`, configured alternatives; stage/session metadata | Preserve existing contracts; do not export full databases into ordinary report bundles |
| Diagnostic and stop receipts | Transcript/log paths, `artifacts/fallback-handoffs/`, mail and power-helper receipt directories | Keep host provenance and existing consumers; expose safe references, not write authority |
| Personal/business working documents | Ignored `docs/plans/`, `docs/library-private/`, client `p7-projects/`; also drafts incorrectly placed under tracked `docs/` | Private staging and reviewed private promotion; directory name or Markdown extension does not establish public suitability |
| Active handoff and history | Ignored `CURRENT_CONTEXT.md`, tracked session history | Worker-local handoff is useful; shared active handoff requires host-mediated task-scoped update |
| Private operational state | Council databases, outreach history, invoices and configured application stores | Remain application-owned; neither generic artifacts nor agent-editable shared files |

The named parked file exists at
`.tmp/run-worktrees/ee0236b6bcf8/docs/business-eligibility-resolution-20261119.md`
in the main checkout (4,978 bytes at inspection). Existence is verified; contents,
authorship, legal correctness and publication suitability were not audited here.
Preserve it in place pending private review; do not merge it into public `docs/`
merely because it is already there in a scratch checkout.

Private planning inputs inspected in the main checkout:
`docs/plans/business-decision-20261119.md` establishes recommendation-only business
drafts and pending owner facts; `docs/plans/eval-scheduling-20261119.md` establishes
route/eval evidence needs. No private facts are reproduced here. Other business
name/funding plans and unrelated application roadmaps were not needed to select
output categories. Neither input grants broader write or provider access.

## Proposed directory layout

Paths below are relative to an explicitly configured host root, never inferred
from a worker's current directory. All new shared publication is host-mediated.

```text
worker workspace (writable only by its run)
  tracked source/docs/...          ordinary task changes
  artifacts/<full-run-id>/outbox/  publication candidates and manifest
  artifacts/<full-run-id>/scratch/ intermediate fixtures, logs, local databases
  private temp/profile/cache/     tool support inside the isolation boundary

host repository (worker has no direct write grant)
  artifacts/<full-run-id>/attempts/<attempt-id>/
    reports/                      readable run/eval reports
    evidence/                     bounded fixtures, metrics, safe diagnostics
    receipts/                     host-issued publication/validation receipts
    manifest.json                 provenance and output index
  data/                           existing CLI operational state, unchanged
  apps/workbench_dashboard/data/  existing dashboard state, unchanged
  docs/...                        reviewed public project documentation

owner-selected private root (worker has no direct write grant)
  outputs/<full-run-id>/<attempt-id>/  private run evidence and drafts
  documents/business/<document-id>/   approved private document revisions
  documents/personal/<document-id>/   approved private document revisions
```

The private root should preferably be outside the repository and cloud-synced
folders. An existing ignored private directory is a viable lower-change option,
but needs ignore/backup/access verification. Neither location is encryption or
an access-control guarantee. Selecting/configuring that root needs owner approval.
Do not create it as part of this design task.

Full run IDs prevent collisions; attempt IDs preserve failed and consumed trials.
Readable labels belong in the manifest/report, not identity-bearing folder names
containing client names or personal details. Existing hashed scheduler paths remain
valid; no automatic renaming or database relocation is proposed.

## Write and approval rules

| Operation | Authority / approval |
| --- | --- |
| Task-scoped edits, fixtures, tests and draft reports inside the worker workspace | Existing task authorization; no approval for each file or ordinary command |
| Worker-private temp/cache/profile writes | Scoped runtime support under isolation; no access to owner-wide profiles or credentials by implication |
| Publish new ordinary run evidence | Trusted host validates task-scoped publication capability and writes a fresh destination; standing task authority suffices within its declared data boundary |
| Publish private evidence | Only to an approved private destination under the existing task/data grant; unknown classification stays local/private pending review |
| Promote private draft to canonical business/personal document | Owner approves document, destination and revision; host preserves prior revision |
| Promote sanitized content into public Git docs | Normal reviewed branch/merge gate plus explicit privacy clearance when derived from private material |
| Record progress or agent resolution | Existing authenticated host store operation restricted to this run/source item; preserves agent authorship and evidence |
| Answer an owner-only gate, expand data/provider access, overwrite unrelated output, delete evidence | Requires the applicable explicit owner authorization; never inferred from task completion |

Keep shell, Python, Git inspection and normal test tooling available inside the
boundary. Avoid per-command allowlists that make ordinary coding impractical.
Use existing scoped runtime tools for application operations; never offer an
arbitrary host-shell or host-file-write endpoint as an escape hatch.

## Publication boundary and evidence

Proposed flow: worker prepares candidate → host validates → host publishes a new
version → host records receipt → dashboard links evidence. Publication failure
leaves the candidate and original evidence intact and reports an incomplete
publication; it must not turn a draft into a verified completion claim.

The host derives run/attempt identity, approved destination and item ownership
from its execution context. Worker requests contain relative candidate names and
output roles, not arbitrary absolute destinations. Reject traversal, drive/UNC
paths, alternate streams, symlinks/junctions/reparse points and hard-link escapes;
copy regular bytes through a confined reader to address validation/copy races.
Validate file count/size limits, ownership, expected types and no-clobber rules.
Limits must be visible before admission; exceeding them requests a scoped change
rather than silently truncating evidence or disabling confinement.

Use host-owned temporary files plus atomic completion, unique attempt paths and
idempotent publication identity. Retries return the same successful receipt or
a conflict; they never overwrite differing bytes. Do not treat a worker-supplied
hash as independent validation: the host computes the published digest.

Recommended manifest facts: run/attempt, source item, producing stage, relative
output role/path, classification, byte count/digest, candidate versus verified
status, validation references, publication time and authority reference. Receipts
distinguish worker authorship, host copying and independent checks. A successful
copy does not verify the document's claims. Preserve original write receipts and
digest-bound relocation mappings when a separately approved migration occurs.

The future transport must authenticate run identity, restrict operations and
resist replay/cross-run requests. An unrestricted localhost dashboard API would
bypass the write boundary. Reuse current stores/result collection before adding
a new service or database. These are proposed contract requirements, not claims
that current stores provide all of them.

## Privacy and lifecycle

Classify personal/business drafts and raw model/client output as private by
default; source facts being public does not make an individual's eligibility or
commercial plans public. Separate approved public excerpts from private originals.
Do not put secrets, raw prompts, private reasoning or unnecessary transcripts in
manifests, dashboard summaries or generic diagnostics. A private path is not
permission to send its contents to a provider. Existing provider/privacy and
billing grants remain independent of local write authority.

Private output should have owner-only filesystem permissions and approved backup
coverage. Git ignore is a publication precaution, not confidentiality protection;
check tracked status before staging. Dashboard links must honor private access
and avoid unauthenticated file serving. Do not expose sensitive names in titles.

Retain failed/consumed evidence and prior revisions. This proposal selects no
automatic expiration or deletion policy. Worktree pruning requires verifying that
needed evidence and drafts have been preserved and that no process owns them;
private retention and erasure need a separate owner decision. Do not quietly
delete the parked business draft after copying it.

## Alternatives and acceptance boundary

Recommended: worktree staging plus narrow host publication. It preserves useful
tools and shared discoverability, with added host validation/transport work.
Keeping everything in retained worktrees is simpler and fits current staging,
but leaves evidence hard to find and vulnerable to later pruning. Direct writable
shared directories are convenient but permit cross-run corruption and contradict
the selected write boundary; they are not a compatible implementation option.

Before implementation, owner acceptance must cover the publication contract and
private destination. This proposal does not create a new standing gate or mutate
dashboard records; any implementation decision request must be surfaced through
the existing dashboard item/gate workflow, not left only in chat. No new ADR is
marked accepted here.

Suggested proving matrix for follow-up: ordinary coding/tests succeed; direct
host/sibling/state writes fail through shell and descendants; valid publication
succeeds without repeated owner prompts; cross-run, traversal, link/race, replay,
oversized and overwrite attempts fail; private content cannot enter public output;
failed publication preserves bytes; concurrent/retried attempts stay distinct;
receipts distinguish authored/published/verified outcomes; owner-only resolutions
cannot be forged. Test every execution route and fallback under ADR-095. These
checks are proposed, not executed by this documentation task.

Design completion condition: inventory, layout, approval/privacy rules and
follow-up verification criteria are recorded. Enforcement and migration remain
separate work; this document does not close `dadde0c4` or certify containment.
