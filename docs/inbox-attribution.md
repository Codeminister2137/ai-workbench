# Inbox attribution

Owner decision 107870329da14bbcb03ffcd685d618e4 approved A+B plus a
harness identity spike (2026-11-27), with A+B as the fallback.

Inbox metadata accepts `author_source`, `author_route` and `author_model`.
Explicit author values take precedence. Rule filings are stamped as `rule`
at the deterministic store/followup/shipping call sites. Unidentified legacy
supervisor filings remain unknown; agent filings display CLI with unknown
model unless explicit identity is supplied. Owner filings display owner.

Run-linked items inherit the latest receipt containing observed route/model
fields, with `attribution_run_id` identifying that execution. The UI labels
this as linked execution, not proof that a model authored a rule-generated
item. Mai emits `effective_model_id` alongside its effective fallback route;
dashboard executor receipts record `model_id` separately from `route_id`.
Session run tracking also records the effective model. Models are never
inferred from route aliases. Reads enrich legacy items without rewriting
history; absent old model observations remain unknown. New filings persist
available inherited metadata. Inbox list and detail expose attribution; the
detail also displays the full item ID.

The C spike found no repository-supported harness session model identity
source and no matching model-identity environment variable names in the
executing process. This does not establish that every external harness lacks
such a facility. No external session logs or private transcripts were read.
The approved A+B fallback applies; CLI model identity remains unknown unless
explicitly provided in metadata. No new identity service or integration was
introduced. Relay composition is not currently connected to dashboard run
execution; its existing tests do not prove a production relay filing path.
