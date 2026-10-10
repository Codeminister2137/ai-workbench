# ADR-051 - Openings API Integration

**Status:** Accepted direction (2026-10-10); offline bridge implemented, deployment unvalidated

## Context and alternatives

The owner prefers reusing an existing job-search application over rebuilding
discovery and tracking. Openings is the selected primary candidate; open-jobs
remains a possible supplement whose added useful coverage is unproved.

An external API bridge keeps our preparation code independent of Openings
internals, but its pinned manual-import endpoint loses multi-source provenance.
Using the internal collector upsert already retains mirrors, but couples our
integration to implementation and deployment details. A reviewed upstream API
fix resolves the demonstrated defect while keeping the client boundary narrow;
it requires patch maintenance until upstream adopts equivalent behavior.

## Decision and owner rationale

After those trade-offs were presented, the owner approved the recommendation:
**reviewed Openings mirror fix plus external API bridge**. The previously stated
goal is to delegate discovery/tracking and focus custom work on evidence-backed
CV/message preparation and reviewed delivery. No additional rationale is inferred.

The patch targets revision `156dedef348747652a72c961edde3eb103452c6d`.
Intake explicitly uses `new`, never the endpoint's default `shortlisted`.
Tracker statuses do not grant application or email consent. Client methods
accept posting data only; no CV/profile/attachment or delivery operations exist.

## Implementation and limits

The bridge uses explicit numeric loopback host/port and an explicitly supplied
token, without credential discovery, proxies, redirects, retries or automatic
paging. Each call has a total socket deadline and a 2 MiB body cap. Reads
normalize one export page. Writes require an operator assertion that the reviewed
mirror fix was verified; the API does not provide remote attestation. Failed or
ambiguous writes require state reconciliation before any manual retry.

The receiving local Openings app may persist source posting data in its own
existing database. No new repository store/service is introduced; tokens and
response bodies are omitted from client errors. No private candidate data is
transmitted by these methods. The existing human-review delivery boundary remains.

Offline wire tests and a temporary synthetic local HTTP peer exercise the client.
Isolated upstream SQLite probes verify patch semantics with scoring/embeddings
stubbed. This does not establish full application runtime compatibility.
Installation, deployment/authentication configuration, real-data intake, model
calls, upstream publication and open-jobs coverage trials remain separate work.
