# Invoice + reminders (template notes) — DRAFT

[TO-VERIFY] Field list + KSeF notes with the accountant before first
invoice (see D6). This file is a checklist, not the invoice itself.

## Required fields (PL B2B invoice)

- Sequential invoice number `[OWNER: numbering scheme, e.g. FV/2026/001]`
- Issue date + sale/service date
- Seller: full legal name, address, NIP `[OWNER]`
- Buyer: full legal name, address, NIP (B2B) `[OWNER]`
- Line items: description, quantity, net, VAT rate, gross
- Totals: net / VAT / gross, currency `[OWNER: PLN default]`
- Payment: method, account, due date `[TO-VERIFY: split-payment note rules]`
- KSeF: issuing structured e-invoices is mandatory B2B since 1 Apr 2026
  (micro ≤10k PLN/mo exception ends 1 Jan 2027) `[TO-VERIFY: current status]`

## Reminder sequence (suggestions, owner sets policy)

1. Due-date +3 days: polite nudge, invoice attached again.
2. Due-date +14 days: firm reminder, late-interest notice per contract.
3. Due-date +30 days: final notice before external recovery
   `[TO-VERIFY: required wording + RODO-safe phrasing]`.

## Templates (fill per invoice)

**First reminder**
> Subject: `[OWNER: e.g. Przypomnienie: faktura FV/2026/001]`
> Body: Dzień dobry, przypominam o fakturze `[nr]` na kwotę `[kwota]`,
> z terminem `[data]`. W załączeniu kopia. Proszę o potwierdzenie.

**Firm reminder**
> Subject: `[OWNER: e.g. Ponaglenie: faktura FV/2026/001]`
> Body: Dzień dobry, faktura `[nr]` (`[kwota]`, termin `[data]`) pozostaje
> nieopłacona. Proszę o uregulowanie w ciągu `[OWNER: e.g. 7 dni]`.
> Zgodnie z umową naliczane są odsetki.

**Final notice**
> `[OWNER: accountant-approved wording before use.]`
