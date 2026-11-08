# Restrictions page live feeders — design note (loop9, idea d79e49b1)

The Restrictions tab is static v1 by design: every dimension is honestly
"not yet evaluated". Wiring live data needs the following, smallest first:

1. **Subprocess execution** (cheapest). Run requests already persist in
   chat session records. Add a store query (count by session/day) plus a
   `/api/restrictions` field. UI shows "N run requests recorded".
2. **Human approval gates.** Inbox approval records exist. Same shape:
   count approvals/denials per dimension tag (needs a tag convention on
   inbox items first).
3. **Delegation scope.** Delegation records exist in chat channel tools.
   Needs a persisted per-delegation scope row before it can be counted.
4. **Outbound network / filesystem / secrets.** No enforcement source of
   truth exists (no egress allowlist, no writable-roots policy, no
   transcript secret-scan). These need new policy + audit code, not just
   wiring. Do not fake them with counts.

Recommendation: implement 1 next (one endpoint + one store query), then
2. Leave 3-4 until the underlying policies exist. Keep the "not yet
evaluated" label on anything without a real feeder.
