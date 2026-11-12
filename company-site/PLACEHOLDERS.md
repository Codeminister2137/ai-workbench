# Company site placeholders (P7-gated)

Every undecided item the draft needs before launch. HTML carries
`<!-- PLACEHOLDER(ID): ... -->` markers at each site; this file is the
index. A launch is blocked until every ID below resolves or is
explicitly waived by the owner.

## COMPANY_NAME

Legal + brand display name. P7 naming undecided.
Stand-ins: "Firma IT · Skoczów" (PL), "IT studio · Skoczów" (EN),
draft banners note the name is pending. Sites: brand links on all
6 pages. Unblocks: brand links, titles, footer identity.

## CONTACT_EMAIL

Enquiry destination address. P7 contact decision.
The intake form prepares JSON "to attach to an email" but no address
is published. Sites: kontakt.html, en/contact.html (visible pending
line). Unblocks: real enquiries. Mailto wiring follows the address.

## PHONE

Whether a phone number is published at all. Not referenced anywhere
yet. Owner to decide (publish vs email-only). No site changes until
decided.

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

Lawyer + accountant review of master terms before first real SOW,
and one paid accountant hour before the first invoice (see
billing.py docstring). Disclosed on uslugi.html terms section.
Launch gate; not a copy change.

## SELLER_IDENTITY

NIP/REGON/full registered address for footer identity and billing
Party fields. P7 registration decision. Site shows only
"Skoczów, Polska" until then.

## BRANDING

Logo, favicon, og-image. No marks invented (P7 branding decision).
The draft ships without them; a missing favicon 404s harmlessly.

## DOMAIN_HOSTING

Domain + hosting target undecided (`deploy/` is empty). Launch
decision; the site is static + a local JSON intake form.
