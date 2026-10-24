# Current task - UNATTENDED until 2026-10-24T20:00:00Z; OpenRouter free route declared

Branch: develop. `HEAD == origin/develop == 607ca72` (push of 607ca72 pending at
handoff time; verify before relying on it).
Active unattended window until **22:00 Europe/Warsaw / 20:00Z**, plan at
`docs/plans/unattended-work-plan.md` (Status: ACTIVE).

**Status: INCOMPLETE.** The owner-approved Option A (declare an OpenRouter free
catalog route) is implemented, validated and pushed. Ordinary CLI use of that
route is blocked by an account entitlement question that needs the owner, so it
is declared but deliberately not ordered. Next imperative action: the owner
decision in "Pending owner decision" below; independent work continues in the
window.

## Pending owner decision - OpenRouter free-route entitlement

Decision needed: how the declared OpenRouter free route should become usable for
ordinary CLI work on this account.

Why it matters: the account reports `is_free_tier: true` (no credits ever
purchased), and ADR-063 requires an explicit public/synthetic attestation for a
Free-plan account. The CLI has no attestation flag, so every ordinary CLI request
to this route is refused before inference by the entitlement guard. Because a
`CONFIGURATION` refusal is not a continuation signal, a fallback walk that reaches
the route stops there instead of continuing. The route is therefore declared,
tested and live-probed but not ordered.

Options:
- **A. Buy $10 of OpenRouter credits (owner spends money).** Flips
  `is_free_tier` to false, removes the entitlement refusal and raises the free
  daily ceiling from 50 to 1,000. Pros: the route becomes usable for ordinary CLI
  work with no code or privacy change; also raises quota. Cons: real spend, and it
  treats a credits-purchase proxy as evidence of data-policy entitlement, which
  the source-state notes is not the same claim.
- **B. Add an explicit CLI public/synthetic attestation flag.** Pros: no spend;
  keeps the ADR-063 boundary explicit and operator-controlled. Cons: a new
  user-facing privacy-affecting switch; the operator must assert the whole request
  is public, and the flag could be misused.
- **C. Let a fallback walk continue past a route-level `CONFIGURATION` refusal.**
  Pros: the whole ordered set is honored even when a route cannot serve; no spend
  or privacy change. Cons: changes shared routing policy and contradicts the
  existing `test_other_errors_do_not_switch` contract; could mask a genuine
  misconfiguration by silently switching.
- **D. Leave the route declared and unused.** Pros: zero risk, no decision needed
  now. Cons: the free capacity stays unavailable, contrary to the free-by-default
  preference.

Technical recommendation: **B**, then C if route refusals keep aborting walks.
B keeps the ADR-063 privacy boundary explicit, costs nothing, and makes the route
usable for genuinely public/synthetic work; A spends money and relies on a proxy
claim, while C changes routing semantics for every route.

Owner answer needed: choose A, B, C or D (or another direction) and, if B or C,
the reason to preserve in the ADR.

## Owner authority and current policy

Free routes are preferred by default whenever they meet the task's quality,
privacy, capability and provider requirements (ADR-068, owner statement
2026-10-24: "Always A, by default. More free stuff is good."). Free never waives
a requirement and never authorizes paid overage.

Keep auxiliary review and scrutiny local for now (ADR-025). A wholly paid-tier
workflow is permissible only after evidence establishes local-model inadequacy.
Standing comparable bounded Go acceptance authorization remains; owner confirmed
Extra Usage disabled. No paid overage, unbounded retries, model/billing switches,
new private payloads, raw-prompt/private-reasoning logging or credential exposure.
Closeouts begin with exact `## **SUMMARY**` and Changed/Validated/Notes bullets.

## Completed in this window

OpenRouter free route (commits 40848ee, a635bd0, 607ca72):

- `packages/ai_orchestrator/examples/model_catalog.toml` declares
  `openrouter/free-google/gemma-4-31b-it:free` (`free_only`, 262,144 context,
  tools). `_PRODUCT_SLUGS` gained `openrouter_free -> free`, so the ADR-065
  derivation still reproduces every declared route id (19 routes).
