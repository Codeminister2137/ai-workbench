# Official-documentation conformance review

**Priority: High. Scope: whole repository. Status: in progress; first Ollama fix
implemented and further bounded findings recorded below.**

The owner prioritized this on 2026-10-11: differences between official documentation
and implementation confuse humans and AI and create later problems. Dropped Ollama
thinking state between tool calls is the first confirmed discrepancy; its repair
does not establish repo-wide conformance or successful coding-quality acceptance.
Group 1 (provider adapters/shared contracts) has several recorded findings below;
the rest of group 1 and the remaining groups are not yet covered.

## Bounded review order

1. Provider adapters/shared contracts: fields, multi-turn tools, continuation,
   streaming, errors, timeout semantics and supported versions.
2. Orchestration/agents: provider limits, fallback, context/token accounting,
   approval/session ownership and lifecycle.
3. Council, job search and automation integrations: API/data contracts,
   authentication, paging/retries and documented SDK usage.
4. Repository tooling: Python/package configuration, CLI usage, dependencies,
   examples and guides.

Prioritize used, failing and high-risk surfaces in reviewable slices alongside
current product work. This does not authorize blanket rewrites, dependency
upgrades, new services or external data transmission.

## Evidence and completion

- Identify installed/supported versions; use primary official documentation or
  versioned upstream source, distinguishing current docs from the version in use.
- Compare actual code paths with focused contract tests, including multi-turn and
  failure behavior. Record reproducible discrepancies and their concrete effects.
- Classify each finding as a bug, stale local guidance, intentional departure or
  unresolved decision. Official examples alone do not mandate an implementation.
- Fix demonstrated bugs and affected guides together. Document valid departures;
  ask at material architecture/privacy/API/dependency boundaries.
- Verify tests/diffs and record remaining limits in the existing handoff/report,
  without adding a tracking system. Use scoped live checks where necessary.

Each slice finishes when its selected contracts conform or have justified,
explicit departures. Whole-repository completion requires coverage of all groups.

## First finding

Ollama's multi-turn examples retain the complete assistant message; streamed
follow-ups include thinking, content and tool calls. Our normalized follow-up
omitted thinking. ADR-055 records explicit transient message metadata as the fix.
Verify roundtrip/privacy/sizing offline and native tool effects live. No quality
gain is inferred solely from documentation alignment.

