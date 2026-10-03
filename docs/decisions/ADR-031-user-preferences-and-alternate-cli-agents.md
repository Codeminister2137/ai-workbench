# ADR-031 - User Preferences And Alternate CLI Agents

**Status:** Accepted

**Date:** 2026-10-01

## Context

The owner needs alternate coding routes because Codex allowance is running out.
The owner explicitly selected a shipped default allowing prepaid credits, a
private preference allowing only subscription allowances, and native automatic
approval for `trusted_local`. Existing project reliability work remains active.

## Decision

- Change the default task cost ceiling to `PREPAID_CREDITS_ALLOWED`. This
  supersedes only ADR-021's default ceiling; its ordered financial boundaries
  and official-client authentication requirements remain in force.
- Store private repo-assistant preferences in ignored `user-config.toml`,
  separate from catalogs, credentials, and shared defaults. Support an explicit
  `--user-config` path. Precedence is explicit CLI flag, user preference, shipped
  default. The first preference is `[defaults].cost_policy`; extend typed
  preference groups when another concrete need appears.
- Keep enum members uppercase, types in PascalCase, and serialized values and
  variables in snake_case. Both allowance and prepaid values follow this rule.
- Classify paid Requesty catalog routes as prepaid credits, not allowances. The
  owner's allowance preference therefore excludes Requesty until an explicit
  `--cost-policy prepaid_credits_allowed` authorizes that run.
- The owner subsequently authorized only free Requesty tests, with no credit
  purchase. Add a separate `requesty-free-gemma-4-31b` route at `FREE_ONLY`.
  Verify the exact model's live input/output, cache, and tier prices before
  every inference request; reject unknown or nonzero prices without inference.
  This preflight is not an atomic server-side price lock. Do not fall back to
  paid models. Keep live acceptance fixtures synthetic.
- Retain Requesty's provider API executor. Use official Antigravity, Copilot,
  and Kiro clients behind the existing external-agent execution adapter. Do not
  extract private subscription credentials or create unofficial API bridges.
- Map `trusted_local` to Antigravity `--dangerously-skip-permissions`, Copilot
  `--allow-all`, and Kiro `--trust-all-tools`. These clients run with native
  permissions and no project-enforced workspace sandbox. Existing Codex mapping
  remains `--ask-for-approval never` with `--sandbox danger-full-access`.
- Other approval presets are not mapped for the three new clients and fail
  before process execution. Codex-specific flags also fail rather than being
  silently ignored. Native client sessions/configuration remain client-owned;
  project-owned resume and session retention controls are deferred.

## Alternatives And Rationale

Direct APIs give the project more control over tools, but do not provide the
same subscription entitlements. Unofficial session-token bridges violate
ADR-021. Official clients preserve entitlement and native agent tools with a
small executor extension; their protocol and lifecycle differences require
explicit normalization and capability-gap follow-up.

The separate preferences file reflects the owner's distinction between product
defaults and personal preferences. Repo-local storage is a reversible first
implementation; cross-project discovery and richer preferences remain future
work. No new Python dependency, daemon, queue, or database is introduced.

## Data And Authorization

Executing external routes sends selected prompt/context and any native tool
results to the selected service: Google Antigravity, GitHub Copilot, Kiro, or
Requesty. Official clients own sign-in; Requesty uses `REQUESTY_API_KEY`.
Clients may retain their own sessions and apply their installed tools, hooks,
MCP servers, and account policies. Automatic approval does not override those
policies. Account overage billing must be controlled in the service account;
the catalog cost tier is a selection boundary, not live billing enforcement.

## Consequences

The CLI has alternate executor paths while preserving provider/orchestrator
boundaries. A configured command is not proof of authentication or entitlement;
live connection checks must be reported separately from deterministic tests.
Capability gaps and blocked account setup belong in `CURRENT_CONTEXT.md`.

## Sources Checked 2026-10-01

- [Antigravity headless protocol](https://antigravity.google/docs/cli/headless/)
- [Antigravity installation and auth](https://antigravity.google/docs/cli/install/)
- [Copilot programmatic reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference)
- [Kiro headless mode](https://kiro.dev/docs/cli/headless/)
- [Requesty free models and daily allowance](https://www.requesty.ai/free-models)
- [Requesty pricing](https://www.requesty.ai/pricing)

Installed Kiro additionally confirmed its actual ACP event stream and existing
sign-in execution; current documentation's API-key requirement does not match
that observed local behavior.
