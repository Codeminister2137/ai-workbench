# ADR-069 — Restricted reviewed non-sensitive input

**Status:** Accepted, 2026-10-25; implemented and validated offline. First live
synthetic request passed admission and exact-payload checks but received an
upstream shared-pool 429. Live model quality remains unestablished.

## Owner decision and rationale

The owner accepts ordinary non-sensitive repository content for OpenRouter use
for now, provided genuinely private data and API keys are excluded. After an
investigation demonstrated that unrestricted reads/shell output can introduce
secrets, the owner selected A: prepare restricted task access first. The owner
also requested B, general repository protection, in the plans.

A is smaller and easier to verify but supports fewer tasks. B enables general
coding workflows but requires a broader boundary across file reads, searches,
commands, history and fallback. Credits increase allowance without establishing
that boundary; purchase remains deferred and was not authorized.

## Narrow implementation

`ai_agent.reviewed_task` prepares or executes one bounded UTF-8 task file. No
repository context, AGENTS, handoff, skills, session history, tools, subprocesses,
delegation, model continuation, retry or fallback are attached or run. The task
file itself must include every instruction/context byte needed for the task.
Preparation shows only digest, size, target and execution bounds; it sends no
data, constructs no provider client and does not attest review.

Execution requires an explicit non-sensitive-input confirmation and the SHA-256
of the exact text reviewed for possible provider retention/training. The file is
read once into a bounded in-memory snapshot, avoiding a second file read after
checks. A digest mismatch refuses before client creation. Review is a caller
declaration, not a content scanner, proof of public status, cryptographic proof
of human involvement or permission inferred from model output.

The provider-neutral reviewed-input helper creates one USER message with
PUBLIC_OR_LOW_RISK privacy. Request metadata `reviewed_non_sensitive_sha256`
binds that declaration to the exact message. At the OpenRouter admission boundary,
the exception is rechecked: one unnamed USER message, matching digest, bounded
input/output, no tools, tool-call data or private continuation. Adding history,
instructions or results invalidates the review. Metadata is not a wire field or
persistent client consent. Other adapters retain their existing privacy handling.

This is separate from ADR-063. Non-sensitive input may still be private; never
set `public_or_synthetic=True` merely to represent the owner's broader tolerance.
Existing ADR-063 full-public attestation and ordinary unattested/private gates
remain unchanged. Only uncertain Free-plan entitlement is relaxed for the narrow
reviewed request. Zero prices, named free model, quota, authentication, privacy
class checks, `data_collection=deny`, zero price caps and parameter enforcement
remain. No ZDR guarantee, paid retry, purchase or account-setting change is added.

The CLI does not read `.env` or invoke a shell. Credentials come through the
existing adapter environment/configuration path and are sent in the appropriate
authentication header. They are not included in task text by this command.
Callers remain responsible for excluding credentials/private data from the file.
Unverified model output is labelled as such; generated tool requests never run.

## Bounds and deferred work

Input is at most 65,536 UTF-8 bytes. Output defaults to 2,048 and is capped at
8,192 tokens. One inference request is allowed; metadata admission uses the
existing model/key GETs. Each HTTP operation has an explicit 1–120 second timeout
(default 60). This is a per-operation bound, not a hard wall-clock deadline for
the complete command; external unattended admission must reserve all operations,
verification and cleanup. No streaming UI or background worker is introduced.

B is recorded in `docs/repo-assistant/restricted-input-plan.md`; general repository
access, arbitrary command filtering and automatic content classification are not
silently enabled by this narrow path. No new dependency, service, persistent
format or storage is needed.
