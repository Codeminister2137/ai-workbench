# Judge pool slice — design

Base: `remote-ai-operator` at `cc3577e`. This patch adds an **inert** finite
judge-pool slice: new module plus tests, no wiring, no activation.

## What exists today (researched, read-only)

- Judges are BYOK-only: each judge attaches their own Meta key and sets their
  own finite limits (`PUT /api/judges/grant`, max 100 requests + USD cap)
  stored in their own isolated task store (`JudgeGrantBridge`). The owner
  pays nothing. (`src/remote_operator/judge_grants.py`, `web.py`
  `effective_grant`, `docs/modal-hosting.md` judge section.)
- Key attach is refused without a grant: judges get 409 "Set judge spending
  limits first", visitors 409 "route not configured". (`web.py attach_key`.)
- An owner grant file (`InferenceGrant`, explicit finite allowance, verified
  credits + accepted local limits) takes precedence over self-grants when
  deployed with `--allow-live-inference --grant`. (`meta.py`,
  `grant_from_file`, `cli.py`, `modal_app.py OPERATOR_GRANT_PATH`.)
- Per-request accounting is `Store.reserve_allowance(grant_id, fingerprint,
  maximum, reservation, approved)`: consume-before-send, fingerprint-pinned
  settings, exhaustion refusal, failed calls stay consumed, durable through
  the shared single-writer volume commit. (`store.py`.)
- Admission defaults to disabled everywhere: `MetaModel` raises without
  grant+key, `JudgeGrantBridge.effective` returns None for visitors, missing
  or expired records. (`meta.py`, `judge_grants.py`.)

## Decision

Add `src/remote_operator/judge_pool.py` with three pieces:

1. **`JudgePoolConfig`** — explicit required pool amount. Five fields
   (`grant_id`, `model`, `expires_at`, `max_requests`, `approved_usd`), all
   without defaults so Python itself rejects a missing amount. Validation
   mirrors `InferenceGrant.check` bounds (muse non-contributor model, 1–100
   requests, positive finite decimal-string USD, finite future expiry).
   `pool_config_from_mapping` parses an explicit mapping, names missing
   fields, reads no environment, applies no defaults.
2. **Disabled-until-grant admission** — `JudgePool` holds at most one grant.
   Before `attach_grant`, `effective()` returns None, `reserve()` raises
   `PoolDisabled`, `status()` reports `enabled: False`. Only `judge-*`
   subjects are admitted; visitors always read None; expired grants read as
   absent (mirrors `JudgeGrantBridge.effective`).
3. **Shared-ledger reservation reuse** — the pool takes one shared `Store`
   (one pool file for all judges, single-writer safe) and delegates every
   request to `Store.reserve_allowance` with the pool grant id plus a
   canonical config fingerprint. Fingerprint pinning, exhaustion refusal and
   consumed-on-failure semantics are inherited, not reimplemented.

Deliberately **not** in this slice: any change to `web.py`, `deployment.py`,
`modal_app.py`, `cli.py`, any environment variable, any default amount, any
owner-key handling, any activation. The module is unreachable from the live
app until a later wired slice the owner approves.

## Alternatives rejected

- **Default pool amount.** Rejected: a default would silently fund inference
  the owner never approved. Every amount field is required.
- **Per-judge pool rows summed on read.** Rejected: racy, duplicates ledger
  logic, and breaks the existing consumed-settings pinning. One shared pool
  file reuses `Store` verbatim.
- **Reusing `InferenceGrant` directly as the pool config.** Rejected for this
  slice: it carries `credits_verified` / `local_spending_limit_accepted`
  flags whose meaning for a shared owner-funded pool (whose key? whose
  credits?) is exactly the unanswered owner question below. A narrow config
  keeps the slice honest about what is undecided.
- **Wiring admission into `effective_grant` now.** Rejected: that is
  activation, which the owner has not approved. The pool exposes the same
  `effective(subject)` shape so wiring later is a small additive step.
- **Owner key in the pool module.** Rejected: server-side owner credentials
  are a privacy/billing decision (current rule: "the owner never pays for
  judge runs"). The slice funds nothing and stores no key.

## What needs owner approval

1. **The amount.** Concrete `max_requests`, `approved_usd`, expiry and model
   route for the pool. There is intentionally no suggested value in the
   code; the tests use fixtures only.
2. **Activation.** Wiring the pool into the hosted admission path (order
   vs owner grant and judge self-grants), whose key funds pool requests,
   and whose credits the spend bills. Until approved, the funded judge path
   stays disabled exactly as today.

## Open questions for the owner

- Should a future pool bill an owner key (reversing "owner never pays for
  judge runs") or cap judge keys against a shared counter?
- If activated, what precedence: owner grant > pool > self-grant?
- Should pool consumption be visible to judges (`/api/allowance` scope
  `judge_pool`) or owner-only?
