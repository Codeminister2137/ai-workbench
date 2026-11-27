# P7 Track 2.3: AI-cost handling ? reconciled alternatives

Reconciled 2026-11-27 under inbox `52b91c6139f646608224b185a775fbcf` A.
Original proposal: commit `78019a48b70a13d8847374aa6dc0eadd8bdb7fab`.

## Accepted decision and remaining boundaries

Source `1ce80f7f35a74b09b60ea01a4fd9e7d4` selected D with clarification:
our code-factory AI is our operating cost within the fixed scoped delivery fee,
never a separate client charge. Attribution is advisory for estimates and margins;
it may inform price and useful disclosure. For a client AI-enabled product,
C (client-owned keys/credits and direct provider billing) is preferred, subject
to the client's choice. Onboarding help does not transfer account responsibility.
Conditional product extraction depends on discovery demand, not immediate build
approval. The [accepted decision](decisions/p7-track23-ai-cost-handling.md)
controls over the original proposal.

The table retains historical alternatives, not pending default choices. Its
production-consumption mechanics must never be applied as delivery-AI charges.
No prices, spending, billing implementation, hard caps, credentials, external
routing, client terms or publication are authorized here.

## Viable alternatives

| Option | Pros | Cons / operational burden |
| --- | --- | --- |
| A: At-cost pass-through with visible usage reports | Client pays actual attributable consumption; avoids hidden risk premium; supports changing workloads without repeated allowance negotiations. | Client total varies and reports alone do not prevent surprise bills; founder fronts spend and reconciles invoices, currency, credits and disputed usage. A separate agreed ceiling/escalation rule is still advisable. |
| B: Capped allowance with pause before overage | Predictable maximum authorized spend per agreed period; clear consent for more spending; bounds founder exposure and fits small initial pilots. | Service can pause and deadlines can move; estimation, alerts, admission controls, in-flight reservations and reconciliation are needed. An included allowance creates under-use/over-use economics that must be defined. |
| C: Client-owned provider account, directly billed; separate integration/support fee | Client controls provider invoices, budgets and continuity after handoff; founder avoids financing/reselling inference; clean cost separation. | Client onboarding, account eligibility and billing remain work; delegated credentials and usage visibility require care. Provider bills still vary; client-side caps and support responsibilities must be agreed. Credentials must not be casually shared. |
| D: Fixed bundled price for a tightly defined workload | Simplest client bill and strongest predictable fee within scope; rewards efficient delivery and removes small per-call billing disputes. | Founder absorbs consumption volatility and must price contingency; narrow volume/model/context limits and change control are essential. Unlimited usage is unsuitable without reliable economics; measuring margins still takes work. |

Prepaid credits are a funding mechanism for A/B, not a distinct cost-allocation
model: they reduce receivables but add balance, expiry, refund and tax accounting.
Metered cost-plus is also viable when a managed-service margin is explicit:
it funds operations but retains variable bills and adds markup disputes; prefer
a separate visible management fee initially. Local inference can reduce external
metering, but hardware, electricity, maintenance and capacity remain real costs;
it is a deployment choice under any option, not free consumption.

## Historical production-only mechanics ? conditional, not approved

The following describes B only if separately negotiated for a client product.
It is not the selected delivery policy or an implementation requirement.

For B, recommend a separately disclosed, project-specific production budget,
actual-cost drawdown with reports, and no automatic overage purchase. State whether
it is prepaid or invoiced in arrears; recommend prepaid for initial pilots with
unused funds reconciled/refunded, subject to accountant/legal review. Do not imply
that a usage estimate is an invoice or that a provider credit is cash expenditure.

Before quoting, specify period/reset/time zone, currency/FX date and fees, taxes,
provider/tool/storage charges included, credits/refunds, failed calls/retries,
abuse liability, attribution, report cadence and dispute process. Recommend
monthly reporting plus a warning before exhaustion; exact budget and warning
threshold remain client-specific, not selected here. Reports should show period,
route/model, attributable usage, estimated versus reconciled cost, remaining
budget and adjustments, without exposing prompts or other clients' information.

Pause admission early enough to reserve worst-case in-flight costs across retries
and fallback routes; if cost cannot be bounded, do not promise a hard ceiling.
Pause AI-dependent operations safely, preserve pending work, explain timeline
effects and require explicit authorized budget increase before resuming. Critical
uninterrupted workloads need a separately agreed reserve or continuity plan.
Provider limits supplement, rather than prove, application-level protection.
Existing tracking is a starting point; no end-to-end client billing or hard-cap
enforcement was tested by this documentation task.

Illustration only, not a quote: a 200-unit monthly budget and 80-unit actual usage
means 80 attributable units under A/B/C; under B the balance treatment follows
the agreed reconciliation rule. At 260 units of requested usage B pauses admission
before the authorized 200-unit exposure is exceeded; a provider invoice or delayed
estimate is not sufficient enforcement. Under D the founder bears permitted
in-scope consumption within the fixed bundle price.

## Resolution and review boundary

The original recommendation of B as the initial default is superseded by D for
our delivery AI and the separate C preference for client-product AI. Do not ask
the owner to select the default again. Client-specific scope, cost allocation,
accountant/legal and data terms still require review before a quote, promise or
charge. The original gate `p7-track23-ai-cost-terms` records the resolved choice.

Provider references in original commit 78019a4 are historical research, not
revalidated by this reconciliation. They establish no current account allowance
or Workbench budget guarantee. See the provider source-state reference before
relying on provider behaviour.
