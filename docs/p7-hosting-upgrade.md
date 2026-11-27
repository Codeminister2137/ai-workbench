# P7 hosting upgrade: parked reassessment

Owner instruction, 2026-11-27, inbox `69a987501b794924aa261f37ce1ee7ad`:
use Cloudflare Pages + Zoho Mail EU now; park upgrade conditions and next steps.
This is a manual review gate, not approval to buy or migrate infrastructure.

## Reopen when there is evidence

- Around five concurrent clients: review whether email, meetings and scoped SOWs
  still support ordering, handover and changing requirements. Client count is a
  review signal, not a capacity limit or automatic migration threshold.
- A concrete need for client authentication, shared files, project state or a
  database: establish access, retention, backup and audit needs before a portal.
- Measured function/runtime limits, persistent work, long jobs, storage needs,
  reliability incidents or recurring cost make the current deployment unsuitable.
- A client contract requires stricter EU/Poland localization or the documented
  processing arrangement cannot meet it. EU Zoho mail does not localize Pages
  traffic or lead storage by itself.
- Mail capacity, delivery, client protocol support or collaboration requirements
  exceed the selected Zoho plan. Assess a mail-plan change independently of hosting.

## Steps when reopened

1. Capture the trigger, affected workflow, volume, measured limits/cost, required
   availability, data categories and residency requirements. Do not collect raw
   client content merely to justify an upgrade.
2. Compare staying on Pages with a compatible managed backend against an EU/PL
   managed host or VPS. The former preserves static delivery and reduces server
   administration but adds service limits and integration boundaries; the latter
   gives runtime/control options but adds patching, backup, monitoring and recovery
   responsibilities. An authenticated portal can run on managed services; it does
   not inherently require a VPS. Compare renewal/operations costs, not intro prices.
3. Recommend the smallest change that meets the evidenced requirement. Bring a
   decision brief to the owner covering options, trade-offs, processors/data flow,
   costs, credentials, retention and compatibility. No provider, storage, budget
   or authorization change is approved by this parked item.
4. After approval, document the decision and prepare a staged migration: inventory
   DNS and services, export/back up data, test restore, build a synthetic-data
   staging deployment, test access isolation and end-to-end intake, and define
   cutover/rollback criteria and the owner-visible maintenance window.
5. Cut over only after acceptance, verify HTTPS, mail and form delivery, monitor
   failures and costs, retain a working rollback, and retire old resources only
   after verification and approved retention/deletion handling. Avoid moving mail
   merely because web hosting changes; preserve its MX/authentication records.

Until reopened by the owner, this work remains blocked in the backlog under a
manual gate. Registration and current B3 work continue independently through the
[registration guide](p7-hosting-mail-registration.md).
