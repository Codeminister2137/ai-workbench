# ADR-085: Default task privacy external_allowed; user-config holds defaults only

Status: Accepted by the owner, 2026-11-10 (directed in chat; dev standard
is Codex/OpenCode allowances + Meta free credits).

## Decision and intent

The shipped privacy default is `external_allowed` (was `local_only`):
CLI `--privacy`, `UserConfig` base, and `coding_task_profile` default.
Development auto-routes to allowance/free-credit models without a flag;
`--privacy local_only` keeps a run on the machine.

User-config values are defaults, not overrides: case-specific needs win.
Concretely, the dev-mode HIGH quality floor applies unless `--quality`
was explicitly passed, even when user-config sets a quality default;
explicit route/model choice still opts out (deliberate local testing).

Owner rationale (2026-11-10): standard development runs through
Codex/OpenCode allowances + Meta (free credits while they last); the
orchestrator must arrive at that judgment itself. Local-only default
forced every dev run through explicit flags and silently settled tool
work on local models (pilots 2026-11-10).

## Alternatives considered

- Per-run flags only (rejected): forgettable; the default kept routing
  dev work local.
- user-config-only change (rejected): new checkouts/CI keep the shipped
  default; the owner wants the product default to match the standard.
- Keep `local_only` default + carve-outs per mode (rejected): same
  effect with more special cases; the explicit opt-out is one flag.

## Safety posture (explicit)

- Repository contents are now transmitted to external providers by
  default. Sensitive work must pass `--privacy local_only` explicitly.
- Unchanged: no secrets in prompts, credential guards, approval gates,
  cost tiers (user-config ceiling `allowances_allowed` still blocks
  prepaid/billing), shared-inspection read-only (tested on both the
  native and external paths).
- `SENSITIVE_REVIEW_REQUIRED` still refuses external processing.

## Consequences

- Default ask/review/plan/implement routes are external allowance
  routes (codex first by catalog order at HIGH).
- Local runs need explicit `--privacy local_only` (and usually an
  explicit `--quality` or route/model for dev modes).
- Tests pinning the old default were moved to explicit flags; the
  native-path safety test gained an external-path twin.