- `scripts/fallback-acceptance.py` gained `--fallback-route openrouter-free`; a
  new test renders every harness route into a loadable catalog.
- `FallbackSession.run` now records `{"route_id", "status": "failed",
  "category"}` for a route whose non-continuable provider error stops the walk,
  so the run record names the aborted route instead of hiding it.
- Dated findings in `packages/ai_provider/docs/source-state.md`: 469 public
  models, 17 `:free`, 16 tool-capable at zero price; the chosen route has exactly
  one free endpoint (Google AI Studio, 262,144 context, zero price).
- ADR-068 records free-by-default; `docs/decisions.md` index updated.

Live evidence (fresh, not a replay):

- `artifacts/fallback-acceptance-20261024-173049/` and
  `artifacts/fallback-acceptance-20261024-174436/`: preserved failures. The walk
  reached `openrouter/free-google/gemma-4-31b-it:free` and stopped on the
  entitlement refusal. The second run records the attempted route with
  `category: configuration` (the first could not, before the recording fix).
- `artifacts/unattended-20261024-1720/openrouter_attested_probe.py`: an attested
  synthetic call passed every adapter guard; account quota was 0/50 used, 50
  remaining; the single upstream endpoint answered **429**
  (`limit_source: upstream_provider_shared_pool`, "temporarily rate-limited
  upstream"). `openrouter_429_diagnosis.py` preserves the body and account data.
  This is upstream capacity, not exhausted allowance, and the adapter maps 429 to
  `RATE_LIMIT`, which a walk already continues.

## Validation in this window

- Full suite: 2846 passed, 9 skipped (before the recording fix); targeted
  fallback suite 192 passed after it.
- Ruff check and format clean; Pyright 0 errors.
- Pushed `develop` at a635bd0; 607ca72 committed after that and its push is the
  remaining step.

## M5 installed-client/live parity - investigated, blocked on allowance

The offline C1-C6 contract in `tests/test_ide_independent_capabilities.py` already
passes without IDE configuration. What M5 still needs is the same approved
capability set exercised through an **installed third-party client** against a real
repository. Both known clients are unavailable for that today:
`github/copilot-cli-auto` has its chat bucket at 200/200 used (0% remaining) and
no configured command, and `kiro/auto` reports its monthly limit reached as a
generic process error. The free and Go routes are provider APIs, not installed
clients, so they cannot substitute.

Blocker: no installed client with remaining allowance. Unlock condition: Copilot
quota reset or a configured Copilot command, Kiro monthly reset, or a newly
installed client. No code change is pending on this; do not re-run the offline
surface checks.

## Consumed live evidence - do not replay or rewrite verdicts

c: `artifacts/cli-baseline-hybrid-successor-20261024c/` FAILED private acceptance
(frozen review lacked receipts). d: `artifacts/local-scrutiny-evidence-20261024d/`
local diagnostic. e: `artifacts/cli-baseline-hybrid-successor-20261024e/`
completed coding and frozen review. f:
`artifacts/cli-bookkeeping-review-20261024f/` completed_with_auxiliary_errors.
g: `artifacts/cli-bookkeeping-attribution-20261024g/`
completed_with_auxiliary_errors, auxiliary contract aligned. Do not replay or
regrade c, d, e, f or g. Slice B live runs:
`artifacts/fallback-acceptance-20261024-151618/` and `-151909/` passed;
`-151449/` is a preserved round-limit failure.

## Fallback ordering

Configurable via `[fallback] priority`/`exclude`/`allow_cost_escalation`,
`--fallback-priority` and `--fallback-exclude`. The local order is Requesty free,
opencode-go, kiro, copilot, antigravity-pro, antigravity-flash, derived from
`artifacts/allowance-inventory-20261024/`. The OpenRouter free route is
intentionally absent from `priority` until the decision above is made. Two
recorded hazards: `kiro_usage` reports plan coverage, never remaining balance, and
hitting any Go account window blocks the whole `opencode-go` provider including
its free models.

Relevant private plans remain repo-assistant-cli-parity-plan.md and
opencode-go-integration-first-20261022.md. Historical trials and earlier failures
remain in `docs/session-history.md`.
