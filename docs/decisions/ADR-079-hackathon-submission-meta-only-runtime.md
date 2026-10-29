# ADR-079: The hackathon submission calls only Meta models at runtime

Status: Accepted by the owner, 2026-10-29. Recorded constraint; the ai-workbench
part of the showcase is still an open sub-decision.

## Decision and intent

The hackathon organizers stated the rule for the final submission: third-party
libraries, APIs and frameworks are allowed within their terms and licences, and
any coding tools may be used to build the project, but **every model the project
calls at runtime must be a Meta model**. The owner accepted that constraint for
our submission on 2026-10-29.

The constraint applies to what the judged artifact does while it runs: the demo,
the hosted service, the judge path and any recording of them. It does not apply
to the tools used to build the project. Development-time use of coding agents,
this Workbench, delegation to other providers and offline analysis remain
permitted, because a reviewer interacting with the submission never reaches them.

Remote Operator already satisfies this by construction rather than by policy
text:

- its CLI accepts only `--model-mode scripted` or `--model-mode meta`, and
  scripted mode calls no external model;
- the live path loads an explicit inference grant, and the grant validator refuses
  a model name that does not match `muse-[a-z0-9.-]+` and refuses any
  `muse-*-contributor` model before a request is built;
- the endpoint is the fixed `https://api.meta.ai/v1/responses` origin, so a
  different vendor cannot be reached by configuration;
- expiry, byte and money limits refuse before the request, which also prevents a
  silent fallback to another provider after a refusal.

Those rules are covered by existing tests, including the refusal cases in
`remote-ai-operator/tests/test_meta.py`. The runtime therefore has no path to a
non-Meta model: there is no provider list, no fallback chain and no key that
switches vendor. Modal runs the validation sandbox and performs no inference, so
it is compute rather than a model provider. The Baseten event alias
`meta-models/muse-spark-open-1026` is a Meta model and is eligible on the same
basis as the direct Meta endpoint.

ai-workbench itself is prior work and is not part of the judged runtime by
default. If it is ever shown as part of the submission, that path must first be
restricted to Meta models; until then it stays out of the demo and the video.

## Alternatives and trade-offs

- Declare the rule, keep the existing grant/CLI guards as the enforcement, and
  verify them in the pre-submission checklist (chosen). Cost is one checklist step
  and a documented inventory; the guards already exist and are tested, so there is
  no second mechanism that can drift from the first.
- Rely on the written rule alone, with no guard and no checklist. Cheaper, but a
  single configuration slip in the demo would be an eligibility violation that
  could disqualify the whole submission, and nothing would catch it before upload.
- Restrict every tool, including development-time coding agents, to Meta models.
  Strongest possible reading, but it is not the stated rule, it would block the
  working development setup that produced the submission, and it would add cost
  with no reviewer-visible benefit.

## Consequences

The submission inventory must keep naming every component that calls a model and
its provider, and the demo path must stay on `scripted`/`meta` only. Any future
component that talks to a model inherits this constraint before it may appear in
the judged runtime. The open sub-decision is whether ai-workbench appears in the
showcase at all; either answer is compatible with this record, but showing it
requires a Meta-only execution profile first.

See [submission eligibility](../plans/remote-ai-operator-2026/SUBMISSION-ELIGIBILITY.md)
for the inventory, the evidence for each row and the pre-submission checks.
