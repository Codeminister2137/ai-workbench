# Day digest 2026-11-27 (digest-level report)

Snapshot ~16:30. Company registered (JDG "Jakub Jaworski BeskidLogic",
brand BeskidLogic, inFakt + Beata Witek). Owner cleared a large inbox
 backlog today; P7 offering tracks all decided; U1 UI unification
shipped; intake B1+B2 merged. Beata's question pack sent, answers
pending. Unattended window runs to 22:00 (see
`docs/plans/unattended-work-plan.md`).

## Work state by track

- **Publish chain** (trigger: owner picks — DONE): hosting+mailbox FINAL
  is Cloudflare Pages + Zoho Mail EU (`69a98750` A). Registration guide
  exists (`docs/p7-hosting-mail-registration.md`); registration itself
  is an owner action (`74d4b57d`). Copy tracks decided (`52ccc91a`).
  Remaining code: intake B3 binding, then deploy + live-fire verify.
- **P7 offering**: all tracks decided today — 2.3 AI-cost D (our AI is
  our operating cost), 2.4 IP B (reusable templates, client keeps
  maintenance choice), 2.5 price presentation C preliminary (confirmed),
  regional basis A, Track 3 affordability A, discovery credit A.
  Reconcile of cost/IP proposal briefs approved (`52b91c61` A);
  integration runs tonight.
- **Dashboard UI**: U1 freeText unification + Enter-chat shipped
  (`7543058`). U2 header layout: owner picked B; implementation exists
  on `feature/dashboard-tools-2cdeb7fc`, review+merge tonight.
- **Gmail skill**: design approved (owner B, ADR-099, class-based
  approval, no external auto-send). Branch `docs/gmail-standing-
  approval-design` awaits review+merge; implementation item `71563595`
  runs tonight.
- **Mai**: daily-evidence week 1 due today; fallback/handoff mechanics
  verified (see below).
- **Investor**: Alpaca paper account open and funded ($100k simulated)
  but nothing trades: no execution loop exists yet (ADR-093 explicitly
  records fixtures/profiles/stub-judge only). Engine slices queue for
  tonight after company-ops.
- **Mail/notifications**: hourly owner mail and the 23.11 weekly digest
  were built but SKIPPED by design — mail only sends when supervision
  is `unattended`. Last delivered hourly digest: 23.11. No newsletter
  sender allowlist exists (`digest-sources.json` missing); owner was
  never tasked. Both need owner input (items filed tonight).

## Numbers (dashboard stores)

- Runs: 510 total — 247 completed, 172 failed (diffuse, no dominant
  cluster; top titles x5: Opencode live-proof allowance, sweep E2E
  follow-ups), 72 cancelled, 9 merged, 6 queued (5 failed-run triages
  + 1 drain-paused), 1 needs-attention (sweep E2E follow-up failure).
- E2E promotion reports: 85 — 35 pass, 50 fail.
- Inbox: 1132 total — 1055 closed, 53 open, 24 answered. Open machine
  kinds dominate (18 closeouts, 17 chain reports, 6 run-branch
  reviews); owner-facing remainder is ~10 items.

## Needs owner (filed, answer anytime)

- `74d4b57d` register Cloudflare Pages + Zoho mailbox (guide ready).
- Newsletter senders for the weekly digest (new item tonight).
- Mail policy: should digests/notifications send in attended mode too?
  (new item tonight; currently skipped by design).
- Beata-dependent: VAT, ZUS dates, auth+price, G2 template,
  e-Doreczenia, LGD (pack sent 27.11, answers pending).

## Needs tonight (unattended to 22:00)

U2 + Gmail + attribution merges, P7 reconcile + run-branch review
queue, B3 binding, Mai evidence, digest-button slice, mail-requirement
check, investor first engine slice if company-ops clears. Anything not
done lands in the goal backlog (`data/backlog/`).

## Environment flags

- `%TEMP%` pytest junction re-sticks on every gate run; Dev Mode is
  enabled but needs sign-out/restart to take effect. Pushes use a clean
  `TEMP` override until then.
- Same-checkout concurrency is live (a second session merges P7 work
  into develop); check reflog when the tip surprises you.
