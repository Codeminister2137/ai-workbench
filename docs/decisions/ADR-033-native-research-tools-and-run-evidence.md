# ADR-033 - Native Research Tools And Run Evidence

**Status:** Accepted
**Date:** 2026-10-01

## Context

The unattended research workflow previously received coding tools and accepted
model-authored source declarations. Report structure checks could not prove that
sources were fetched or that the current run wrote the report. External clients
own their tool registries, so selecting our registry cannot constrain them.

## Options considered

- Add a NETWORK permission category and migrate the shared permission contract.
- Use the existing CUSTOM category for explicit public HTTP fetching.
- Continue research through generic shell commands and declarative provenance.

## Decision

The owner accepted the recommendation to use existing CUSTOM permissions and
an explicit provider-native research profile. Coding remains the default.

Research tools perform public HTTP(S) GETs, extract bounded text and links, and
read/write only one configured Markdown report inside the workspace. They
provide no shell, generic repository editing, or delegation. Each redirect is
checked against non-public addresses, and connections use the validated address.
TLS verification remains enabled. Authenticated fetching, ambient proxies,
cookies, and caller-supplied headers are unavailable.

`trusted_local` permits fetching, `read_only` denies it, and `interactive` and
`workspace_write` require approval through their existing CUSTOM policy. Report
writes follow WRITE permissions. The profile requires local-only inference and
cost policy, orchestrated execution, and deterministic validation. External
executors and external fallback are excluded because they cannot preserve this
tool surface.

Use ADR-028's existing implementation-stage JSON metadata for actual fetch and
report-write receipts. No additional persistence schema or store is introduced.
Fetch receipts record requested/final URLs, UTC time, HTTP status, retained-byte
digest, retained length, and truncation. Report receipts record target, UTC time,
and digest. Receipts are persisted at tool execution and shared across repairs.
The completion gate checks fetched source declarations against the current run's
URLs/access dates and requires a matching report-write digest.

## Reason

The recommendation keeps permission and persistence contracts stable while
providing a focused research surface and execution-backed provenance. The owner
accepted that recommendation and explicitly kept CLI refactoring below current
reliability priorities. No further owner rationale was supplied.

## Consequences

- Requested public sites receive URLs, query strings, and ordinary HTTP request
  metadata. Page excerpts go to the selected local model. No cloud AI or search
  service is added, and no credentials are required for source fetching.
- URLs and receipts persist locally in the existing ignored SQLite database;
  fetched page bodies are not stored there. The configured report is local.
- Fetching is bounded to text/JSON/XHTML, standard web ports, five redirects,
  512 KB retained bytes, 12,000 characters of returned text, and 40 links.
  PDFs, authenticated sites, JavaScript rendering, and compressed responses
  are unsupported in this slice. Failures must be reported honestly.
- Receipts prove retrieval and matching report output, not source authority,
  claim entailment, factual truth, or model quality. Honest unfetched/unknown
  entries remain valid. Local database tampering is outside this evidence model.
- The subsequent foreground research supervisor enforces the wrapper's elapsed
  budget by stopping its owned worker tree and recording a durable timeout
  handoff. It preserves the report and receipts and leaves independent Ollama
  servers running. Direct CLI and general coding runs retain scheduling/request
  bounds; shared cancellation for those routes remains follow-up work.

## Amendment - Research defaults and sustained review (2026-10-02)

The owner explicitly approved recording the following inherited decisions on
2026-10-02. The research wrapper defaults to `gpt-oss:20b`, following its prior
native-tool acceptance. Research should repeatedly scrutinize, refine, and repair
within the available budget rather than stop solely at structural success or a
passing review. Reserve final-review time and stop ineffective repetition; do not
idle merely to fill the budget. These controls are implemented, but successful
live acceptance of the combined workflow remains unverified.

Search must follow the selected overall cost policy. Free search is the default;
paid search is an optional alternative, not authorization to incur charges. The
owner's previously stated rationale is that local-model users probably do not
want to spend money, and the owner does not want to spend money either.
ADR-034 records the newly approved SearXNG choice and query-sharing boundary.
The original no-search consequence above describes the implemented fetching
slice, not a prohibition on the subsequently approved search extension.

## Amendment - Advisory report length (2026-10-02)

The owner approved making report length advisory after live receipt validation
found only a length failure in a 6,272-character report. Length is a completeness
heuristic, not a provider constraint or quality measure. The 7,000-visible-character
guideline now produces advice without failing completion or forcing repair.
Mandatory section, source declaration, fetch receipt, and matching report-write
receipt checks remain enforced. Prompts must encourage substantive coverage
without requiring padding or a minimum count.
