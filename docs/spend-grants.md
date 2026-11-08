# Spend grants and policy

How the Workbench controls paid-model spending. All values below are
synthetic examples. Real grants live in the ignored local directory
`apps/workbench_dashboard/data/spend/` and are never committed.

## Grant buckets (`grants/*.json`)

One JSON file per bucket. Required keys: `allowance_id` (letters,
digits, `_`, `-`), `provider` (for example `meta`), `kind`,
`granted_cents` (non-negative integer), and the explicit acceptance
flag `local_spending_limit_accepted: true`. Optional `expires_at`
(unix timestamp or null).

```json
{
  "allowance_id": "meta-free-credits",
  "provider": "meta",
  "kind": "allowance_expiring",
  "granted_cents": 20000,
  "expires_at": 1798761600.0,
  "local_spending_limit_accepted": true
}
```

Kinds, in the order money is spent:

1. `free_daily` — replenishing free quota, spent first.
2. `allowance_expiring` — finite grants (free credits, hackathon
   allowances); soonest expiry first.
3. `prepaid` — real money, spent only when a policy rule permits.

## The free-grant override pattern

Credits that are normally paid but were received for free (hackathon
grants, gifted credits) belong in an `allowance_expiring` bucket, not
in `prepaid`. The dashboard then shows them as a finite free grant
with an expiry, and spending draws them before any prepaid money.
Example: Meta API credits received for free → provider `meta`, kind
`allowance_expiring`, `expires_at` set to the grant deadline.

## Policy rules (`policy.json`)

Prepaid spending is denied by default. To permit it, add `policy.json`
next to `grants/` (same ignored directory):

```json
{
  "rules": [
    {"scope": "global", "prepaid_allowed": false},
    {"scope": "meta", "prepaid_allowed": true, "max_prepaid_cents_per_day": 500}
  ]
}
```

Rules: a scope is `global` or one provider name; `prepaid_allowed`
must be boolean; the day cap is optional. Unknown keys fail closed,
and malformed files fail loud at startup — money never flows on a
misread config. Missing `policy.json` means default-deny.

## Dashboard visibility

The home-page Spend card shows every bucket (status, kind,
balance/granted), open reservations, spend order, today's prepaid
total, and the active rules. `/api/spend` exposes the same view for
scripts. Grant files stay the single editable source; the dashboard
never writes them.
