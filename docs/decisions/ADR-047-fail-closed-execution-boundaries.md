# ADR-047 - Fail-closed execution boundaries and requirements-based regression tests

**Status:** Accepted; packaging and legacy email entry-point choices remain open

**Date:** 2026-10-08

## Owner decision and intent

The owner requested a repository design and test audit, emphasizing reusable
logic, requirements, long-term stability, edge cases and security before further
authentication/internet work. After reviewing the findings, the owner approved
the recommendations and instructed implementation. This records that approval;
it does not authorize new cloud services, credentials or persistence.

## Boundaries

- Authenticated provider requests refuse all HTTP redirects. Neither credentials
  nor prompts may follow a different origin or a protocol downgrade.
- Recursive repository search skips directory links/junctions and validates every
  resolved file path. These tools are not an operating-system sandbox against a
  concurrent malicious local process changing filesystem links during access.
- Declared tool parameter types, required fields and enum values are validated
  before permission prompts and execution. Unknown keys retain the existing
  schema behavior; individual tools retain semantic and array-item validation.
- Council remains a loopback prototype. Host/Origin validation and bounded JSON
  bodies precede configuration, storage and inference. Non-loopback binding is
  unavailable through its CLI. This is not remote-user authentication.
- Public fetch and search share the response-read watchdog. It enforces a total
  header/body budget even when a server continually sends small amounts of data.
- Application approval binds recipient, message, attachment identity and bytes.
  Guarded delivery rejects bypass flags or changed materials and supplies a
  temporary verified attachment copy to the synchronous transport. That copy is
  removed after the call. No new durable application store is introduced.
- The application lifecycle is still caller-owned: callers must retain the
  returned SENT/FAILED package. This change does not promise persistent or
  concurrent exactly-once delivery from old immutable approved objects.
- Full offline testing includes job-search, Council and root suites. Discovery
  rejects unassigned tests under applications/packages as well as root tests.
- CLI tests call package code directly. Synthetic process execution is injected
  into the real external-client lifecycle rather than substituted by an example.
- Primary, repair and fallback external execution derive settings consistently,
  retaining tool profile, task identity and approval constraints.

## Alternatives and consequences

Following only same-origin redirects would preserve some API compatibility but
requires additional credential/prompt redirect policy. Refusing all redirects is
the smaller explicit boundary; providers must expose their final endpoint.

Checking search's root alone was insufficient for linked descendants. Skipping
directory links avoids traversing external trees and cycles at the cost of not
recursively searching linked directories, including links inside the workspace.

Coercing model arguments appeared convenient but could turn a string "false"
into an overwrite. Invalid arguments now fail visibly without mutation.

Attachment-path approval was insufficient because its bytes could change.
Digest validation plus a verified temporary copy closes the validation-to-send
gap while preserving the existing path-based synchronous transport contract.
Immutable prepared packages do not replace a future durable delivery ledger.

## Open choices

- Optional CLI dependencies through an `ai-provider[cli]` extra versus a separate
  composition package require the owner's explicit selection.
- Routing the legacy email CLI through preview/approval/guarded delivery versus
  disabling its send workflow requires the owner's product selection.
- Broader decomposition of the CLI remains incremental work. Extracting common
  external-execution settings does not claim that the entire CLI is decomposed.

## Verification

Regression tests use synthetic credentials, models, local HTTP servers and
temporary files. They verify rejected effects as well as error responses.
Live model quality, SMTP delivery, cloud authentication and browser-specific
exploitation are outside this offline validation.
