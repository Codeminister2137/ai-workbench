# ADR-099: Gmail reading and class-based send approval

Status: Accepted design, 2026-11-27. Runtime implementation pending.
Source inbox: `1ce1d465084943ed9d2fb30c93689997`.
Closeout run: `d06daaf679294e0892686e4019cd75d9`.

## Owner decision and intent

The owner selected **B: class-based standing approval + audit log** and added:
"Sending mail to our mailboxes should be always allowed, sending anywhere
else needs carefully designed rules". This authorizes mailbox reading and
establishes the owned-mailbox send class. It does not approve intake
confirmations, outreach, or another external-recipient class merely because
those were examples in the question. No additional owner rationale is inferred.

## Authorization classes

| Operation | Accepted boundary |
| --- | --- |
| Read authorized personal Gmail | Standing permission for task-relevant search/read, including full message text; no per-message approval. |
| Send only to verified owned mailboxes | Standing permission, without per-message approval. |
| Send to any other recipient | No standing class approved yet; require explicit approval of the exact message and recipients until carefully scoped class rules are approved. |
| Read a future company mailbox | Apply the design after ownership, account scope and access are configured; this decision does not establish access to that account. |

The owned-mailbox class covers ordinary sends, replies and forwards. It is an
authorization exception independent of message topic or model classification.
Existing notification producers still obey ADR-098's unattended-only hourly
cadence: permission to send is not an instruction to send every notification
immediately or while attended. Existing job-search approval gates remain in
place until deliberately integrated and tested.

"Our mailboxes" means explicit owner-confirmed mailbox identities, including
the authenticated owner account. Do not infer ownership from a matching domain,
contact name, reply history, plus-address, alias, or model assertion. Future
company addresses and aliases need confirmed ownership before joining the set;
no private addresses belong in tracked documentation. This design does not
select a new persistent configuration format or credential mechanism.

Before dispatch, validate the complete final transport envelope: To, Cc and
Bcc, including recipients introduced by reply-all or forwarding. Every recipient
must qualify for the owned-only class. Mixed owned/external sets take the
external path. Ambiguous or malformed recipients cannot receive automatic
authorization. Parse addresses using mail-aware parsing rather than substring
or domain matching; reject header injection. Validate the sending identity too.

Approval of an external message binds its sender, recipients, subject, body and
attachments. Changing any of these invalidates that approval. An email body,
attachment, linked page or classifier cannot grant authority or change rules.
External standing classes need a separate owner-approved rule describing exact
recipient scope, purpose, allowed content/attachments, limits, revocation and
proof cases. Unmatched or uncertain cases remain individually gated. This
decision approves no external automatic sending rule.

## Reading, privacy and transport

Reuse `scripts/mail_digest.py`'s existing read-only IMAP path and credential
resolver. A future `--full` read option must be explicit, leave the current
snippet output unchanged by default, and preserve read-only mailbox behavior.
Do not implicitly download attachments, follow links, mark mail read, delete,
archive or relabel as part of reading permission.

Gmail receives mailbox queries and send payloads through the configured mail
transport. Existing Gmail app-password credentials remain in approved local
secret mechanisms, never in audit records. Reading mail does not authorize
transmitting it to an AI provider. Hosted summarization remains subject to the
existing task/data and inference grants; no new provider, OAuth scope, service,
or inference allowance is approved here.

## Audit contract for runtime implementation

Record authorization attempts and outcomes locally: operation/correlation ID,
UTC time, account reference, read/send class, rule and revision or exact-message
approval reference, allow/deny/pending reason, and transport result. Include a
private recipient-set reference and payload fingerprint for sends, so a reviewer
can connect approval to the final envelope without logging message content.
For reads, record the bounded scope and result count without raw search text.
Record revocations and rule changes as well as successful sends.

Keep subjects, bodies, snippets, attachments, credentials and raw server replies
out of the audit. Mail content remains in the mailbox or explicitly requested
private output, not the general run log. Audit metadata and fingerprints are
private too. Use existing local audit facilities where suitable; storage format,
retention and migration choices are not selected by this design.

Persist authorization evidence before dispatch; an unavailable audit sink blocks
dispatch, including owned-only mail, without demanding fresh owner approval.
Record success, refusal and failure separately. A timeout after submission is
an unknown delivery outcome; reconcile before any retry. Do not promise
exactly-once delivery across a transport/local-record crash boundary.

## Alternatives and consequences

A (per-message approval) gives direct review of every send, at the cost of
owner friction even for owned recipients. B (accepted) removes that friction
for defined classes but requires exact recipient checks and auditable rules;
misclassification could disclose mail. C (read-only/manual send) is simplest
but leaves the owner copying and sending drafts. The source recommended A;
the owner's B answer supersedes that recommendation. The technical follow-through
is deterministic recipient enforcement, with no external class inferred.

## Proving cases before runtime activation

Use fake IMAP/SMTP and a temporary private audit sink. Verify read-only fetch
and explicit full-text behavior; owned-only To/Cc/Bcc and replies/forwards pass
without prompts; mixed sets, lookalike domains, unconfirmed aliases, malformed
headers and reply-all additions cannot auto-send. Verify exact external approval
binding, changed payload rejection, revocation, audit failure before transport,
secret/content-free audit entries, and unknown-outcome retry suppression.
Retest existing job-search gates and ADR-098 cadence independently.

This closeout records the design, not a working general Gmail sender, installed
skill, implemented audit sink, `--full` flag, or live-mail acceptance. Runtime
activation and its proving cases remain a linked implementation follow-up.
