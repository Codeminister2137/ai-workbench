# Fresh implementation audit and remaining owner choices

**INCOMPLETE roadmap; eligible audit fixes implemented.** Reviewed 2026-10-05
after the owner challenged premature completion. This supersedes the earlier
blanket assertion that wider plans offered no implementation work.

All six private DOCX plans were read: master priorities, provider infrastructure,
Council, job search, business discovery and Orchestrator. The five Markdown plans
covering CLI readiness/parity, common capabilities, research review and token
counting were checked against ADR-040/041/042/043/044 and current code. Their old
unchecked items and resource restrictions were not treated as current decisions.

## Implemented from the fresh audit

| Plan/candidate | Evidence and outcome |
| --- | --- |
| Timed unattended work | Candidate ledger and explicit start/deadline rule added; sleep refuses before a supplied `NotBeforeUtc`. Dry runs verified refusal without sleeping. |
| C3/C5 IDE lifecycle | Entire SDK handshake/discovery/call/cleanup has a 30-second limit. Real heartbeat-stream cancellation and actual PyCharm wrappers passed. |
| C6 foreground continuity | Closed supervisors refuse starts; launch/shutdown races are synchronized. Deleted MCP sessions invalidate queued operations and pending terminal approvals. |
| C4 public documentation | Existing pinned public fetcher is shared with coding routes under existing CUSTOM permissions. Direct shared-host and actual Copilot fetches passed. Slow header/body bytes no longer renew the read deadline. |
| Provider streaming/errors | Both adapters preserve streamed tools; hosted trailing usage survives. Invalid wire/tool data produces normalized errors. Invalid optional counters stay unknown. |
| Usage visibility | Read-only summaries replay explicit local/Codex/Copilot/Kiro receipts without account polling, inferred balances or a new store. |
| Research refinement | Full report reads are paged rather than silently cut at 20,000 characters. A short actual GPT-OSS fixture read both pages of a 23,061-character synthetic report and returned its tail marker. |
| Orchestrator hard constraints | Catalog estimates reject invalid numbers; programmatic NaN/negative/bool latency values cannot bypass a hard task bound. Routing preferences are unchanged. |

The local model fixture took 26 seconds, with three provider calls. Its worker,
runtime and listener were cleaned up. It proves paging plumbing, not improved
research quality, full-instruction capacity or general tool parity. No long
evaluation matrix or global IDE/client setting change ran. One actual Copilot
public-only fixture passed in 13.7 seconds and reported one premium request. It
called our production fetch tool once, recorded HTTP 200 and the body digest, and
returned matching receipt values. Its foreground listener was absent after close.
The prompt contained only the explicit public documentation URL and synthetic
instructions; no private repository content was selected. This does not establish
all-client C4 parity or access to authenticated/private sources.

## Remaining foundation work

Attended terminal acceptance is a required input, not a new architectural choice.
Offline tests cover exact approval, denial, expiry, session deletion and fallback;
an agent-generated `yes` cannot establish a real human interaction. Run a bounded
fixture with the owner present after their return. Keep Antigravity's previously
accepted exclusion until narrow client permissions can be verified.

### Semantic refactoring scope

`ide_bridge.py` forwards interpreter, diagnostics and symbol information only.
The IDE's tested rename operation mutates files; it does not provide an assumed
pre-mutation preview. The exact operation, affected-file scope, approval and
failure/reconciliation contract is still missing.

| Choice | Benefit | Trade-off |
| --- | --- | --- |
| Retain the accepted read-only bridge; design a preview/review contract first | Avoids promising a preview the host cannot supply; ordinary reviewed file edits remain available | Full semantic-refactoring capability remains unfinished |
| Add an explicitly approved IDE rename with post-operation diff review | Delivers actual IDE rename sooner | Approval precedes knowledge of every affected edit; interrupted operations need reconciliation |

Recommendation: retain read-only scope while preparing the concrete preview/review
contract. Owner choice is required before exposing mutation. IDE independence
also needs a selected standalone replacement and dependency contract; the current
bridge does not satisfy that milestone merely because native file tools work.
The subsequent [concrete rename proposal](semantic-refactoring-proposal.md)
compares an optional Jedi preview, direct IDE rename and deferral. Its recommended
two-step contract and dependency remain unapproved; source inspection is complete.

## Wider plans: concrete next-track choices

The master plan favors finished vertical slices and at most two active feature
tracks. Current CLI foundation and research work are those tracks. Do not start
another application solely to occupy an unattended window.

| Candidate | Current code evidence | Decision needed before implementation |
| --- | --- | --- |
| Council synthesis | `council.py` queries members sequentially and preserves raw answers; `agent.py` constructs local Ollama clients. No synthesis/comparison workflow exists. | Select Council as the next track; choose synthesizer/model selection, report behavior and whether synthesis is saved in existing history or exported separately. |
| Job-search vertical slice | `job-email/main.py` sends immediate SMTP messages and records successful addresses. It has no evidence profile, normalized job, material versions or application approval record. | Select first input source, candidate evidence and local application-record format/storage. An existing SMTP login is not approval to send applications. |
| Usage-aware routing | Existing fallback excludes exhausted billing buckets during a run; diagnostics expose recorded consumption. No trustworthy remaining-balance/reset/freshness source exists. | Select the first allowance source and semantics before adding account integration or persisted snapshots. Current usage cannot be subtracted from an unknown starting balance. |
| Business plan | Customer interviews, offer selection, paid pilot and commercial setup are human discovery activities. | Choose a real customer/problem and permitted pilot data; no authority to contact people or invent market evidence. |

Recommendation: finish attended CLI acceptance first. If an application track is
then wanted, start a local-only Council synthesis slice using explicit model
selection and a simple report that preserves all raw answers and minority views.
It reuses existing infrastructure and requires fewer new personal-data contracts
than job-search ingestion. Choose job search instead if that is the owner's higher
product priority. Keep reactive allowance fallback plus receipt diagnostics until
a concrete balance source is selected.

## Deferred acceptance, not implementation permissions to infer

Research review policy D1-D4 already has conditional approval. Keep it opt-in
because the recorded evaluation still has citation/correction defects; do not
ask to reapprove that same policy or activate it on this one plumbing fixture.
The existing long held-out/sustained jobs need a specifically selected compute
allocation. A four-hour implementation window does not silently renew an earlier
one-hour heavy-model allowance. Exact tool-bearing token counting remains outside
the verified tool-free framing contract and needs a concrete compatibility proposal.

Grouped local checks and direct URL fetching are accepted. Jenkins/hosted CI,
new search services, automatic IDE discovery and optional browser/notebook/debugger/
GitHub/visual capabilities are deferred choices, not reasons to stop independent
approved implementation. The current roughly one-minute full gate is manageable.

## Guard limits

For timed runs pass the explicit deadline to the sleep helper. The optional
parameter protects that invocation; it cannot enforce time if omitted, drive the
coding agent itself, or make blocked product work safe to implement. The fresh
per-candidate audit is therefore required before an early completion claim. If
approved work is exhausted before the deadline, report active work and waiting
separately and keep sleep guarded rather than creating speculative work.
