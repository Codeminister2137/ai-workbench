# ADR-052 - Emergency preservation and quality-preferred fallback

**Status:** Accepted direction; offline implementation, live acceptance pending
**Date:** 2026-10-11
**Partially supersedes:** ADR-042 default and weaker-model authority.

## Context and owner rationale

The attended CLI pilot exposed that declared high-quality alternatives were
unavailable or incompatible. The owner requires delegation and fallback as core
CLI behavior and wants the Orchestrator to choose replacement models. The owner
proposed emergency fallback to preserve completed work, or a quality-preferred
policy that continues on weaker models when stronger models are unavailable,
and explicitly selected both configurable policies. The rationale is preserving
work and avoiding unnecessary fallback blockage without silently weakening quality.

## Decision

- Default `emergency_preserve` first tries normal continuation meeting both the
  task and original route's declared quality floor. If no ready eligible route
  remains, the host saves a deterministic metadata handoff before further inference.
  Weaker eligible routes may then inspect/report only. Native provider preservation
  is a no-tools completion of metadata; official clients use shared inspection
  with read-only permissions and sandbox mapping. No edit, shell, delegation,
  original-task completion, native resume or model-directed cleanup is authorized.
  Route mappings that cannot suppress native shell tools are excluded from
  preservation; current Codex mapping is one such route.
- Existing host-owned process cleanup remains the host's responsibility. A weaker
  model does not acquire cleanup permissions. Failed saves prevent emergency
  inference. No remaining model or deadline still leaves the deterministic handoff.
- Explicit `prefer_quality` ranks stronger eligible routes before weaker ones,
  then permits weaker implementation below the original/task floor. The CLI
  reports downgrade metadata; normal validation and approvals still apply.
- Preserve privacy, same billing tier, capability/latency eligibility, exhausted
  billing buckets, overloaded route exclusions and aggregate invocation deadlines.
  No automatic paid-tier escalation, new service, dependency or quota store.
- Refuse new-policy selection when the original route/model grade is unknown.
  Catalog grades are declarations, not measured quality equivalence; do not
  relabel client-selected `auto` models to manufacture comparable quality.
- The Orchestrator selects models. The owner chooses policy through existing
  `[fallback].quality_policy` or `--fallback-quality-policy`. Existing explicit
  `preserve_quality` and `task_minimum` settings retain their behavior.
- Emergency reporting never changes the original failed outcome into success.
  Save bounded supplemental reporting separately from the original failure and
  receipts. Do not send raw tool arguments/outputs in the preservation prompt.

## Alternatives and consequences

Strict stopping provides a clear implementation quality boundary but cannot
produce model-assisted preservation when only weaker routes remain. Emergency
preservation retains that boundary with restricted reporting, at additional
allowance cost and without completing the original task. Quality-preferred
continuation improves availability but may reduce implementation quality and
requires explicit selection, visible downgrades and unchanged validation.
Both policies preserve owner control rather than forcing manual fallback models.

## Validation and limits

Offline tests cover policy ranking and floors, privacy/billing exclusions,
unknown grades, saved-before-report sequencing, original outcome preservation,
save failure, read-only configuration and native no-tools reporting. These tests
do not establish model quality, natural exhaustion recovery, live account readiness
or migration acceptance. The attended pilot remains a separate evidence gate.
