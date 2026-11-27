# P7 hosting and mailbox registration

Accepted owner decision, 2026-11-27: inbox `69a987501b794924aa261f37ce1ee7ad`,
option A, Cloudflare Pages + Zoho Mail EU. This guide implements the requested
registration handoff; it is not evidence of registration or deployment.
It supersedes the unselected variants and illustrative DNS values in the private
`docs/plans/site-deploy-runbooks.md` and `site-dns-template.md` for this launch.
The private intake-server design and work-20261127 plan still govern B3.

## Owner: register and configure

1. Confirm purchase/control of the intended domain (currently `beskidlogic.pl`,
   domain item `0fad97a0`). Choose the mailbox local part, still unanswered:
   `kontakt`, your name, or another address. Record the full address on owner
   task `74d4b57d3d5442a7944b8046bc8a7742`; no address is assumed here.
2. Create/sign in to Cloudflare. Enable MFA and save recovery codes privately.
   Add the domain, review the imported DNS records against the registrar's
   existing zone, and save a copy before changes. For an apex Pages domain,
   use Cloudflare nameservers; enter the assigned pair at the registrar.
   Preserve existing mail records until the intended mail cutover.
3. Create a Pages project. Use the verified `company-site/` static output,
   no build command. If connecting Git, limit access to the intended repository;
   follow the approved launch branch/promotion policy, never enable automatic
   publication of unrelated work. A static upload alone does not deploy the
   Python intake core. Preview the output before attaching the final domain.
4. In Pages > Custom domains, add the apex and `www` before configuring their
   DNS targets. Use the values Pages supplies, wait for activation and HTTPS,
   and configure/test a redirect from `www` to the chosen apex URL. Do not use
   a guessed IP or treat a bare CNAME as domain attachment.
5. Start [Zoho Mail EU registration](https://www.zoho.eu/mail/) and confirm
   the organization is in the EU data center before creating the organization
   or importing mail. Check the actual plan, renewal cost, mailbox capacity,
   and SMTP/API availability required by B3; free-plan availability and features
   are not assumed. Owner approves any purchase. Enable MFA and retain recovery
   material privately. Review the applicable processing terms/DPA.
6. Add the domain to Zoho and publish its verification TXT record in the active
   Cloudflare DNS zone. Return to Zoho and verify ownership. Create the selected
   mailbox, then copy **all** MX targets and priorities from this organization's
   Zoho console. At the intended cutover, replace conflicting old MX entries.
   Mail routing records must not be HTTP proxied.
7. Copy Zoho's SPF value and generated DKIM selector/value from the console.
   Maintain one SPF policy, combining authorized senders if any already exist.
   Verify MX, SPF and DKIM in Zoho. Configure DMARC after checking alignment;
   begin monitoring before enforcing quarantine/reject. Only add a report
   recipient you control and have approved; reports themselves disclose metadata.
   Do not copy the older private DNS template as production values.
8. Test inbound mail from an unrelated mailbox, outbound mail and a reply.
   Inspect received authentication headers for SPF/DKIM and DMARC alignment;
   check spam folders and bounces. Record the tested address, time and outcome
   on the owner task, without passwords or tokens. Reply Done only after delivery
   works; otherwise record the failing step.

## Agent follow-through and launch proof

Existing backlog `07521e74ea0c496bbeb50d909e730eae` owns Intake B3: Pages
binding, forwarding and lead storage. Host choice is resolved, but mailbox
readiness, binding compatibility and EU lead storage remain to be verified.
The Python core cannot simply be uploaded as a Pages Function. Investigate a
compatible adapter and present any new runtime, service, persistence or data-route
decision to the owner before implementing it. Do not invent local JSONL disk
durability on a serverless host. Keep this AI work visible on the existing item.

Before launch, validate final copy/contact identity and PL/EN privacy text;
run `python -m pytest tests/test_company_site.py tests/test_intake_server.py`.
Then verify HTTPS on both names, redirects, contact links and the deployed
form's successful reference, mailbox delivery and retained lead. Use a synthetic
lead, verify failure/abuse handling and the offline fallback, and record cleanup.
Static-page success or a JSON download does not prove B3 delivery. Do not publish
a form claiming server delivery before the deployed endpoint passes this check.

Cloudflare receives public site traffic/request metadata; Zoho receives mailbox
contents and mail metadata. EU mailbox selection does not establish EU-only site
processing. The accepted choice is not blanket authorization for new AI routes:
chatbot provider credentials, budget, abuse controls, disclosure and human handoff
need their existing scoped gates before live inference.

For rollback, retain the previous deployment and DNS export. Restore the previous
verified deployment on a site regression; restore old mail routing only when the
previous mailbox still works. Verify both services after any rollback and allow
for DNS caching. Keep secrets and recovery codes out of Git and dashboard notes.

## Official references checked 2026-11-27

- [Pages custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/)
- [Zoho domain verification](https://www.zoho.com/mail/help/adminconsole/domain-verification.html)
- [Zoho mail delivery and data-center-specific MX](https://www.zoho.com/mail/help/adminconsole/configure-email-delivery.html)
- [Zoho SPF](https://www.zoho.com/mail/help/adminconsole/spf-configuration.html)
- [Zoho DKIM](https://www.zoho.com/mail/help/adminconsole/dkim-configuration.html)

Future reassessment: [hosting upgrade conditions](p7-hosting-upgrade.md).
