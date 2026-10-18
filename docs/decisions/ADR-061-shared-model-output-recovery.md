# ADR-061 — Shared model-output correction within the original allowance

**Status:** Accepted and implemented offline (2026-10-18); live acceptance incomplete.

## Owner decision and rationale

The owner reaffirmed that agents should correct ordinary coding mistakes as
Codex can, while avoiding useless loops and following established expert
methodology. After investigation, the owner chose shared-agent recovery over a
private-pilot-only experiment and approved continuing the planned implementation.
The proposed universal one-correction-per-turn cap was withdrawn, not adopted.

OpenAI documents [bounded recovery and checking effects](https://developers.openai.com/api/docs/guides/agents-api/errors)
and [safe tool failure feedback with explicit stopping conditions](https://developers.openai.com/api/docs/guides/tools-computer-use-sdk-drivers).
These principles inform this design; they do not reveal internal Codex behavior,
select our thresholds or establish model/tool parity.

## Implementation

Use an additive `ToolCallFormatError` subtype of `ProviderError` to identify
malformed generated arguments before any call in that response is delivered to
the host. Its message is fixed and safe. It retains `non_retryable` and
`retryable=False`: model correction is separate from transport retry or fallback.
Existing consumers catching ProviderError remain compatible. No error-category,
database, settings, dependency, service or persistent-state change is required.

Ollama opts into this signal for decoded argument JSON/shape failures and a
narrow bounded HTTP500 Harmony wrapper with a recognized trailing JSON-decoder
cause. Separate the server's cause suffix from echoed generated arguments.
Unknown/truncated bodies, unrelated status codes and uncertain effects do not
enable correction. Never persist the body or echo generated fragments into the
model's feedback. Other providers are not implicitly certified by this change.

The shared loop appends fixed, explicitly host-authored user-role feedback. It
does not fabricate an assistant message, call ID or tool result for an undecoded
response. Earlier instructions, observations and exact-origin continuation remain
in history. Model requests, including failures and corrections, consume existing
iteration/deadline/admission bounds; no independent retry allowance is introduced.

For this slice, choose the approved **actionable stop** option rather than adding
production interactive checkpoint machinery. Two equivalent output failures at
the same observed file state stop the turn with retained messages and an explicit
instruction to inspect effects before resuming unfinished work. This uses the
existing pilot's repeated-failure threshold as a conservative implementation
choice, not an OpenAI-prescribed rule. Several corrections can occur in a turn
when the relevant observed state differs.

Progress observations are transient and limited to workspace paths reported by
completed tools. Hash at most1MiB per observed file on a failure; outside paths,
links, oversized/unreadable files and unknown effects do not establish progress.
Retain counts for previously seen states so no-op writes and A/B/A cycling do
not reset them. This is bounded evidence, not comprehensive workspace monitoring:
new observations can add relevant information, and unreported command effects
may conservatively lead to an earlier stop. No recursive repository scan is added.

Emit safe error attribution/count/action diagnostics and return a numeric
model-output-error count with successful loop results. CLI activity and existing
stage details surface recovery separately from tool errors. Existing numeric
usage observes failed adapter attempts; missing usage/cost remains unknown or
partial. A corrected final response does not erase the first observed failure.

## Alternatives and limits

- Terminal provider errors everywhere: smaller control surface and preserves
  prior behavior, but prevent correction of known pre-tool generation mistakes.
- Shared selective correction, chosen: improves the daily CLI and centralizes
  loop behavior, but needs provider recognition, effect/permission checks and
  composed tests. Unknown service failures remain terminal to this correction path.
- Private pilot only: lowers immediate production exposure, but duplicates the
  behavior under evaluation without improving the actual CLI; owner rejected this
  as the implementation target.

No permission, privacy, fallback-route, paid-inference or consumed-trial boundary
changes. No live prompt or automated approval is added to production. The private
pilot callback remains separately scoped. A stop permits an explicit later turn;
it cannot renew a consumed pilot allowance or replay uncertain operations.

Deterministic adapter/loop/native-CLI tests must pass before claiming software
completion. Fresh model-authored coding/test/report/frozen-review acceptance is
still required for baseline usability, independently of this software change.

Validation: full offline gate 2,450 passed / 3 skipped (workspace 2,328, Council 38,
job-search 84); full Pyright and Ruff lint/format pass. Tests cover multiple
corrections in one turn, unchanged/cycling states, preexisting effects, actual
adapter decoding, unknown/spoofed/oversized errors, permission/deadline/request
limits, native activity reporting and partial usage. No live inference ran.
