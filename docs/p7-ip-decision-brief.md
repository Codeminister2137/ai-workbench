# P7 Track 2.4: IP licensing - reconciled alternatives

Reconciled 2026-11-27 under inbox `52b91c6139f646608224b185a775fbcf` A.
Original proposal: commit `78019a48b70a13d8847374aa6dc0eadd8bdb7fab`.

## Accepted general intent and pending terms

Source `2c9efe65437b493792497d4f807570e0` selected B as general intent:
a broad nonexclusive deliverable licence, retaining reusable templates, with
clients free to choose who maintains and expands their software. The owner wants
both sides to benefit from existing work and to avoid forced dependency.
A/C/D remain negotiable for particular clients. Later owner answers
`6dea3d6d42ef463aaac822135748a8ed` and `900205c04ef94c379ec369164ce0cf0a`
confirm project-source/build/deploy/runbook handover, company-wide business use,
scaling, modification, expansion, integrations and independent appointed
maintenance under confidentiality. Software redistribution/resale/sublicensing
requires separate negotiation and legal review; no blanket enforceability claim
is made. Niche validation and final legal wording remain pending. See the
[reconciled decision](decisions/p7-track24-ip-licensing.md), prepared under
`ba6281ff` A for Tier 3 review. No access to all Workbench internals, assignment,
contract, price or publication is authorized. Accepted answers control over this
historical proposal.

## Viable alternatives

| Option | Pros / client rights | Cons / cost and reuse burden |
| --- | --- | --- |
| A: Assign bespoke deliverables; retain named background assets with sufficient embedded-use licence | Client owns agreed bespoke economic rights and can maintain/commission changes; founder retains Workbench, reusable templates and lawful general know-how. Balanced fit for custom fixed-price builds. | Requires an accurate asset schedule and rights chain. Client ownership does not automatically supply rights to embedded tooling; licence and source handoff must avoid dependency traps. Assigned bespoke code cannot simply be reused by founder. |
| B: Founder retains deliverable ownership; broad nonexclusive client licence | Founder can reuse generic implementation and amortize development, potentially reducing price; client can receive durable use, modification, third-party maintenance and deployment rights. | Some clients/procurement require ownership; client needs strong continuity/transfer rights and confidence against lock-in. Founder must distinguish reusable code from confidential client material. Wider rights and support still cost money. |
| C: Exclusive licence for named bespoke elements, with background carve-outs | Client gets defined competitive exclusivity without a full assignment; field/territory/time restrictions can target a real commercial need. | Exclusivity reduces founder reuse and merits a premium; defining reserved uses and overlaps adds negotiation and monitoring. Client still relies on licence durability; Polish formalities and duration/termination need review. |
| D: Buyout of specifically scheduled bespoke plus reusable components, where rights permit | Client gains strongest control over purchased assets and can reduce supplier dependence; suitable when strategic exclusivity has real value. | Highest price should reflect lost reuse/replacement cost; founder may impair other projects. Cannot assign third-party rights not owned, or already-granted rights away. A broad Workbench buyout needs a separate owner decision and cannot be implied by this option. |

Hosted subscription/access-only delivery is another viable service model: it can
fund ongoing operations and avoid deployment work, but gives the client less
source/continuity control, creates hosting/support/data duties and changes the
offering. Defer it as the default custom-build arrangement; use a separate scope
decision if a client actually wants hosted access rather than a delivered system.

## Required boundary and client-rights schedule

For the selected B intent, prepare a per-project rights schedule for review;
the following require per-project drafting consistent with the accepted scope:

- Bespoke deliverables: named source code, configurations, designs, documentation
  and client-specific workflows. Define the proposed licence scope and effective event; any assignment
  belongs to a separately negotiated A/D alternative, not default B.
- Background assets: pre-existing Workbench, libraries, templates and reusable
  improvements specifically identified before delivery. New generic improvements
  need explicit classification; calling everything a template is insufficient.
- Embedded background rights: propose nonexclusive, worldwide, fully paid rights
  intended to survive the engagement, sufficient to run, copy, deploy, modify and
  engage replacement maintainers for the delivered system. Define affiliate,
  successor/transfer and sublicensing rights and any standalone resale limits.
  Counsel must translate intended durability into enforceable duration/termination
  terms; do not promise an irrevocable licence without review.
- Source/runbook/access handoff and dependency inventory: identify anything only
  hosted by the founder, required build tools and any proprietary dependency that
  would prevent independent operation. Owning output does not grant access to all
  Workbench internals. Agree the necessary handoff before contracting.
- Third-party/open-source assets, fonts, content and AI-assisted material: list
  provenance, licences, notices, restrictions and review evidence; do not promise
  exclusivity or assign rights that the founder does not hold. Assess copyleft and
  provider terms per component and use, not by blanket assurance.
- Client data, marks and confidential processes remain separately protected.
  Retained know-how means general skills and nonconfidential methods; it never
  permits copying client secrets, personal data or confidential code into another
  project, training corpus or portfolio. Portfolio permission is separate.

## Resolution and review boundary

The original recommendation of A is superseded by the owner's B general intent.
Do not reopen the default question. A may suit a buyer requiring bespoke ownership
but reduces founder reuse; C trades targeted exclusivity for additional price and
negotiation; D requires separately valuing lost reuse and checking owned rights.
B supports reuse and client choice but still needs a credible continuity package.
The source-continuity and business-use choices are resolved as recorded above;
per-project implementation, niche validation and legal wording remain pending.

Asset boundaries, confidentiality, third-party rights and legal review remain
required before client use. Counsel must review actual licence scope, form,
duration/termination and modification/maintenance terms. This reconciliation
makes no new legal finding and does not validate the original proposal's legal
sources or approve its candidate rights schedule. Original gate
`p7-track24-ip-terms` records resolved general intent, not final client terms.