Sources: [Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling),
[Ollama thinking](https://docs.ollama.com/capabilities/thinking).

## Subsequent bounded findings

Ollama thinking was hidden on `AIMessage` continuation but remained visible in
default `AIResponse` and streaming-event representations through raw metadata.
Those diagnostic fields are now omitted from default representations, preserving
explicit field access, serialization, answers, usage and exact-origin replay.
Regression checks cover both final responses and mixed thinking/text deltas.
This is representation privacy, not deletion of explicit diagnostic data or
proof of live coding quality. See the [interface contract](../packages/ai_provider/docs/interface.md).

The shared process tool advertised argv as an unconstrained array even though its
handler accepts only strings. Optional neutral array-element metadata now survives
agent/provider translation and advertises `items: {type: string}` for that tool.
Existing callers omitting metadata keep their schema. This corrects the published
tool contract; it does not establish the cause of a gateway400 or coding quality.

The 2026-10-13 Codex0.160.1 startup feature notice was classified as fatal despite
its native warning shape. A narrow known-notice fix is implemented and tested;
broader nonfatal-item policy remains an owner decision. See the
[CLI roadmap](repo-assistant/development-roadmap.md).

The Openings bridge rejected valid mixed-case JSON media types. Normalization and
a public export regression now follow [RFC9110 section8.3.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3.1).
This changes no endpoint, credential, posting, approval or persistence boundary.
Whole-repository conformance remains incomplete.

The Council ask endpoint had the same case-sensitive JSON media-type comparison
as the Openings bridge. It now accepts valid mixed-case `application/json`,
including parameters, under the same RFC9110 rule. Real loopback HTTP regressions
retain the streaming contract and existing rejection checks. This changes no
origin, model, persistence or approval boundary.

Requesty's current model catalog exposes cache-write `caching_price`,
`caching_5m_price` and `caching_1h_price` alongside cache-read prices. The existing
free-only checker ignored those write prices. It now checks every advertised
cache price at both model and threshold tiers before completion or streaming;
offline regressions refuse a nonzero price before POST and retain zero-price
behavior. No new account, source, billing fallback or transmission is activated.
Malformed catalog UTF-8 now produces the existing configuration refusal before
inference instead of escaping as an unhandled decoder exception.
Source: [Requesty List Models](https://docs.requesty.ai/api-reference/endpoint/models-list).

Council declared a message-to-conversation foreign key but never enabled SQLite
enforcement. It now enables the existing constraint on every store connection.
Offline checks reject new orphan messages, preserve normal/resumed history, and
retain historical orphan rows without migration or deletion. This changes no
schema or application workflow; [SQLite requires per-connection enablement](https://www.sqlite.org/foreignkeys.html#fk_enable).

The OpenRouter free adapter's request contract was checked against the official
[provider routing reference](https://openrouter.ai/docs/guides/routing/provider-selection)
on 2026-10-22. The `provider` object it sends — `require_parameters: true`,
`data_collection: "deny"` and a zero `max_price` for `prompt`, `completion`,
`request` and `image` — uses the documented field names, types and price
attributes, and the `GET /api/v1/key` fields it reads (`is_free_tier`,
`free_model_daily_requests`) match the documented response shape. The request
guards were already locked by offline regressions, so no code changed.

One deliberate departure is now recorded rather than silently treated as
conformance. OpenRouter documents a separate `provider.zdr` boolean that
restricts routing to Zero-Data-Retention endpoints. It is a stronger claim than
`data_collection: "deny"`, and upstream states that a request-level `zdr` only
ever adds enforcement. The adapter does not request it, because the Free-plan
data-policy entitlement remains unresolved and requiring ZDR could leave the
free route with no eligible endpoint. This is an intentional, documented
departure, not a defect; changing it is a material privacy/routing decision for
the owner. Dated official findings are recorded in
[the provider source state](../packages/ai_provider/docs/source-state.md).

The three OpenCode Go protocol adapters (Chat, Responses, Messages) were checked
on 2026-10-22 against the official [Go endpoint table](https://opencode.ai/v2/docs/console/go/)
and [Inference API reference](https://opencode.ai/v2/docs/console/api/inference/).
Conforming: the Chat endpoint `https://opencode.ai/inference/go/openai/v1/chat/completions`
matches the documented path exactly; `User-Agent: ai_projects/0.1.0` satisfies the
requirement to identify with a project-specific agent rather than a generic SDK or
HTTP-library name; the Messages adapter always sends `max_tokens` (defaulting to
4096), satisfying the documented requirement that it be present; and
`x-opencode-session` is always sent, with callers able to pin a stable id through
`request.metadata["opencode_session"]`.

Two working departures are recorded rather than silently treated as defects.
Responses and Messages use base `https://opencode.ai/inference/go/v1` (yielding
`/responses` and `/messages`), whereas the docs document
`https://opencode.ai/inference/go/openai/v1/responses` and
`https://opencode.ai/inference/go/anthropic/v1/messages`. Separately, the
`_RESPONSES_MODELS`/`_MESSAGES_MODELS` sets route some models to a different
protocol than the current docs table: the docs place `qwen3.8-max`, `qwen3.8-flash`,
`qwen3.7-plus` and `minimax-m3` on Messages and `deepseek-v4.1-flash`/`deepseek-v4-pro`
on Chat, while the implemented sets route them the other way. Both divergences were
live-confirmed on 2026-10-22 — every affected model returned `ok` under the
implemented routing in `docs/artifacts/go-all-model-probe-20261022-rerun.json` — and
the implemented endpoint paths are pinned by `tests/test_opencode_go_protocol_adapters.py`.
No code changed: the implemented paths work, and switching to the documented canonical
paths is unverified without live inference. Recommendation is to keep the current
paths unless live verification is authorized and evidence shows the shorter forms are
deprecated; aligning is a reversible, low-priority follow-up, not a blocker.

A demonstrated bug was found and fixed in the shared Anthropic Messages adapter
(``anthropic_messages.py``, inherited by ``opencode_go_messages.py``). It forwarded
system messages as ``{"role": "system", ...}`` inside the ``messages`` array, but the
[Anthropic Messages API](https://docs.anthropic.com/en/api/messages) accepts only
``user`` and ``assistant`` roles there and requires the system prompt as the top-level
``system`` parameter; sending ``role: "system"`` in ``messages`` is rejected. Because
``coding_assist.py`` builds ``AIMessage(MessageRole.SYSTEM, ...)`` and the factory
routes Messages-protocol models (for example ``claude-haiku-5-5``, ``minimax-m2.7``) to
this adapter, any system prompt on those models would have produced a 400. The adapter
now hoists system messages to the top-level ``system`` field (joined with blank lines)
and keeps only user/assistant turns in ``messages``. A focused offline regression,
``test_messages_client_hoists_system_prompt_to_top_level``, locks the payload shape. The
OpenAI-compatible (Chat Completions) and OpenAI Responses adapters were checked and are
unaffected: Chat Completions and the Responses ``input`` array both accept a ``system``
role natively, so no change was needed there.

A full field-by-field sweep of the two large generic adapters followed. The
OpenAI-compatible Chat Completions adapter (`openai_compatible.py`) conforms: its
request fields (`model`, `messages`, `stream`, `temperature`, `top_p`, `max_tokens`,
`tools`), message/tool-call shapes, `usage.prompt_tokens`/`completion_tokens`/
`total_tokens` reads, and `finish_reason` mapping all match the documented Chat
Completions contract; no change. The OpenAI Responses adapter (`openai_responses.py`)
conformed on its request fields (`model`, `input`, `stream`, `temperature`, `top_p`,
`max_output_tokens`), output/text extraction, streaming event types
(`response.output_text.delta`, `response.completed`) and `usage.input_tokens`/
`output_tokens`/`total_tokens` reads — but it hardcoded ``finish_reason=STOP`` and
ignored the documented ``status`` and ``incomplete_details`` fields. That meant a
response truncated by ``max_output_tokens`` or stopped by a content filter (both report
``status: "incomplete"`` with an ``incomplete_details.reason``) was silently reported as
a clean stop, hiding truncation from callers and acceptance validation. The adapter now
maps ``status``/``incomplete_details.reason`` to the existing ``FinishReason`` enum
(``completed``/absent → ``STOP``, ``incomplete``+``max_output_tokens`` → ``LENGTH``,
other non-completed → ``UNKNOWN``), matching the Chat Completions adapter's convention;
providers that omit ``status`` keep the historical ``STOP`` default. Regression
``test_responses_finish_reason_maps_status_and_incomplete_details`` locks the mapping.

One documented caveat, not a bug: when no session id is supplied the adapters
generate a fresh uuid4 per request. That satisfies the header's presence requirement,
but multi-turn continuity across requests requires the caller to pass a stable
`opencode_session`; otherwise each request is treated as a distinct session. The
adapter docstrings state this explicitly. No new regression tests were added because
no functional gap was demonstrated — every divergence is a working divergence already
covered by existing offline checks. Whole-repository conformance remains incomplete.

The shared Anthropic Messages adapter (`anthropic_messages.py`, inherited by
`opencode_go_messages.py`) had the same truncation-hiding shape in streaming as
the Responses adapter had in completion: `stream()` hardcoded
`finish_reason=STOP` and ignored the documented `message_delta.delta.stop_reason`,
so a `max_tokens` truncation was reported as a clean stop. It now captures that
`stop_reason` and maps it through the existing `FinishReason` enum
(`end_turn`/`stop_sequence` → `STOP`, `max_tokens` → `LENGTH`, other values →
`UNKNOWN`); streams that omit `stop_reason` keep the historical `STOP` default.
The non-streaming mapping adds the documented `stop_sequence` clean-stop value,
which was previously reported as `UNKNOWN`. Regressions
`test_messages_finish_reason_maps_stop_sequence` and
`test_messages_stream_maps_stop_reason` lock the mapping. The provider capability
matrix in `packages/ai_provider/docs/interface.md` is also corrected: Ollama tool
calling is implemented (it sends/parses tools and reports `tools=True`), and
OpenCode Go tool calling is qualified except for Messages-protocol models, whose
adapter does not send/parse tools and reports `tools=False`. No live inference,
routing, privacy, persistence or dependency change follows.

Host review additionally corrected streamed usage accumulation: preserve input
counts from `message_start` while updating cumulative counts from `message_delta`.
The streaming regression now checks both counts and the `stop_sequence` mapping.
Conformance Group 2, slice 1 (2026-11-10): the shared OpenAI-compatible
streaming path never requested usage. OpenAI's [API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and Requesty's [streaming guide](https://docs.requesty.ai/features/streaming)
both state streams carry no `usage` unless `stream_options: {"include_usage":
true}` is sent (final chunk, empty `choices`) — so streamed token accounting
was silently zero on those routes while the reader already handled exactly
that chunk shape. The adapter now sends the flag for OpenAI and Requesty
streams only (`STREAM_USAGE_FLAG_PROVIDERS`, regression
`test_stream_usage_flag_only_where_documented`). Recorded departures, not
defects: Google is excluded on conflicting third-party evidence (one report
of a 400 on this field with default usage); OpenRouter and OpenCode Go Chat
are unverified and keep prior behavior. Verifying either is a bounded
follow-up requiring primary-doc or live evidence.

Group 2 finding 1 (2026-11-13, CORRECTED same day): catalog
`context_limits` ARE consumed — `prepare_native_coding_client` resolves
per-model capacity from them (Ollama fail-closes on unknown runtime
capacity). The original "write-only" claim was wrong: the repo-wide
consumer search hit its match cap and truncated before
`native_admission.py`, and the conclusion was drawn from incomplete
evidence. Likewise the hardcoded 32768s (`agent_executor.py`,
`research_execution.py`) are deliberate conservative runtime budgets
with comments, not drift. Genuine residue: 17/25 routes declare no
limits, so those resolve to unknown capacity (admission proceeds
unverified, per ADR-059's unknown-capacity path). Filling them from
primary sources is a bounded data follow-up. The wire/enforce/drop
brief was withdrawn with this correction. No behavior changed.

Group 2 finding 2 (2026-11-13): clean bill on the fallback path. ADR-059's
20% rule is implemented in `fallback_context.FallbackHistoryClient`
(boundary-tested in `test_fallback_context.py`, incl. the exact 20%
equality case) and wired in the composing CLI, which wraps the native
client when fallback history exists. Capacity flows from catalog limits
via `prepare_native_coding_client` (Ollama fail-closes on unknown).
`fallback_candidates` ordering/privacy/cost docstring matches the
implementation (recommender reuse for acceptance, priority never
relaxes filters, cost escalation opt-in). No divergence found; no
change. Live acceptance of fallback quality remains separately unproved
(as the ADR itself states).

Group 3 finding 1 (2026-11-13): our Openings bridge client verified live.
`openings_api.OpeningsAPI` (previously offline-tested only) was exercised
against the kept service: export page parses to `JobVacancy` rows, and an
identical re-add through `add_posting` collapses to the same job id (the
maintained mirror patch holding over HTTP). Auth contract confirmed both
ways: the client sends `X-Openings-Token` (primary) and the server also
accepts `Authorization: Bearer`. No divergence; the client's strict
response-shape assertions held against real responses. No change.

Group 3 finding 2 (2026-11-13): clean bill on council API controls. Live
loopback probe of the council server verified every README claim:
127.0.0.1-only bind, foreign Origin refused (403), malformed JSON and
missing prompt refused before inference/storage, >512KB body refused,
root serves 200. Probe state removed afterwards (server stopped, temp
config deleted). No divergence; no change.

Group 3 finding 3 (2026-11-14): clean bill on job-email approval
binding. Every ADR-047 boundary holds in code: `materials_digest`
binds recipient, message, attachment identity and exact bytes;
`deliver_application` rejects bypass flags and changed materials and
sends a verified temporary attachment copy (removed after the call);
the `--send` flow adds preview-by-default, exact per-recipient
confirmation and a review-vs-approval digest recheck; sent-file and
record writes stop the batch on failure. `test_email_cli.py` covers
all nine boundary cases (219 job-search tests green). No divergence;
no change.

Group 4 finding 1 (2026-11-13): clean bill on CLI entry examples. The
documented `uv run --no-sync ai-assistant --help` (exit 0),
`--mode plan "..."` (plan metadata, local context only, no inference
observed), `--list-skills` and `--fallback-readiness` (both valid JSON
payloads) all run as documented from the repo root. No divergence; the
remaining Group 4 surface (dependencies, guides, examples beyond the
entry page) is future scope.

Group 4 finding 2 (2026-11-14): clean bill on the getting-started
guide. All ten referenced files exist; `--mode diagnose` prints
readiness JSON (exit 0, no stderr); the documented
`python -m uv run ai-assistant --mode plan` entry point runs as
written (plan metadata, no model contact). The privacy-default
statement matches ADR-085; the dated spending-exemption block is a
labeled example. Remaining Group 4 surface: dependencies. No
divergence; no change.
