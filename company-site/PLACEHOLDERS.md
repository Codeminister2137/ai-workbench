# Company site placeholders (P7-gated)

Every undecided item the draft needs before launch. HTML carries
`<!-- PLACEHOLDER(ID): ... -->` markers at each site; this file is the
index. A launch is blocked until every ID below resolves or is
explicitly waived by the owner.

## COMPANY_NAME — RESOLVED 2026-11-26 (owner, inbox f85da96e)

Firma: "Jakub Jaworski BeskidLogic"; brand: "BeskidLogic". Brand
links + footer identity live on all 6 pages. Domain/handle checks:
beskidlogic.pl has no DNS (likely free — confirm at registrar);
no web collisions for "BeskidLogic".

## CONTACT_EMAIL

Enquiry destination address. P7 contact decision.
The intake form prepares JSON "to attach to an email" but no address
is published. Sites: kontakt.html, en/contact.html (visible pending
line). Unblocks: real enquiries. Mailto wiring follows the address.

## PHONE — RESOLVED 2026-11-24 (owner a1a7b4bf)

Email-only: no company number is published (owner's number stays
private; surprise inbound calls unwanted). The intake form collects
the CLIENT's optional phone (E.164) so the owner reaches out.
Reversible if a company number is ever acquired — then add the
published line to kontakt/contact pages.

## SERVICE_CITIES

In-person city list assumed from grounding §1 proposal
(Bielsko-Biała, Cieszyn, Żywiec, Tychy, Katowice edge). Grounding
says "[Owner confirms city list]" with no recorded confirmation.
Sites: index.html radius section + footer, EN equivalents.
Unblocks: launch copy freeze. Re-confirm at launch.

## SITE_VOICE

Grounding §3 open question: recommended default applied
(company-voice "we" on site, personal "I" in direct contact).
Owner may flip to full-"I" everywhere (distinctive craft brand).
No single site; affects all copy on flip.

## MASTER_TERMS_REVIEW

Lawyer + accountant review of master terms before first real Statement of Work (SOW),
and one paid accountant hour before the first invoice (see
billing.py docstring). Disclosed on uslugi.html terms section.
Launch gate; not a copy change.

## SELLER_IDENTITY — PARTIAL 2026-11-26 (inbox 82207bdd)

NIP 5482782178 / REGON 546248869 live in footers + billing Party
fields. Street address (Skoczów, Mickiewicza 25) HELD: publication
needs the AI-investigation + owner deliberation the owner requested.
Site shows city only until then.

## BRANDING

Logo, favicon, Open Graph (OG) image. No marks invented (P7 branding decision).
The draft ships without them; a missing favicon 404s harmlessly.

## DOMAIN_HOSTING

Domain + hosting target undecided (`deploy/` is empty). Launch
decision; the site is static + a local JSON intake form.
